#!/usr/bin/env python3
"""
Demodulate WWV 10 MHz AM audio from a DigitalRF recording.

Processing steps:
1) Mix the RF center to baseband at the WWV carrier.
2) Decimate to an intermediate rate (default 200 kHz).
3) Narrow lowpass channel filter, then AM envelope detection.
4) Resample to audio rate and bandpass 50-2700 Hz.
"""

from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

import digital_rf as drf
import numpy as np
from scipy import signal
from scipy.io import wavfile
from tqdm import tqdm


DEFAULT_INPUT_ROOT = Path("~/data/hf_data/itsi/rooftop_20260114/M10124").expanduser()
DEFAULT_CHANNEL = "cha"
DEFAULT_TARGET_CENTER_HZ = 10_000_000.0
DEFAULT_AUDIO_RATE = 48000
DEFAULT_BLOCK_SECONDS = 1.0
DEFAULT_BANDPASS_LOW_HZ = 50.0
DEFAULT_BANDPASS_HIGH_HZ = 10_000.0
DEFAULT_DECIM_FILTER_ORDER = 6
DEFAULT_TUNE_RATE_HZ = 200_000.0
DEFAULT_TUNE_SECONDS = 2.0
DEFAULT_TUNE_SPAN_HZ = 100_000.0
DEFAULT_RF_LOWPASS_HZ = 10_000.0
DEFAULT_DEMOD = "dsb"
DEFAULT_REFERENCE_RATE = 8000

TWO_PI = 2.0 * math.pi


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert WWV 10 MHz channel to audio WAV.")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT, help="DigitalRF dataset root.")
    parser.add_argument("--channel", default=DEFAULT_CHANNEL, help="DigitalRF channel name.")
    parser.add_argument(
        "--raw-center-hz",
        type=float,
        default=None,
        help="Recorded center frequency. If omitted, uses drf_properties center_frequency_hz.",
    )
    parser.add_argument(
        "--target-center-hz",
        type=float,
        default=DEFAULT_TARGET_CENTER_HZ,
        help="Target WWV carrier frequency to demodulate.",
    )
    parser.add_argument("--audio-rate", type=int, default=DEFAULT_AUDIO_RATE, help="Audio sample rate (Hz).")
    parser.add_argument(
        "--block-seconds",
        type=float,
        default=DEFAULT_BLOCK_SECONDS,
        help="Block size in seconds for streaming processing.",
    )
    parser.add_argument(
        "--bandpass-low-hz",
        type=float,
        default=DEFAULT_BANDPASS_LOW_HZ,
        help="Audio bandpass low cutoff (Hz).",
    )
    parser.add_argument(
        "--bandpass-high-hz",
        type=float,
        default=DEFAULT_BANDPASS_HIGH_HZ,
        help="Audio bandpass high cutoff (Hz).",
    )
    parser.add_argument(
        "--decim-filter-order",
        type=int,
        default=DEFAULT_DECIM_FILTER_ORDER,
        help="Order of per-stage decimation IIR filter.",
    )
    parser.add_argument(
        "--tune-rate-hz",
        type=float,
        default=DEFAULT_TUNE_RATE_HZ,
        help="Intermediate sample rate after first decimation (Hz).",
    )
    parser.add_argument(
        "--tune-seconds",
        type=float,
        default=DEFAULT_TUNE_SECONDS,
        help="Seconds of data to estimate fine frequency offset.",
    )
    parser.add_argument(
        "--tune-span-hz",
        type=float,
        default=DEFAULT_TUNE_SPAN_HZ,
        help="Search span for fine frequency offset (Hz).",
    )
    parser.add_argument(
        "--fine-tune-hz",
        type=float,
        default=None,
        help="Override fine frequency offset (Hz). If omitted, auto-tuned.",
    )
    parser.add_argument(
        "--rf-lowpass-hz",
        type=float,
        default=DEFAULT_RF_LOWPASS_HZ,
        help="Lowpass cutoff (Hz) before AM envelope detection.",
    )
    parser.add_argument(
        "--demod",
        choices=("dsb", "envelope"),
        default=DEFAULT_DEMOD,
        help="Demodulation mode: coherent DSB-AM (dsb) or envelope.",
    )
    parser.add_argument(
        "--reference-audio",
        type=Path,
        default=None,
        help="Optional reference audio (wav/mp4) for fine-tune correlation.",
    )
    parser.add_argument(
        "--output-wav",
        type=Path,
        default=None,
        help="Output WAV path. Defaults to <input_root>/wwv_10mhz_audio.wav",
    )
    return parser.parse_args()


