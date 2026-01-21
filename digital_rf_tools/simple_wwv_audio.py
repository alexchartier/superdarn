#!/usr/bin/env python3
"""
Simple WWV 10 MHz AM demod from a DigitalRF dataset.

This mirrors the 10Wideband.grc flowgraph:
mix -> decimate to ~50 kS/s -> magnitude (AM) -> resample to audio -> lowpass.
"""

from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path
from typing import Iterable, Optional

import digital_rf as drf
import numpy as np
from scipy import signal


DEFAULT_INPUT_ROOT = Path("/Users/chartat1/data/hf_data/itsi/rooftop_20260114/M10124")
DEFAULT_CHANNEL = "cha"
DEFAULT_TARGET_HZ = 10_000_000.0
DEFAULT_AUDIO_RATE = 48_000
DEFAULT_CHANNEL_RATE = 50_000.0
DEFAULT_BLOCK_SECONDS = 1.0
DEFAULT_CHANNEL_LP_HZ = 10_000.0
DEFAULT_CHANNEL_TRANSITION_HZ = 3_000.0
DEFAULT_AUDIO_LP_HZ = 3800.0
DEFAULT_AUDIO_TRANSITION_HZ = 1500.0
DEFAULT_AUDIO_HP_HZ = 20.0
DEFAULT_GAIN = 4000.0  # matches 800*5 in 10Wideband.grc
DEFAULT_NORMALIZE_TARGET = 0.98
DEFAULT_NORMALIZE_PERCENTILE = 99.9
DEFAULT_NORMALIZE_SAMPLES_PER_BLOCK = 5000
DEFAULT_END_SECONDS = 1.0
DEFAULT_DEGLITCH_SIGMA = 8.0
DEFAULT_DEGLITCH_KERNEL = 9


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Demodulate WWV 10 MHz AM audio from DigitalRF.")
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help=f"DigitalRF dataset root. Default: {DEFAULT_INPUT_ROOT}.",
    )
    p.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help=f"DigitalRF channel name. Default: {DEFAULT_CHANNEL}.",
    )
    p.add_argument(
        "--raw-center-hz",
        type=float,
        default=None,
        help="Recorded center frequency (Hz). Default: DigitalRF metadata center_frequency_hz when present (supersedes the default None).",
    )
    p.add_argument(
        "--target-hz",
        type=float,
        default=DEFAULT_TARGET_HZ,
        help=f"Target carrier to demodulate (Hz). Default: {DEFAULT_TARGET_HZ:g}.",
    )
    p.add_argument(
        "--audio-rate",
        type=int,
        default=DEFAULT_AUDIO_RATE,
        help=f"Output audio rate (Hz). Default: {DEFAULT_AUDIO_RATE}.",
    )
    p.add_argument(
        "--channel-rate",
        type=float,
        default=DEFAULT_CHANNEL_RATE,
        help=f"Intermediate rate after first decimation (Hz). Default: {DEFAULT_CHANNEL_RATE:g}.",
    )
    p.add_argument(
        "--channel-lp-hz",
        type=float,
        default=DEFAULT_CHANNEL_LP_HZ,
        help=f"Lowpass cutoff before envelope detection (Hz). Default: {DEFAULT_CHANNEL_LP_HZ:g}.",
    )
    p.add_argument(
        "--channel-transition-hz",
        type=float,
        default=DEFAULT_CHANNEL_TRANSITION_HZ,
        help=f"Transition width for the channel lowpass (Hz). Default: {DEFAULT_CHANNEL_TRANSITION_HZ:g}.",
    )
    p.add_argument(
        "--block-seconds",
        type=float,
        default=DEFAULT_BLOCK_SECONDS,
        help=f"Seconds of RF to process per block. Default: {DEFAULT_BLOCK_SECONDS:g}.",
    )
    p.add_argument(
        "--audio-lp-hz",
        type=float,
        default=DEFAULT_AUDIO_LP_HZ,
        help=f"Audio lowpass cutoff (Hz). Default: {DEFAULT_AUDIO_LP_HZ:g}.",
    )
    p.add_argument(
        "--audio-transition-hz",
        type=float,
        default=DEFAULT_AUDIO_TRANSITION_HZ,
        help=f"Audio lowpass transition width (Hz). Default: {DEFAULT_AUDIO_TRANSITION_HZ:g}.",
    )
    p.add_argument(
        "--audio-hp-hz",
        type=float,
        default=DEFAULT_AUDIO_HP_HZ,
        help=f"Audio highpass cutoff for DC blocking (Hz). Default: {DEFAULT_AUDIO_HP_HZ:g}.",
    )
    p.add_argument(
        "--gain",
        type=float,
        default=DEFAULT_GAIN,
        help=f"Linear audio gain before writing. Default: {DEFAULT_GAIN:g}.",
    )
    p.add_argument(
        "--mix-sign",
        type=int,
        choices=(-1, 1),
        default=-1,
        help="Sign for mixing (+1 or -1). Default: -1 (matches GNU Radio freq_xlating_fir_filter).",
    )
    p.add_argument(
        "--start-seconds",
        type=float,
        default=2.0,
        help="Skip this many seconds from the start. Default: 2.0.",
    )
    p.add_argument(
        "--end-seconds",
        type=float,
        default=DEFAULT_END_SECONDS,
        help=f"Skip this many seconds from the end (after --seconds). Default: {DEFAULT_END_SECONDS:g}.",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Process only this many seconds. Default: to end.",
    )
    p.add_argument(
        "--output-wav",
        type=Path,
        default=None,
        help="Output WAV path. Default: <input-root>/wwv_10mhz_audio_simple.wav.",
    )
    return p.parse_args()


