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
DEFAULT_GAIN = 4000.0  # matches 800*5 in 10Wideband.grc


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Demodulate WWV 10 MHz AM audio from DigitalRF.")
    p.add_argument("--dataset-root", type=Path, default=DEFAULT_INPUT_ROOT, help="DigitalRF dataset root.")
    p.add_argument("--channel", default=DEFAULT_CHANNEL, help="DigitalRF channel name.")
    p.add_argument(
        "--raw-center-hz",
        type=float,
        default=None,
        help="Recorded center frequency (Hz). If omitted, uses drf_properties.",
    )
    p.add_argument("--target-hz", type=float, default=DEFAULT_TARGET_HZ, help="Target carrier to demodulate (Hz).")
    p.add_argument("--audio-rate", type=int, default=DEFAULT_AUDIO_RATE, help="Output audio rate (Hz).")
    p.add_argument(
        "--channel-rate",
        type=float,
        default=DEFAULT_CHANNEL_RATE,
        help="Intermediate rate after first decimation (Hz).",
    )
    p.add_argument(
        "--channel-lp-hz",
        type=float,
        default=DEFAULT_CHANNEL_LP_HZ,
        help="Lowpass cutoff before envelope detection (Hz).",
    )
    p.add_argument(
        "--channel-transition-hz",
        type=float,
        default=DEFAULT_CHANNEL_TRANSITION_HZ,
        help="Transition width for the channel lowpass (Hz).",
    )
    p.add_argument(
        "--block-seconds",
        type=float,
        default=DEFAULT_BLOCK_SECONDS,
        help="Seconds of RF to process per block.",
    )
    p.add_argument(
        "--audio-lp-hz",
        type=float,
        default=DEFAULT_AUDIO_LP_HZ,
        help="Audio lowpass cutoff (Hz).",
    )
    p.add_argument(
        "--audio-transition-hz",
        type=float,
        default=DEFAULT_AUDIO_TRANSITION_HZ,
        help="Audio lowpass transition width (Hz).",
    )
    p.add_argument("--gain", type=float, default=DEFAULT_GAIN, help="Linear audio gain before writing.")
    p.add_argument(
        "--mix-sign",
        type=int,
        choices=(-1, 1),
        default=-1,
        help="Sign for mixing (+1 or -1). Use -1 to match GNU Radio freq_xlating_fir_filter.",
    )
    p.add_argument("--start-seconds", type=float, default=0.0, help="Skip this many seconds from the start.")
    p.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Process only this many seconds (default: to end).",
    )
    p.add_argument(
        "--output-wav",
        type=Path,
        default=None,
        help="Output WAV path (default: <input-root>/wwv_10mhz_audio_simple.wav).",
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

    mix_hz = raw_center - args.target_hz
    phase_step = float(args.mix_sign) * 2.0 * math.pi * mix_hz / fs_in
    phase = 0.0

    channel_taps = signal.firwin(
        _hamming_taps_for_transition(stage1_rate, args.channel_transition_hz),
        args.channel_lp_hz,
        fs=stage1_rate,
        window="hamming",
    )
    channel_zi = np.zeros(len(channel_taps) - 1, dtype=np.complex64)

    audio_taps = signal.firwin(
        _hamming_taps_for_transition(args.audio_rate, args.audio_transition_hz),
        args.audio_lp_hz,
        fs=args.audio_rate,
        window="hamming",
    )
    audio_zi = np.zeros(len(audio_taps) - 1, dtype=np.float32)

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(args.audio_rate))

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
                stage1 = signal.resample_poly(block, 1, decim1).astype(np.complex64, copy=False)
            else:
                stage1 = block

            # Channel lowpass before envelope detection.
            stage1, channel_zi = signal.lfilter(channel_taps, [1.0], stage1, zi=channel_zi)

            decimated = signal.resample_poly(stage1, 1, decim2).astype(np.complex64, copy=False)

            # Envelope detect (AM).
            envelope = np.abs(decimated).astype(np.float32, copy=False)

            # Resample to audio rate and apply audio lowpass.
            audio = signal.resample_poly(envelope, audio_up, audio_down).astype(np.float32, copy=False)
            audio, audio_zi = signal.lfilter(audio_taps, [1.0], audio, zi=audio_zi)

            # Scale and write.
            audio *= float(args.gain)
            audio_i16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
            wf.writeframes(audio_i16.tobytes())

            if (block_idx + 1) % 10 == 0 or (block_idx + 1) == total_blocks:
                print(f"Processed {block_idx + 1}/{total_blocks} blocks")

    print(f"Wrote {output_wav}")


if __name__ == "__main__":
    main()
