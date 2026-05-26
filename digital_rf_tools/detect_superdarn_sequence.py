#!/usr/bin/env python3
"""
Detect a SuperDARN pulse sequence in a DigitalRF recording.

The detector:
1) reads a short DigitalRF span;
2) finds candidate narrowband lines near the configured center frequency;
3) mixes each candidate to baseband and decimates;
4) matched-filters each PRI against a SuperDARN pulse sequence;
5) reports the best delay/frequency hit and an approximate Doppler from the
   matched-filter phase progression across PRIs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import digital_rf as drf
import numpy as np
from scipy import signal

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:
    from drf_compat import open_drf_like_reader
except ImportError:  # pragma: no cover
    from digital_rf_tools.drf_compat import open_drf_like_reader


SEQUENCES = {
    "7p": {
        "pulse_sequence": [0, 9, 12, 20, 22, 26, 27],
        "tau_us": 2400.0,
        "pulse_len_us": 300.0,
        "pri_s": 0.1,
    },
    "8p": {
        "pulse_sequence": [0, 14, 22, 24, 27, 31, 42, 43],
        "tau_us": 1500.0,
        "pulse_len_us": 300.0,
        "pri_s": 0.1,
    },
}
DECIM_FIR_TAPS = 161


@dataclass
class Candidate:
    offset_hz: float
    abs_freq_hz: float
    line_db: float
    mod10: float
    score: float


@dataclass
class Detection:
    offset_hz: float
    abs_freq_hz: float
    lag_samples: int
    lag_us: float
    one_way_range_km: float
    score: float
    amplitude_median: float
    amplitude_peak: float
    doppler_hz: float | None
    kept_pris: int
    pri_count: int


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect a SuperDARN pulse sequence in DigitalRF.")
    p.add_argument("--dataset-root", type=Path, required=True, help="DigitalRF dataset root.")
    p.add_argument("--channel", default=None, help="Channel name. Default: first channel in the dataset.")
    p.add_argument("--center-hz", type=float, default=None, help="RF center frequency. Default: infer from metadata.")
    p.add_argument("--sequence", choices=sorted(SEQUENCES), default="7p", help="Pulse sequence to match. Default: 7p.")
    p.add_argument("--skip-seconds", type=float, default=10.0, help="Skip this many seconds from the start. Default: 10.")
    p.add_argument("--seconds", type=float, default=20.0, help="Seconds of RF to analyze. Default: 20.")
    p.add_argument("--search-span-hz", type=float, default=100e3, help="Search candidate carriers within +/- this span. Default: 100e3.")
    p.add_argument("--nfft", type=int, default=4096, help="FFT length for candidate search. Default: 4096.")
    p.add_argument("--max-candidates", type=int, default=12, help="Maximum candidate carriers to evaluate. Default: 12.")
    p.add_argument("--decimated-rate", type=float, default=100e3, help="Baseband rate for matched filtering. Default: 100e3.")
    p.add_argument("--channel-lp-hz", type=float, default=12e3, help="Lowpass cutoff before decimation. Default: 12e3.")
    p.add_argument("--fine-span-hz", type=float, default=1500.0, help="Residual frequency search span around the best coarse hit. Default: 1500.")
    p.add_argument("--fine-step-hz", type=float, default=50.0, help="Residual frequency search step. Default: 50.")
    p.add_argument("--output-prefix", type=Path, default=None, help="Output prefix for JSON/PNG. Default: ./<dataset>_<sequence>_superdarn")
    return p.parse_args()


def _infer_center_hz(dataset_root: Path) -> float | None:
    meta_root = dataset_root / "metadata"
    if not meta_root.exists():
        return None
    try:
        reader = drf.DigitalMetadataReader(str(meta_root))
        start, _ = reader.get_bounds()
        payload = reader.read(start, start + 1)
        if not payload:
            return None
        meta = next(iter(payload.values()))
        for key in ("center_frequency_hz", "freq_hz", "frequency_hz"):
            if key in meta and meta[key] not in ("", None):
                return float(meta[key])
    except Exception:
        return None
    return None


def _infer_start_epoch(dataset_root: Path, start_sample: int, fs: float) -> float:
    meta_root = dataset_root / "metadata"
    if meta_root.exists():
        try:
            reader = drf.DigitalMetadataReader(str(meta_root))
            start, _ = reader.get_bounds()
            payload = reader.read(start, start + 1)
            if payload:
                meta = next(iter(payload.values()))
                if "start_epoch_seconds" in meta:
                    return float(meta["start_epoch_seconds"])
        except Exception:
            pass
    return float(start_sample) / fs


def _output_prefix(args: argparse.Namespace) -> Path:
    if args.output_prefix is not None:
        return args.output_prefix
    return Path.cwd() / f"{args.dataset_root.name}_{args.sequence}_superdarn"


def _load_span(reader: drf.DigitalRFReader, channel: str, start_sample: int, total_samples: int) -> tuple[np.ndarray, float]:
    stop_sample = start_sample + total_samples - 1
    blocks = reader.get_continuous_blocks(start_sample, stop_sample, channel)
    if not blocks:
        raise RuntimeError("No data blocks found in the requested range.")

    data = np.zeros(total_samples, dtype=np.complex64)
    finite_count = 0
    for block_start, block_len in blocks.items():
        lo = max(start_sample, block_start)
        hi = min(stop_sample, block_start + block_len - 1)
        if hi < lo:
            continue
        chunk = reader.read_vector_1d(lo, hi - lo + 1, channel).astype(np.complex64, copy=False)
        finite = np.isfinite(chunk.real) & np.isfinite(chunk.imag)
        finite_count += int(np.count_nonzero(finite))
        chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.0, neginf=0.0)
        data[lo - start_sample : hi - start_sample + 1] = chunk
    return data, float(finite_count) / max(total_samples, 1)


def _spectral_candidates(
    x: np.ndarray,
    fs: float,
    center_hz: float,
    pri_hz: float,
    search_span_hz: float,
    nfft: int,
    max_candidates: int,
) -> tuple[np.ndarray, np.ndarray, list[Candidate]]:
    n = (x.size // nfft) * nfft
    if n < nfft:
        raise RuntimeError("Not enough samples for the requested FFT length.")
    blocks = x[:n].reshape(-1, nfft)
    window = np.hanning(nfft).astype(np.float32)
    win_pow = float(np.sum(window**2))

    spec = np.fft.fft(blocks * window[None, :], axis=1)
    power = (np.abs(spec) ** 2) / max(win_pow, 1e-12)
    sum_psd = power.sum(axis=0)
    times = (np.arange(blocks.shape[0], dtype=np.float64) * nfft + 0.5 * nfft) / fs
    ph = np.exp(-2j * np.pi * pri_hz * times)
    sum_pri = (power * ph[:, None]).sum(axis=0)

    mean_psd = sum_psd / blocks.shape[0]
    mod = np.abs(sum_pri) / np.maximum(sum_psd, 1e-12)
    freqs = np.fft.fftfreq(nfft, d=1.0 / fs)
    mean_db = 10.0 * np.log10(np.maximum(mean_psd, 1e-20))
    kernel = min(201, mean_db.size - (1 - mean_db.size % 2))
    if kernel < 3:
        kernel = 3
    if kernel % 2 == 0:
        kernel -= 1
    baseline = signal.medfilt(mean_db, kernel_size=kernel)
    line_db = mean_db - baseline
    score = np.maximum(line_db, 0.0) * mod

    mask = np.abs(freqs) <= search_span_hz
    masked = np.where(mask, score, -np.inf)
    peak_idx, _ = signal.find_peaks(masked, distance=max(2, nfft // 512))
    if peak_idx.size == 0:
        peak_idx = np.where(mask)[0]
    order = peak_idx[np.argsort(masked[peak_idx])[::-1]]

    out: list[Candidate] = []
    used: list[int] = []
    guard = max(1, nfft // 128)
    for idx in order:
        if not np.isfinite(masked[idx]):
            continue
        if any(abs(idx - prev) <= guard for prev in used):
            continue
        out.append(
            Candidate(
                offset_hz=float(freqs[idx]),
                abs_freq_hz=float(center_hz + freqs[idx]),
                line_db=float(line_db[idx]),
                mod10=float(mod[idx]),
                score=float(score[idx]),
            )
        )
        used.append(int(idx))
        if len(out) >= max_candidates:
            break
    return freqs, mean_db, out


def _iter_mixed_decimated(
    x: np.ndarray,
    fs_in: float,
    mix_hz: float,
    fs_out: float,
    lp_hz: float,
    chunk_samples: int = 2_000_000,
) -> Iterable[np.ndarray]:
    decim = int(round(fs_in / fs_out))
    if not math.isclose(fs_in / fs_out, decim, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("decimated-rate must divide the input sample rate exactly.")
    taps = signal.firwin(DECIM_FIR_TAPS, lp_hz, fs=fs_in).astype(np.float32)
    zi = np.zeros(taps.size - 1, dtype=np.complex64)
    phase = 0.0
    phase_step = -2.0 * math.pi * mix_hz / fs_in
    decim_offset = 0

    for start in range(0, x.size, chunk_samples):
        chunk = x[start : start + chunk_samples]
        if chunk.size == 0:
            continue
        n = np.arange(chunk.size, dtype=np.float64)
        mixer = np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
        mixed = chunk * mixer
        phase = (phase + phase_step * chunk.size) % (2.0 * math.pi)
        filt, zi = signal.lfilter(taps, [1.0], mixed, zi=zi)
        out = filt[decim_offset::decim]
        decim_offset = (decim_offset - filt.size) % decim
        if out.size:
            yield out.astype(np.complex64, copy=False)


def _mix_decimate(x: np.ndarray, fs_in: float, mix_hz: float, fs_out: float, lp_hz: float) -> np.ndarray:
    pieces = list(_iter_mixed_decimated(x, fs_in=fs_in, mix_hz=mix_hz, fs_out=fs_out, lp_hz=lp_hz))
    if not pieces:
        return np.array([], dtype=np.complex64)
    return np.concatenate(pieces)


def _match_sequence(
    y: np.ndarray,
    fs: float,
    global_start_sample: int,
    pulse_sequence: list[int],
    tau_us: float,
    pulse_len_us: float,
    pri_s: float,
) -> tuple[np.ndarray, np.ndarray, Detection]:
    pri_samples = int(round(pri_s * fs))
    pulse_samples = int(round(pulse_len_us * 1e-6 * fs))
    offsets = np.round(np.asarray(pulse_sequence, dtype=np.float64) * tau_us * 1e-6 * fs).astype(int)
    template_span = int(offsets[-1] + pulse_samples)
    valid_lags = pri_samples - template_span + 1
    if valid_lags <= 0:
        raise RuntimeError("PRI is shorter than the requested pulse sequence.")

    frame_offset = (-global_start_sample) % pri_samples
    usable = y[frame_offset:]
    pri_count = usable.size // pri_samples
    frames = usable[: pri_count * pri_samples].reshape(pri_count, pri_samples)
    env_frames = np.abs(frames).astype(np.float64, copy=False)
    env_frames = np.maximum(env_frames - np.median(env_frames, axis=1, keepdims=True), 0.0)
    env_cs = np.concatenate(
        [np.zeros((pri_count, 1), dtype=np.float64), np.cumsum(env_frames, axis=1, dtype=np.float64)],
        axis=1,
    )
    env_box = env_cs[:, pulse_samples:] - env_cs[:, :-pulse_samples]
    env_corr = np.zeros((pri_count, valid_lags), dtype=np.float64)
    for off in offsets:
        env_corr += env_box[:, off : off + valid_lags]

    cs = np.concatenate(
        [np.zeros((pri_count, 1), dtype=np.complex128), np.cumsum(frames, axis=1, dtype=np.complex128)],
        axis=1,
    )
    box = cs[:, pulse_samples:] - cs[:, :-pulse_samples]
    corr = np.zeros((pri_count, valid_lags), dtype=np.complex128)
    for off in offsets:
        corr += box[:, off : off + valid_lags]

    profile = np.mean(env_corr, axis=0)
    lag_samples = int(np.argmax(profile))
    series = corr[:, lag_samples]
    amp = env_corr[:, lag_samples]
    median_amp = float(np.median(amp))
    peak_amp = float(np.max(amp))
    mad_amp = float(np.median(np.abs(amp - median_amp))) + 1e-12
    keep = amp > (median_amp + 3.0 * 1.4826 * mad_amp)

    doppler_hz = None
    if np.count_nonzero(keep) >= 8:
        seq_times = np.arange(pri_count, dtype=np.float64)[keep] * pri_s
        phase = np.unwrap(np.angle(series[keep]))
        slope, _ = np.polyfit(seq_times, phase, 1)
        doppler_hz = float(slope / (2.0 * math.pi))

    lag_us = 1e6 * lag_samples / fs
    one_way_range_km = 299_792.458 * lag_us * 1e-6
    median_profile = float(np.median(profile))
    sigma_profile = float(1.4826 * np.median(np.abs(profile - median_profile)) + 1e-12)
    det = Detection(
        offset_hz=0.0,
        abs_freq_hz=0.0,
        lag_samples=lag_samples,
        lag_us=float(lag_us),
        one_way_range_km=float(one_way_range_km),
        score=float((profile[lag_samples] - median_profile) / sigma_profile),
        amplitude_median=median_amp,
        amplitude_peak=peak_amp,
        doppler_hz=doppler_hz,
        kept_pris=int(np.count_nonzero(keep)),
        pri_count=int(pri_count),
    )
    return profile, series, det


def _refine_frequency(
    y_coarse: np.ndarray,
    fs: float,
    global_start_sample: int,
    coarse_offset_hz: float,
    pulse_sequence: list[int],
    tau_us: float,
    pulse_len_us: float,
    pri_s: float,
    fine_span_hz: float,
    fine_step_hz: float,
) -> tuple[float, np.ndarray, np.ndarray, Detection]:
    t = np.arange(y_coarse.size, dtype=np.float64) / fs
    residuals = np.arange(-fine_span_hz, fine_span_hz + 0.5 * fine_step_hz, fine_step_hz, dtype=np.float64)

    best_profile = np.array([], dtype=np.float64)
    best_series = np.array([], dtype=np.complex128)
    best_det: Detection | None = None
    best_offset = float(coarse_offset_hz)

    for residual in residuals:
        y = y_coarse * np.exp(-2j * np.pi * residual * t).astype(np.complex64)
        profile, series, det = _match_sequence(
            y,
            fs=fs,
            global_start_sample=global_start_sample,
            pulse_sequence=pulse_sequence,
            tau_us=tau_us,
            pulse_len_us=pulse_len_us,
            pri_s=pri_s,
        )
        if best_det is None or det.score > best_det.score:
            best_profile = profile
            best_series = series
            best_det = det
            best_offset = float(coarse_offset_hz + residual)

    assert best_det is not None
    return best_offset, best_profile, best_series, best_det


def _plot_results(
    path: Path,
    center_hz: float,
    freqs: np.ndarray,
    mean_db: np.ndarray,
    candidates: list[Candidate],
    best: Detection,
    profile: np.ndarray,
    series: np.ndarray,
    fs_match: float,
    pri_s: float,
    dataset_name: str,
    sequence_label: str,
) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(12, 12), constrained_layout=True)

    ax = axes[0]
    ax.plot((center_hz + freqs) / 1e6, mean_db, lw=1.0, color="0.2")
    for cand in candidates:
        color = "tab:red" if abs(cand.offset_hz - best.offset_hz) < 1e-6 else "tab:blue"
        ax.axvline(cand.abs_freq_hz / 1e6, color=color, alpha=0.5, lw=1.0)
    ax.set_title(f"{dataset_name} average spectrum")
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("PSD (dB)")

    ax = axes[1]
    lag_ms = np.arange(profile.size, dtype=np.float64) * 1e3 / fs_match
    ax.plot(lag_ms, profile, lw=1.0)
    ax.axvline(best.lag_us * 1e-3, color="tab:red", ls="--", lw=1.0)
    ax.set_title(f"{sequence_label} matched-filter profile")
    ax.set_xlabel("Lag within PRI (ms)")
    ax.set_ylabel("Mean |MF|")

    ax = axes[2]
    seq_idx = np.arange(series.size, dtype=np.float64)
    ax.plot(seq_idx * pri_s, np.abs(series), lw=1.0)
    ax.set_title("Matched-filter amplitude at best lag")
    ax.set_xlabel("Time in analyzed span (s)")
    ax.set_ylabel("|MF|")

    ax = axes[3]
    phase = np.unwrap(np.angle(series))
    ax.plot(seq_idx * pri_s, phase, lw=1.0)
    if best.doppler_hz is not None:
        ax.set_title(f"Matched-filter phase, Doppler ~ {best.doppler_hz:.3f} Hz")
    else:
        ax.set_title("Matched-filter phase")
    ax.set_xlabel("Time in analyzed span (s)")
    ax.set_ylabel("Phase (rad)")

    fig.suptitle(
        f"{dataset_name} {sequence_label} detection: {best.abs_freq_hz/1e6:.6f} MHz, "
        f"lag={best.lag_us:.1f} us, score={best.score:.2f}"
    )
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    cfg = SEQUENCES[args.sequence]

    reader, resolved_channel, reader_mode = open_drf_like_reader(args.dataset_root, args.channel)
    channels = reader.get_channels()
    if not channels:
        raise RuntimeError("No DigitalRF channels found.")
    if reader_mode != "digital_rf":
        print(f"Using flat Data/rf@*.h5 reader for channel {resolved_channel} under {args.dataset_root}")
    channel = resolved_channel
    if channel not in channels:
        raise RuntimeError(f"Channel {channel!r} not found. Available: {channels}")

    props = reader.get_properties(channel)
    fs = float(props["samples_per_second"])
    dataset_start, dataset_stop = reader.get_bounds(channel)
    start_sample = dataset_start + int(round(args.skip_seconds * fs))
    total_samples = int(round(args.seconds * fs))
    if total_samples <= 0:
        raise RuntimeError("--seconds must be positive.")
    if start_sample + total_samples - 1 > dataset_stop:
        total_samples = dataset_stop - start_sample + 1
    if total_samples <= 0:
        raise RuntimeError("Requested analysis window is outside dataset bounds.")

    center_hz = float(args.center_hz) if args.center_hz is not None else _infer_center_hz(args.dataset_root)
    if center_hz is None:
        raise RuntimeError("Could not infer center frequency from metadata. Supply --center-hz.")

    x, finite_frac = _load_span(reader, channel, start_sample, total_samples)

    freqs, mean_db, candidates = _spectral_candidates(
        x,
        fs=fs,
        center_hz=center_hz,
        pri_hz=1.0 / cfg["pri_s"],
        search_span_hz=args.search_span_hz,
        nfft=args.nfft,
        max_candidates=args.max_candidates,
    )
    if not candidates:
        raise RuntimeError("No spectral candidates found in the requested search span.")

    best_coarse: Candidate | None = None
    best_y = np.array([], dtype=np.complex64)
    best_det: Detection | None = None
    decim = int(round(fs / args.decimated_rate))
    group_delay_raw = (DECIM_FIR_TAPS - 1) // 2
    global_start_dec = start_sample // decim + group_delay_raw // decim

    for cand in candidates:
        y = _mix_decimate(
            x,
            fs_in=fs,
            mix_hz=cand.offset_hz,
            fs_out=args.decimated_rate,
            lp_hz=args.channel_lp_hz,
        )
        if y.size == 0:
            continue
        _, _, det = _match_sequence(
            y,
            fs=args.decimated_rate,
            global_start_sample=global_start_dec,
            pulse_sequence=cfg["pulse_sequence"],
            tau_us=cfg["tau_us"],
            pulse_len_us=cfg["pulse_len_us"],
            pri_s=cfg["pri_s"],
        )
        if best_det is None or det.score > best_det.score:
            best_coarse = cand
            best_y = y
            best_det = det

    if best_coarse is None or best_det is None or best_y.size == 0:
        raise RuntimeError("No candidate produced a matched-filter hit.")

    best_offset, profile, series, best_det = _refine_frequency(
        best_y,
        fs=args.decimated_rate,
        global_start_sample=global_start_dec,
        coarse_offset_hz=best_coarse.offset_hz,
        pulse_sequence=cfg["pulse_sequence"],
        tau_us=cfg["tau_us"],
        pulse_len_us=cfg["pulse_len_us"],
        pri_s=cfg["pri_s"],
        fine_span_hz=args.fine_span_hz,
        fine_step_hz=args.fine_step_hz,
    )
    best_det.offset_hz = float(best_offset)
    best_det.abs_freq_hz = float(center_hz + best_offset)

    prefix = _output_prefix(args)
    png_path = prefix.with_suffix(".png")
    json_path = prefix.with_suffix(".json")

    _plot_results(
        png_path,
        center_hz=center_hz,
        freqs=freqs,
        mean_db=mean_db,
        candidates=candidates,
        best=best_det,
        profile=profile,
        series=series,
        fs_match=args.decimated_rate,
        pri_s=cfg["pri_s"],
        dataset_name=args.dataset_root.name,
        sequence_label=args.sequence,
    )

    start_epoch = _infer_start_epoch(args.dataset_root, start_sample, fs)
    payload = {
        "dataset_root": str(args.dataset_root),
        "channel": channel,
        "analysis_start_sample": int(start_sample),
        "analysis_start_epoch_seconds": float(start_epoch + args.skip_seconds),
        "analysis_seconds": float(total_samples / fs),
        "input_fs_hz": fs,
        "center_hz": center_hz,
        "finite_fraction": finite_frac,
        "sequence": args.sequence,
        "pulse_sequence": cfg["pulse_sequence"],
        "tau_us": cfg["tau_us"],
        "pulse_len_us": cfg["pulse_len_us"],
        "pri_s": cfg["pri_s"],
        "spectral_candidates": [asdict(c) for c in candidates],
        "best_detection": asdict(best_det),
        "output_png": str(png_path),
    }
    json_path.write_text(json.dumps(payload, indent=2))

    print(f"Dataset: {args.dataset_root}")
    print(f"Channel: {channel}")
    print(f"Center frequency: {center_hz/1e6:.6f} MHz")
    print(f"Analyzed span: start_sample={start_sample}, seconds={total_samples/fs:.3f}, finite_fraction={finite_frac:.6f}")
    print(f"Sequence: {args.sequence} pulses={cfg['pulse_sequence']} tau_us={cfg['tau_us']:.1f} pulse_len_us={cfg['pulse_len_us']:.1f}")
    print("Top spectral candidates:")
    for cand in candidates:
        print(
            f"  {cand.abs_freq_hz/1e6:.6f} MHz "
            f"(offset {cand.offset_hz:+.1f} Hz, line_db={cand.line_db:.2f}, mod10={cand.mod10:.4f}, score={cand.score:.4f})"
        )
    print("Best detection:")
    print(
        f"  freq={best_det.abs_freq_hz/1e6:.6f} MHz "
        f"(offset {best_det.offset_hz:+.1f} Hz), "
        f"lag={best_det.lag_us:.1f} us, range~{best_det.one_way_range_km:.1f} km, "
        f"score={best_det.score:.2f}, doppler_hz={best_det.doppler_hz}"
    )
    print(f"Saved plot: {png_path}")
    print(f"Saved summary: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
