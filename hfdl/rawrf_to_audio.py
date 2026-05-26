#!/usr/bin/env python3
"""AM/SSB demod from raw cf32 using the digital_rf_tools simple_wwv_audio pipeline."""
from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from scipy import signal

DEFAULT_TARGET_HZ = 10_000_000.0
DEFAULT_AUDIO_RATE = 48_000
DEFAULT_CHANNEL_RATE = 50_000.0
DEFAULT_BLOCK_SECONDS = 1.0
DEFAULT_CHANNEL_LP_HZ = 10_000.0
DEFAULT_CHANNEL_TRANSITION_HZ = 3_000.0
DEFAULT_AUDIO_LP_HZ = 3800.0
DEFAULT_AUDIO_TRANSITION_HZ = 1500.0
DEFAULT_AUDIO_HP_HZ = 20.0
DEFAULT_GAIN = 4000.0
DEFAULT_NORMALIZE_TARGET = 0.98
DEFAULT_NORMALIZE_PERCENTILE = 99.9
DEFAULT_NORMALIZE_SAMPLES_PER_BLOCK = 5000
DEFAULT_END_SECONDS = 0.0
DEFAULT_DEGLITCH_SIGMA = 8.0
DEFAULT_DEGLITCH_KERNEL = 9


class RawCF32Reader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._mmap = np.memmap(self.path, dtype=np.complex64, mode="r")

    def read_vector_1d(self, start: int, count: int) -> np.ndarray:
        if count <= 0:
            return np.array([], dtype=np.complex64)
        return np.asarray(self._mmap[start : start + count], dtype=np.complex64)

    def get_bounds(self) -> tuple[int, int]:
        total = int(self._mmap.size)
        if total <= 0:
            return (0, -1)
        return (0, total - 1)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AM/SSB demod from raw cf32 recordings.")
    p.add_argument("--raw-cf32", type=Path, required=True, help="Path to raw complex float32 file.")
    p.add_argument("--sample-rate", type=float, required=True, help="Sample rate (Hz).")
    p.add_argument("--center-hz", type=float, required=True, help="Recording center frequency (Hz).")
    p.add_argument("--target-hz", type=float, default=DEFAULT_TARGET_HZ, help="Target carrier to demodulate (Hz).")
    p.add_argument(
        "--demod",
        choices=("am", "usb", "lsb"),
        default="am",
        help="Demodulation mode. Default: am (envelope).",
    )
    p.add_argument("--audio-rate", type=int, default=DEFAULT_AUDIO_RATE, help="Output audio rate (Hz).")
    p.add_argument("--channel-rate", type=float, default=DEFAULT_CHANNEL_RATE, help="Intermediate rate after first decimation (Hz).")
    p.add_argument("--channel-lp-hz", type=float, default=DEFAULT_CHANNEL_LP_HZ, help="Channel lowpass cutoff (Hz).")
    p.add_argument("--channel-transition-hz", type=float, default=DEFAULT_CHANNEL_TRANSITION_HZ, help="Channel transition width (Hz).")
    p.add_argument("--block-seconds", type=float, default=DEFAULT_BLOCK_SECONDS, help="Seconds per block.")
    p.add_argument("--audio-lp-hz", type=float, default=DEFAULT_AUDIO_LP_HZ, help="Audio lowpass cutoff (Hz).")
    p.add_argument("--audio-transition-hz", type=float, default=DEFAULT_AUDIO_TRANSITION_HZ, help="Audio transition width (Hz).")
    p.add_argument("--audio-hp-hz", type=float, default=DEFAULT_AUDIO_HP_HZ, help="Audio highpass cutoff (Hz).")
    p.add_argument("--gain", type=float, default=DEFAULT_GAIN, help="Linear audio gain before writing.")
    p.add_argument("--mix-sign", type=int, choices=(-1, 1), default=-1, help="Mixing sign.")
    p.add_argument("--start-seconds", type=float, default=0.0, help="Skip this many seconds from start.")
    p.add_argument("--seconds", type=float, default=30.0, help="Process only this many seconds.")
    p.add_argument("--end-seconds", type=float, default=DEFAULT_END_SECONDS, help="Skip this many seconds from end.")
    p.add_argument("--output-wav", type=Path, default=None, help="Output WAV path.")
    return p.parse_args()


def _odd_len(value: float) -> int:
    taps = int(math.ceil(value))
    if taps % 2 == 0:
        taps += 1
    return max(taps, 3)


def _hamming_taps_for_transition(fs: float, transition_hz: float) -> int:
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
    reader: RawCF32Reader,
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
        block = reader.read_vector_1d(idx, int(count))
        if block is None:
            block = np.zeros(int(count), dtype=np.complex64)
        else:
            # Ensure writable buffer for in-place mixing/filtering.
            block = block.astype(np.complex64, copy=True)
            if block.size < count:
                pad = np.zeros(int(count) - block.size, dtype=np.complex64)
                block = np.concatenate([block, pad])

        if mix_hz != 0.0:
            n = np.arange(block.shape[0], dtype=np.float64)
            block *= np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
            phase = (phase + phase_step * block.shape[0]) % (2.0 * math.pi)

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

        if args.demod == "am":
            envelope = np.abs(decimated).astype(np.float32, copy=False)
        elif args.demod == "usb":
            envelope = np.real(decimated).astype(np.float32, copy=False)
        else:
            envelope = np.real(np.conj(decimated)).astype(np.float32, copy=False)

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
    raw = args.raw_cf32.expanduser()
    reader = RawCF32Reader(raw)
    start, end = reader.get_bounds()
    fs_in = float(args.sample_rate)
    raw_center = float(args.center_hz)

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
        combined_gain = float(args.gain) * (DEFAULT_NORMALIZE_TARGET / ref_after_gain)
    else:
        combined_gain = float(args.gain)

    output_wav = args.output_wav or raw.with_suffix("").with_suffix(".wav")
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    print("Pass 2/2: writing audio.")
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
            if not audio.size:
                continue
            audio = audio * combined_gain
            audio_i16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
            wf.writeframes(audio_i16.tobytes())
            if (block_idx + 1) % 10 == 0 or (block_idx + 1) == total_blocks:
                print(f"Wrote {block_idx + 1}/{total_blocks} blocks")

    print(f"Wrote {output_wav}")


if __name__ == "__main__":
    main()