def _estimate_fine_tune(
    reader: drf.DigitalRFReader,
    channel: str,
    start: int,
    fs_in: float,
    mix_hz: float,
    tune_rate_hz: float,
    tune_seconds: float,
    tune_span_hz: float,
) -> float:
    tune_samples = int(round(fs_in * tune_seconds))
    block = reader.read_vector_1d(start, tune_samples, channel)
    if block.size == 0:
        raise RuntimeError("No samples available for fine-tuning.")

    block = block.astype(np.complex64, copy=False)
    block -= np.mean(block)
    n = np.arange(block.shape[0], dtype=np.float64)
    block *= np.exp(1j * (TWO_PI * mix_hz / fs_in * n)).astype(np.complex64)

    decim = int(round(fs_in / tune_rate_hz))
    if abs(fs_in / decim - tune_rate_hz) > 1e-3:
        raise ValueError(f"Cannot reach tune_rate_hz={tune_rate_hz} from fs_in={fs_in}")
    block = signal.resample_poly(block, 1, decim)
    fs_tune = fs_in / decim

    nfft = 1 << int(math.floor(math.log2(block.shape[0])))
    if nfft < 2048:
        raise ValueError("Not enough samples to estimate fine tune.")
    block = block[:nfft]
    window = np.hanning(nfft)
    spectrum = np.fft.fftshift(np.fft.fft(block * window))
    mag = np.abs(spectrum)
    freqs = (np.arange(nfft) - nfft / 2.0) * (fs_tune / nfft)

    mask = np.abs(freqs) <= tune_span_hz
    if not np.any(mask):
        raise ValueError("Tune span too small for FFT resolution.")
    peak_idx = np.argmax(mag[mask])
    peak_freq = freqs[mask][peak_idx]

    return -float(peak_freq)


