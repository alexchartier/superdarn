#!/usr/bin/env python3
"""
Band-limit a DigitalRF capture around a fixed SuperDARN carrier and correlate
its envelope against a transmitted pulse sequence on each 0.1 s PRI.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Correlate a fixed-center SuperDARN pulse sequence in DigitalRF.")
    p.add_argument("--dataset-root", type=Path, required=True, help="DigitalRF dataset root.")
    p.add_argument("--channel", default=None, help="Channel name. Default: first channel.")
    p.add_argument("--center-hz", type=float, default=None, help="Recorded center frequency. Default: infer from metadata.")
    p.add_argument("--target-hz", type=float, default=12_000_000.0, help="Carrier to analyze. Default: 12 MHz.")
    p.add_argument("--sequence", choices=sorted(SEQUENCES), default="7p", help="Pulse sequence template. Default: 7p.")
    p.add_argument("--skip-seconds", type=float, default=0.0, help="Skip this many seconds from the start. Default: 0.")
    p.add_argument("--seconds", type=float, default=None, help="Seconds to analyze. Default: full remaining span.")
    p.add_argument("--channel-lp-hz", type=float, default=10_000.0, help="Lowpass cutoff after mixing (Hz). Default: 10 kHz.")
    p.add_argument("--decimated-rate", type=float, default=100_000.0, help="Post-channel sample rate (Hz). Default: 100 kHz.")
    p.add_argument("--raw-chunk-seconds", type=float, default=2.0, help="Raw read chunk size in seconds. Default: 2.")
    p.add_argument("--output-prefix", type=Path, required=True, help="Prefix for PNG and JSON outputs.")
    return p.parse_args()


def infer_center_hz(dataset_root: Path) -> float | None:
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


def infer_start_epoch(dataset_root: Path, start_sample: int, fs_hz: float) -> float:
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
    return float(start_sample) / fs_hz


def load_decimated_channel(
    reader: drf.DigitalRFReader,
    channel: str,
    start_sample: int,
    total_samples: int,
    fs_in: float,
    fs_out: float,
    center_hz: float,
    target_hz: float,
    lp_hz: float,
    raw_chunk_seconds: float,
) -> tuple[np.ndarray, float]:
    decim = int(round(fs_in / fs_out))
    if not math.isclose(fs_in / fs_out, decim, rel_tol=0.0, abs_tol=1e-9):
        raise RuntimeError("decimated-rate must divide input sample rate exactly.")

    chunk_samples = max(int(round(raw_chunk_seconds * fs_in)), decim)
    taps = signal.firwin(DECIM_FIR_TAPS, lp_hz, fs=fs_in).astype(np.float32)
    zi = np.zeros(taps.size - 1, dtype=np.complex64)
    mix_hz = target_hz - center_hz
    phase = 0.0
    phase_step = -2.0 * math.pi * mix_hz / fs_in
    decim_offset = 0
    cursor = start_sample
    stop_sample = start_sample + total_samples
    pieces: list[np.ndarray] = []
    finite_count = 0

    while cursor < stop_sample:
        take = min(chunk_samples, stop_sample - cursor)
        chunk = reader.read_vector_1d(cursor, take, channel).astype(np.complex64, copy=False)
        finite = np.isfinite(chunk.real) & np.isfinite(chunk.imag)
        finite_count += int(np.count_nonzero(finite))
        chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.0, neginf=0.0)

        n = np.arange(chunk.size, dtype=np.float64)
        mixer = np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
        mixed = chunk * mixer
        phase = (phase + phase_step * chunk.size) % (2.0 * math.pi)

        filt, zi = signal.lfilter(taps, [1.0], mixed, zi=zi)
        out = filt[decim_offset::decim]
        decim_offset = (decim_offset - filt.size) % decim
        if out.size:
            pieces.append(out.astype(np.complex64, copy=False))
        cursor += take

    if not pieces:
        return np.array([], dtype=np.complex64), 0.0
    return np.concatenate(pieces), float(finite_count) / max(total_samples, 1)


def compute_correlation(
    y: np.ndarray,
    fs_hz: float,
    start_sample_raw: int,
    fs_in: float,
    pri_s: float,
    pulse_sequence: list[int],
    tau_us: float,
    pulse_len_us: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    pri_samples = int(round(pri_s * fs_hz))
    pulse_samples = int(round(pulse_len_us * 1e-6 * fs_hz))
    offsets = np.round(np.asarray(pulse_sequence, dtype=np.float64) * tau_us * 1e-6 * fs_hz).astype(int)
    template_span = int(offsets[-1] + pulse_samples)
    valid_lags = pri_samples - template_span + 1
    if valid_lags <= 0:
        raise RuntimeError("PRI is shorter than the pulse sequence template.")

    decim = int(round(fs_in / fs_hz))
    global_start_dec = start_sample_raw // decim + ((DECIM_FIR_TAPS - 1) // 2) // decim
    frame_offset = (-global_start_dec) % pri_samples

    usable = y[frame_offset:]
    pri_count = usable.size // pri_samples
    frames = usable[: pri_count * pri_samples].reshape(pri_count, pri_samples)

    env = np.abs(frames).astype(np.float64, copy=False)
    env = np.maximum(env - np.median(env, axis=1, keepdims=True), 0.0)
    cs = np.concatenate([np.zeros((pri_count, 1), dtype=np.float64), np.cumsum(env, axis=1, dtype=np.float64)], axis=1)
    box = cs[:, pulse_samples:] - cs[:, :-pulse_samples]

    corr = np.zeros((pri_count, valid_lags), dtype=np.float32)
    for off in offsets:
        corr += box[:, off : off + valid_lags].astype(np.float32)

    best_lag = int(np.argmax(np.mean(corr, axis=0)))
    return corr, np.argmax(corr, axis=1), corr[:, best_lag], best_lag


def make_plot(
    path: Path,
    corr: np.ndarray,
    per_pri_lag: np.ndarray,
    best_series: np.ndarray,
    best_lag: int,
    fs_hz: float,
    pri_s: float,
    title: str,
) -> None:
    time_s = np.arange(corr.shape[0], dtype=np.float64) * pri_s
    lag_ms = np.arange(corr.shape[1], dtype=np.float64) / fs_hz * 1e3

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), constrained_layout=True)

    ax = axes[0]
    im = ax.imshow(
        corr.T,
        aspect="auto",
        origin="lower",
        extent=[time_s[0], time_s[-1] + pri_s, lag_ms[0], lag_ms[-1]],
        cmap="magma",
    )
    ax.axhline(best_lag / fs_hz * 1e3, color="cyan", ls="--", lw=1.0)
    ax.set_ylabel("Lag within PRI (ms)")
    ax.set_title("Envelope correlation vs time")
    fig.colorbar(im, ax=ax, pad=0.01, label="Correlation")

    ax = axes[1]
    ax.plot(time_s, per_pri_lag / fs_hz * 1e3, lw=0.8)
    ax.axhline(best_lag / fs_hz * 1e3, color="tab:red", ls="--", lw=1.0)
    ax.set_ylabel("Per-PRI peak lag (ms)")
    ax.set_title("Per-PRI best lag")

    ax = axes[2]
    ax.plot(time_s, best_series, lw=0.8)
    ax.set_xlabel("Time in analyzed span (s)")
    ax.set_ylabel("Correlation")
    ax.set_title("Correlation at average best lag")

    fig.suptitle(title)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> int:
    args = parse_args()

    reader, resolved_channel, reader_mode = open_drf_like_reader(args.dataset_root, args.channel)
    channels = reader.get_channels()
    if not channels:
        raise RuntimeError("No channels found in dataset.")
    if reader_mode != "digital_rf":
        print(f"Using flat Data/rf@*.h5 reader for channel {resolved_channel} under {args.dataset_root}")
    channel = resolved_channel
    if channel not in channels:
        raise RuntimeError(f"Channel {channel!r} not found. Available: {channels}")

    fs_in = float(reader.get_properties(channel)["samples_per_second"])
    center_hz = float(args.center_hz) if args.center_hz is not None else infer_center_hz(args.dataset_root)
    if center_hz is None:
        raise RuntimeError("Could not infer center frequency; supply --center-hz.")

    start_sample, stop_sample = reader.get_bounds(channel)
    start_sample += int(round(args.skip_seconds * fs_in))
    if start_sample > stop_sample:
        raise RuntimeError("Skip exceeds dataset length.")

    if args.seconds is None:
        total_samples = stop_sample - start_sample + 1
    else:
        total_samples = int(round(args.seconds * fs_in))
        total_samples = min(total_samples, stop_sample - start_sample + 1)
    if total_samples <= 0:
        raise RuntimeError("No samples left to analyze.")

    y, finite_fraction = load_decimated_channel(
        reader,
        channel=channel,
        start_sample=start_sample,
        total_samples=total_samples,
        fs_in=fs_in,
        fs_out=args.decimated_rate,
        center_hz=center_hz,
        target_hz=args.target_hz,
        lp_hz=args.channel_lp_hz,
        raw_chunk_seconds=args.raw_chunk_seconds,
    )
    if y.size == 0:
        raise RuntimeError("No decimated samples produced.")

    cfg = SEQUENCES[args.sequence]
    corr, per_pri_lag, best_series, best_lag = compute_correlation(
        y,
        fs_hz=args.decimated_rate,
        start_sample_raw=start_sample,
        fs_in=fs_in,
        pri_s=cfg["pri_s"],
        pulse_sequence=cfg["pulse_sequence"],
        tau_us=cfg["tau_us"],
        pulse_len_us=cfg["pulse_len_us"],
    )

    start_epoch = infer_start_epoch(args.dataset_root, start_sample, fs_in)
    pri_phase_ms = (start_epoch % cfg["pri_s"]) * 1e3
    abs_tof_ms = (pri_phase_ms + best_lag / args.decimated_rate * 1e3) % (cfg["pri_s"] * 1e3)
    virtual_range_km = 299_792.458 * (abs_tof_ms * 1e-3) / 2.0

    png_path = args.output_prefix.with_suffix(".png")
    json_path = args.output_prefix.with_suffix(".json")

    title = (
        f"{args.dataset_root.name} {args.sequence}, target {args.target_hz/1e6:.6f} MHz, "
        f"LP {args.channel_lp_hz/1e3:.1f} kHz, best lag {best_lag/args.decimated_rate*1e6:.1f} us, "
        f"absolute TOF {abs_tof_ms:.3f} ms, virtual range {virtual_range_km:.1f} km"
    )
    make_plot(
        png_path,
        corr=corr,
        per_pri_lag=per_pri_lag,
        best_series=best_series,
        best_lag=best_lag,
        fs_hz=args.decimated_rate,
        pri_s=cfg["pri_s"],
        title=title,
    )

    result = {
        "dataset_root": str(args.dataset_root),
        "channel": channel,
        "center_hz": center_hz,
        "target_hz": float(args.target_hz),
        "channel_lpf_hz": float(args.channel_lp_hz),
        "decimated_rate_hz": float(args.decimated_rate),
        "sequence": args.sequence,
        "pulse_sequence": cfg["pulse_sequence"],
        "tau_us": cfg["tau_us"],
        "pulse_len_us": cfg["pulse_len_us"],
        "pri_s": cfg["pri_s"],
        "analysis_start_sample": int(start_sample),
        "analysis_seconds": float(total_samples / fs_in),
        "finite_fraction": finite_fraction,
        "best_lag_samples": int(best_lag),
        "best_lag_us": float(best_lag / args.decimated_rate * 1e6),
        "start_epoch_seconds": float(start_epoch),
        "pri_phase_ms": float(pri_phase_ms),
        "absolute_tof_ms": float(abs_tof_ms),
        "virtual_range_km": float(virtual_range_km),
        "per_pri_lag_ms_median": float(np.median(per_pri_lag / args.decimated_rate * 1e3)),
        "per_pri_lag_ms_std": float(np.std(per_pri_lag / args.decimated_rate * 1e3)),
        "output_png": str(png_path),
    }
    json_path.write_text(json.dumps(result, indent=2))

    print(f"Saved plot: {png_path}")
    print(f"Saved summary: {json_path}")
    print(
        f"Best lag {result['best_lag_us']:.1f} us, absolute TOF {result['absolute_tof_ms']:.3f} ms, "
        f"virtual range {result['virtual_range_km']:.1f} km, lag std {result['per_pri_lag_ms_std']:.3f} ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