def _odd_len(value: float) -> int:
    taps = int(math.ceil(value))
    if taps % 2 == 0:
        taps += 1
    return max(taps, 3)


def _hamming_taps_for_transition(fs: float, transition_hz: float) -> int:
    # Hamming rule-of-thumb: transition width ~= 3.3 * fs / N.
    if transition_hz <= 0:
        raise ValueError("transition_hz must be positive")
    return _odd_len(3.3 * fs / transition_hz)


def _resample_taps(up: int, down: int, dtype: np.dtype) -> tuple[np.ndarray, int, int]:
    g = math.gcd(up, down)
    up //= g
    down //= g
    max_rate = max(up, down)
    cutoff = 1.0 / max_rate
    half_len = 10 * max_rate
    taps = signal.firwin(2 * half_len + 1, cutoff, window=("kaiser", 5.0)).astype(dtype)
    taps *= up
    return taps, up, down


def _stream_resample(
    x: np.ndarray,
    up: int,
    down: int,
    taps: np.ndarray,
    zi: np.ndarray,
    offset: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    if x.size == 0:
        return x, zi, offset
    if up > 1:
        upsampled = np.zeros(x.size * up, dtype=x.dtype)
        upsampled[::up] = x
        filt, zi = signal.lfilter(taps, [1.0], upsampled, zi=zi)
    else:
        filt, zi = signal.lfilter(taps, [1.0], x, zi=zi)
    out = filt[offset::down]
    offset = (offset - filt.size) % down
    return out, zi, offset


def _deglitch_audio(audio: np.ndarray) -> np.ndarray:
    if audio.size < 3 or DEFAULT_DEGLITCH_SIGMA <= 0.0 or DEFAULT_DEGLITCH_KERNEL < 3:
        return audio
    abs_audio = np.abs(audio)
    median = float(np.median(abs_audio))
    mad = float(np.median(np.abs(abs_audio - median)))
    sigma = 1.4826 * mad
    if sigma <= 0.0:
        return audio
    thresh = median + DEFAULT_DEGLITCH_SIGMA * sigma
    mask = abs_audio > thresh
    if not np.any(mask):
        return audio
    kernel = DEFAULT_DEGLITCH_KERNEL
    if kernel % 2 == 0:
        kernel += 1
    if kernel > audio.size:
        kernel = audio.size if audio.size % 2 == 1 else max(3, audio.size - 1)
    if kernel < 3:
        return audio
    filtered = signal.medfilt(audio, kernel_size=kernel)
    cleaned = audio.copy()
    cleaned[mask] = filtered[mask]
    return cleaned


def _iter_audio_blocks(
    reader: drf.DigitalRFReader,
    args: argparse.Namespace,
    start: int,
    end: int,
    block_samples: int,
    fs_in: float,
    raw_center: float,
    decim1: int,
    decim2: int,
    channel_taps: np.ndarray,
    audio_taps: np.ndarray,
    audio_hp_sos: Optional[np.ndarray],
    decim1_taps: Optional[np.ndarray],
    decim2_taps: Optional[np.ndarray],
    audio_rs_taps: Optional[np.ndarray],
    audio_up: int,
    audio_down: int,
) -> Iterable[np.ndarray]:
    mix_hz = raw_center - args.target_hz
    phase_step = float(args.mix_sign) * 2.0 * math.pi * mix_hz / fs_in
    phase = 0.0

    channel_zi = np.zeros(len(channel_taps) - 1, dtype=np.complex64)
    audio_zi = np.zeros(len(audio_taps) - 1, dtype=np.float32)
    audio_hp_zi = None

    decim1_zi = np.zeros(len(decim1_taps) - 1, dtype=np.complex64) if decim1_taps is not None else None
    decim1_offset = 0
    decim2_zi = np.zeros(len(decim2_taps) - 1, dtype=np.complex64) if decim2_taps is not None else None
    decim2_offset = 0
    audio_rs_zi = np.zeros(len(audio_rs_taps) - 1, dtype=np.float32) if audio_rs_taps is not None else None
    audio_rs_offset = 0

    total_samples = end - start + 1
    total_blocks = (total_samples + block_samples - 1) // block_samples

    for block_idx in range(total_blocks):
        idx = start + block_idx * block_samples
        if idx > end:
            break
        count = min(block_samples, end - idx + 1)
        block = reader.read_vector_1d(idx, int(count), args.channel)
        if block is None:
            block = np.zeros(int(count), dtype=np.complex64)
        else:
            block = block.astype(np.complex64, copy=False)
            if block.size < count:
                pad = np.zeros(int(count) - block.size, dtype=np.complex64)
                block = np.concatenate([block, pad])

        # Match the MATLAB cfile scaling (int16 -> float [-1,1]).
        block *= np.float32(1.0 / 32768.0)

        if mix_hz != 0.0:
            n = np.arange(block.shape[0], dtype=np.float64)
            block *= np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
            phase = (phase + phase_step * block.shape[0]) % (2.0 * math.pi)

        # Decimate in two stages to keep the channel filter manageable.
        if decim1 > 1:
            stage1, decim1_zi, decim1_offset = _stream_resample(
                block,
                1,
                decim1,
                decim1_taps,
                decim1_zi,
                decim1_offset,
            )
        else:
            stage1 = block

        # Channel lowpass before envelope detection.
        stage1, channel_zi = signal.lfilter(channel_taps, [1.0], stage1, zi=channel_zi)

        if decim2 > 1:
            decimated, decim2_zi, decim2_offset = _stream_resample(
                stage1,
                1,
                decim2,
                decim2_taps,
                decim2_zi,
                decim2_offset,
            )
        else:
            decimated = stage1

        # Envelope detect (AM).
        envelope = np.abs(decimated).astype(np.float32, copy=False)

        # Resample to audio rate and apply audio lowpass.
        if audio_rs_taps is None or audio_up == audio_down:
            audio = envelope
        else:
            audio, audio_rs_zi, audio_rs_offset = _stream_resample(
                envelope,
                audio_up,
                audio_down,
                audio_rs_taps,
                audio_rs_zi,
                audio_rs_offset,
            )
        audio, audio_zi = signal.lfilter(audio_taps, [1.0], audio, zi=audio_zi)
        if audio_hp_sos is not None:
            if audio_hp_zi is None:
                audio_hp_zi = signal.sosfilt_zi(audio_hp_sos) * audio[0]
            audio, audio_hp_zi = signal.sosfilt(audio_hp_sos, audio, zi=audio_hp_zi)

        audio = _deglitch_audio(audio)

        yield audio


def main() -> None:
    args = parse_args()
    input_root = args.dataset_root.expanduser()
    output_wav = args.output_wav or (input_root / "wwv_10mhz_audio_simple.wav")

    reader = drf.DigitalRFReader(str(input_root))
    props = reader.get_properties(args.channel)
    fs_in = float(props["samples_per_second"])
    raw_center = float(props["center_frequency_hz"]) if args.raw_center_hz is None else float(args.raw_center_hz)

    start, end = reader.get_bounds(args.channel)
    if args.start_seconds > 0:
        start += int(round(args.start_seconds * fs_in))
    if args.seconds is not None:
        end = min(end, start + int(round(args.seconds * fs_in)) - 1)
    if args.end_seconds > 0:
        end -= int(round(args.end_seconds * fs_in))
    if start > end:
        raise ValueError("Requested time span is empty.")

    block_samples = int(round(args.block_seconds * fs_in))
    if block_samples < 1:
        raise ValueError("block_seconds too small for the input rate.")

    decim = int(round(fs_in / args.channel_rate))
    if decim < 1 or abs(fs_in / decim - args.channel_rate) > 1e-3:
        raise ValueError(f"Cannot reach channel_rate={args.channel_rate} from fs_in={fs_in}.")
    channel_rate = fs_in / decim

    # Two-stage decimation keeps the channel filter tractable.
    decim1 = 50 if decim % 50 == 0 else 1
    decim2 = decim // decim1
    stage1_rate = fs_in / decim1

    if decim2 < 1:
        raise ValueError("Invalid decimation stages.")

    channel_rate_int = int(round(channel_rate))
    if abs(channel_rate_int - channel_rate) > 1e-6:
        raise ValueError("channel_rate must be an integer for the simple resampler.")

    g = math.gcd(channel_rate_int, int(args.audio_rate))
    audio_up = args.audio_rate // g
    audio_down = channel_rate_int // g
    if audio_up < 1 or audio_down < 1:
        raise ValueError("Invalid audio resampling ratio.")

    decim1_taps = None
    if decim1 > 1:
        decim1_taps, _, _ = _resample_taps(1, decim1, np.float32)

    channel_taps = signal.firwin(
        _hamming_taps_for_transition(stage1_rate, args.channel_transition_hz),
        args.channel_lp_hz,
        fs=stage1_rate,
        window="hamming",
    )

    decim2_taps = None
    if decim2 > 1:
        decim2_taps, _, _ = _resample_taps(1, decim2, np.float32)

    audio_rs_taps, audio_up, audio_down = _resample_taps(audio_up, audio_down, np.float32)
    if audio_up == audio_down:
        audio_rs_taps = None

    audio_taps = signal.firwin(
        _hamming_taps_for_transition(args.audio_rate, args.audio_transition_hz),
        args.audio_lp_hz,
        fs=args.audio_rate,
        window="hamming",
    )
    audio_hp_sos = None
    if args.audio_hp_hz > 0:
        audio_hp_sos = signal.butter(2, args.audio_hp_hz, btype="highpass", fs=args.audio_rate, output="sos")

    total_samples = end - start + 1
    total_blocks = (total_samples + block_samples - 1) // block_samples

    print("Pass 1/2: scanning for normalization stats.")
    peak = 0.0
    norm_samples = []
    for block_idx, audio in enumerate(
        _iter_audio_blocks(
            reader,
            args,
            start,
            end,
            block_samples,
            fs_in,
            raw_center,
            decim1,
            decim2,
            channel_taps,
            audio_taps,
            audio_hp_sos,
            decim1_taps,
            decim2_taps,
            audio_rs_taps,
            audio_up,
            audio_down,
        )
    ):
        if audio.size:
            abs_audio = np.abs(audio)
            peak = max(peak, float(np.max(abs_audio)))
            if abs_audio.size > DEFAULT_NORMALIZE_SAMPLES_PER_BLOCK:
                step = int(math.ceil(abs_audio.size / DEFAULT_NORMALIZE_SAMPLES_PER_BLOCK))
                abs_audio = abs_audio[::step]
            norm_samples.append(abs_audio)
        if (block_idx + 1) % 10 == 0 or (block_idx + 1) == total_blocks:
            print(f"Analyzed {block_idx + 1}/{total_blocks} blocks")

    if norm_samples:
        norm_values = np.concatenate(norm_samples)
        norm_ref = float(np.percentile(norm_values, DEFAULT_NORMALIZE_PERCENTILE))
    else:
        norm_ref = 0.0
    ref_after_gain = norm_ref * float(args.gain)
    if ref_after_gain > DEFAULT_NORMALIZE_TARGET and ref_after_gain > 0.0:
        norm_gain = DEFAULT_NORMALIZE_TARGET / ref_after_gain
    else:
        norm_gain = 1.0
    combined_gain = float(args.gain) * norm_gain
    peak_after_gain = peak * float(args.gain)
    print(
        "Normalization scale: "
        f"{norm_gain:.4f} (combined gain {combined_gain:.4f}, "
        f"p{DEFAULT_NORMALIZE_PERCENTILE:.1f} {ref_after_gain:.4f}, "
        f"peak {peak_after_gain:.4f})"
    )

    print("Pass 2/2: writing WAV.")
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(args.audio_rate))

        for block_idx, audio in enumerate(
            _iter_audio_blocks(
                reader,
                args,
                start,
                end,
                block_samples,
                fs_in,
                raw_center,
                decim1,
                decim2,
                channel_taps,
                audio_taps,
                audio_hp_sos,
                decim1_taps,
                decim2_taps,
                audio_rs_taps,
                audio_up,
                audio_down,
            )
        ):
            audio *= combined_gain
            audio_i16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
            wf.writeframes(audio_i16.tobytes())

            if (block_idx + 1) % 10 == 0 or (block_idx + 1) == total_blocks:
                print(f"Processed {block_idx + 1}/{total_blocks} blocks")

    print(f"Wrote {output_wav}")


if __name__ == "__main__":
    main()