def _load_reference_audio(path: Path, target_rate: int) -> np.ndarray:
    path = path.expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Reference audio not found: {path}")

    wav_path = path
    temp_file = None
    if path.suffix.lower() != ".wav":
        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_file.close()
        wav_path = Path(temp_file.name)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(target_rate),
            str(wav_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")

    try:
        rate, data = wavfile.read(str(wav_path))
    finally:
        if temp_file is not None:
            try:
                wav_path.unlink()
            except OSError:
                pass

    if data.ndim > 1:
        data = data[:, 0]
    audio = data.astype(np.float32, copy=False)
    if rate != target_rate:
        audio = signal.resample_poly(audio, target_rate, rate).astype(np.float32, copy=False)
    audio -= np.mean(audio)
    std = float(np.std(audio))
    if std > 0:
        audio /= std
    return audio


def _estimate_fine_tune_with_reference(
    reader: drf.DigitalRFReader,
    channel: str,
    start: int,
    fs_in: float,
    mix_hz: float,
    tune_rate_hz: float,
    tune_seconds: float,
    tune_span_hz: float,
    rf_lowpass_hz: float,
    ref_audio: np.ndarray,
    ref_rate: int,
) -> float:
    tune_samples = int(round(fs_in * tune_seconds))
    block = reader.read_vector_1d(start, tune_samples, channel)
    if block.size == 0:
        raise RuntimeError("No samples available for fine-tuning.")

    block = block.astype(np.complex64, copy=False)
    block -= np.mean(block)
    n = np.arange(block.shape[0], dtype=np.float64)
    block *= np.exp(1j * (TWO_PI * mix_hz / fs_in * n)).astype(np.complex64)

    decim = int(round(fs_in / tune_rate_hz))
    if abs(fs_in / decim - tune_rate_hz) > 1e-3:
        raise ValueError(f"Cannot reach tune_rate_hz={tune_rate_hz} from fs_in={fs_in}")
    block = signal.resample_poly(block, 1, decim)
    fs_tune = fs_in / decim

    rf_lp_sos = signal.butter(
        DEFAULT_DECIM_FILTER_ORDER,
        min(0.99, rf_lowpass_hz / (fs_tune / 2.0)),
        btype="low",
        output="sos",
    )
    bp_sos = signal.butter(
        4,
        [DEFAULT_BANDPASS_LOW_HZ / (ref_rate / 2.0), DEFAULT_BANDPASS_HIGH_HZ / (ref_rate / 2.0)],
        btype="bandpass",
        output="sos",
    )
    g = math.gcd(int(round(fs_tune)), int(ref_rate))
    ref_up = int(ref_rate // g)
    ref_down = int(round(fs_tune) // g)

    n1 = np.arange(block.shape[0], dtype=np.float64)

    def score_offset(offset_hz: float) -> float:
        mixed = block * np.exp(1j * (TWO_PI * offset_hz / fs_tune * n1)).astype(np.complex64)
        y = signal.sosfilt(rf_lp_sos, mixed)
        env = np.abs(y).astype(np.float32, copy=False)
        env = signal.resample_poly(env, ref_up, ref_down)
        env = signal.sosfiltfilt(bp_sos, env)
        env -= np.mean(env)
        std = float(np.std(env))
        if std > 0:
            env /= std
        m = min(env.shape[0], ref_audio.shape[0])
        return float(abs(np.dot(env[:m], ref_audio[:m])))

    coarse_step = 1000.0
    candidates = np.arange(-tune_span_hz, tune_span_hz + 0.1, coarse_step)
    best_score = -1.0
    best_offset = 0.0
    for off in candidates:
        s = score_offset(off)
        if s > best_score:
            best_score = s
            best_offset = off

    refine_step = 200.0
    refine_span = 3000.0
    candidates = np.arange(best_offset - refine_span, best_offset + refine_span + 0.1, refine_step)
    for off in candidates:
        s = score_offset(off)
        if s > best_score:
            best_score = s
            best_offset = off

    return float(best_offset)


def main() -> None:
    args = parse_args()
    input_root = args.input_root.expanduser()
    output_wav = args.output_wav or (input_root / "wwv_10mhz_audio.wav")

    reader = drf.DigitalRFReader(str(input_root))
    props = reader.get_properties(args.channel)
    fs_in = float(props["samples_per_second"])
    raw_center = args.raw_center_hz if args.raw_center_hz is not None else float(props["center_frequency_hz"])

    if args.audio_rate <= 0:
        raise ValueError("audio_rate must be positive")
    if args.bandpass_high_hz >= args.audio_rate / 2:
        raise ValueError("bandpass_high_hz must be below Nyquist")

    start, end = reader.get_bounds(args.channel)
    total_samples = end - start + 1
    block_samples = int(round(args.block_seconds * fs_in))
    if block_samples < 1:
        raise ValueError("block_seconds too small for the sample rate")

    mix_hz = raw_center - args.target_center_hz
    tune_rate_hz = float(args.tune_rate_hz)
    if tune_rate_hz <= 0:
        raise ValueError("tune_rate_hz must be positive")

    if args.fine_tune_hz is not None:
        fine_tune_hz = float(args.fine_tune_hz)
        print(f"Using fine-tune: {fine_tune_hz:+.1f} Hz")
    elif args.reference_audio is not None:
        ref_audio = _load_reference_audio(args.reference_audio, DEFAULT_REFERENCE_RATE)
        fine_tune_hz = _estimate_fine_tune_with_reference(
            reader,
            args.channel,
            start,
            fs_in,
            mix_hz,
            tune_rate_hz,
            args.tune_seconds,
            args.tune_span_hz,
            args.rf_lowpass_hz,
            ref_audio,
            DEFAULT_REFERENCE_RATE,
        )
        print(f"Reference fine-tune: {fine_tune_hz:+.1f} Hz")
    else:
        fine_tune_hz = _estimate_fine_tune(
            reader,
            args.channel,
            start,
            fs_in,
            mix_hz,
            tune_rate_hz,
            args.tune_seconds,
            args.tune_span_hz,
        )
        print(f"Auto fine-tune: {fine_tune_hz:+.1f} Hz")

    decim = int(round(fs_in / tune_rate_hz))
    if abs(fs_in / decim - tune_rate_hz) > 1e-3:
        raise ValueError(f"Cannot reach tune_rate_hz={tune_rate_hz} from fs_in={fs_in}")
    tune_rate_hz = fs_in / decim

    g = math.gcd(int(round(tune_rate_hz)), int(args.audio_rate))
    audio_up = int(args.audio_rate // g)
    audio_down = int(round(tune_rate_hz // g))
    if audio_up < 1 or audio_down < 1:
        raise ValueError("Invalid audio resample ratio.")

    phase_step = TWO_PI * (mix_hz + fine_tune_hz) / fs_in if (mix_hz + fine_tune_hz) else 0.0
    phase = 0.0

    rf_lp_sos = signal.butter(
        args.decim_filter_order,
        min(0.99, args.rf_lowpass_hz / (tune_rate_hz / 2.0)),
        btype="low",
        output="sos",
    )
    rf_lp_zi: Optional[np.ndarray] = None

    audio_blocks: List[np.ndarray] = []
    num_blocks = (total_samples + block_samples - 1) // block_samples

    for block_idx in tqdm(range(num_blocks), desc="Demodulating"):
        start_idx = start + block_idx * block_samples
        if start_idx > end:
            break
        count = min(block_samples, end - start_idx + 1)
        block = reader.read_vector_1d(start_idx, int(count), args.channel)
        if block.size == 0:
            continue

        block = block.astype(np.complex64, copy=False)
        if phase_step:
            n = np.arange(block.shape[0], dtype=np.float64)
            block *= np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
            phase = (phase + phase_step * float(block.shape[0])) % TWO_PI
        decimated = signal.resample_poly(block, 1, decim)
        if rf_lp_zi is None:
            rf_lp_zi = signal.sosfilt_zi(rf_lp_sos) * decimated[0]
        decimated, rf_lp_zi = signal.sosfilt(rf_lp_sos, decimated, zi=rf_lp_zi)

        if args.demod == "dsb":
            base = np.real(decimated).astype(np.float32, copy=False)
        else:
            base = np.abs(decimated).astype(np.float32, copy=False)

        base -= float(np.mean(base))
        audio = signal.resample_poly(base, audio_up, audio_down).astype(np.float32, copy=False)
        audio_blocks.append(audio)

    if not audio_blocks:
        raise RuntimeError("No audio produced (empty dataset?)")

    audio = np.concatenate(audio_blocks)

    nyq = args.audio_rate / 2.0
    bp = signal.butter(
        4,
        [args.bandpass_low_hz / nyq, args.bandpass_high_hz / nyq],
        btype="bandpass",
        output="sos",
    )
    audio = signal.sosfiltfilt(bp, audio).astype(np.float32, copy=False)

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = 0.9 * (audio / peak)
    audio_i16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)

    wavfile.write(str(output_wav), int(args.audio_rate), audio_i16)
    print(f"Wrote {output_wav} ({audio_i16.shape[0] / args.audio_rate:.1f} s)")


if __name__ == "__main__":
    main()
