#!/usr/bin/env python3
"""
Create a matched-filter pulse stack for a narrowband SuperDARN recording.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy import signal

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
    p = argparse.ArgumentParser(description="Create a matched-filter PRI stack for SuperDARN.")
    p.add_argument("--dataset-root", type=Path, required=True, help="DigitalRF dataset root or channel directory.")
    p.add_argument("--channel", default=None, help="Channel name. Default: inferred.")
    p.add_argument("--center-hz", type=float, required=True, help="Dataset center frequency in Hz.")
    p.add_argument("--target-hz", type=float, required=True, help="Carrier to mix to baseband in Hz.")
    p.add_argument("--sequence", choices=sorted(SEQUENCES), default="7p", help="Pulse sequence template.")
    p.add_argument("--skip-seconds", type=float, default=0.0, help="Seconds to skip from dataset start.")
    p.add_argument("--seconds", type=float, default=100.0, help="Seconds to analyze.")
    p.add_argument("--channel-lp-hz", type=float, default=5000.0, help="Lowpass cutoff after mixing in Hz.")
    p.add_argument("--decimated-rate", type=float, default=100000.0, help="Post-filter sample rate in Hz.")
    p.add_argument("--raw-chunk-seconds", type=float, default=2.0, help="Raw read chunk size in seconds.")
    p.add_argument("--residual-center-hz", type=float, default=0.0, help="Center residual frequency search around baseband in Hz.")
    p.add_argument("--residual-span-hz", type=float, default=30.0, help="Residual frequency half-span in Hz.")
    p.add_argument("--residual-step-hz", type=float, default=1.0, help="Residual frequency step in Hz.")
    p.add_argument("--residual-search-seconds", type=float, default=20.0, help="Seconds to use for residual frequency search.")
    p.add_argument("--lag-center-ms", type=float, default=None, help="If set, center the matched-filter stack on this lag in ms instead of auto-picking.")
    p.add_argument("--lag-span-ms", type=float, default=4.0, help="Total lag span to plot around best lag in ms.")
    p.add_argument("--average-pris", type=int, default=16, help="Average this many consecutive PRI rows.")
    p.add_argument("--output-prefix", type=Path, required=True, help="Prefix for PNG and JSON outputs.")
    return p.parse_args()


def load_decimated_channel(
    reader,
    channel: str,
    start_sample: int,
    total_samples: int,
    fs_in: float,
    fs_out: float,
    center_hz: float,
    target_hz: float,
    lp_hz: float,
    raw_chunk_seconds: float,
) -> np.ndarray:
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

    while cursor < stop_sample:
        take = min(chunk_samples, stop_sample - cursor)
        chunk = reader.read_vector_1d(cursor, take, channel).astype(np.complex64, copy=False)
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
        return np.array([], dtype=np.complex64)
    return np.concatenate(pieces)


def frame_pris(
    y: np.ndarray,
    fs_hz: float,
    start_sample_raw: int,
    fs_in: float,
    pri_s: float,
) -> tuple[np.ndarray, int]:
    pri_samples = int(round(pri_s * fs_hz))
    decim = int(round(fs_in / fs_hz))
    global_start_dec = start_sample_raw // decim + ((DECIM_FIR_TAPS - 1) // 2) // decim
    frame_offset = (-global_start_dec) % pri_samples
    usable = y[frame_offset:]
    pri_count = usable.size // pri_samples
    frames = usable[: pri_count * pri_samples].reshape(pri_count, pri_samples)
    return frames, frame_offset


def envelope_best_lag(
    frames: np.ndarray,
    fs_hz: float,
    pulse_sequence: list[int],
    tau_us: float,
    pulse_len_us: float,
) -> tuple[np.ndarray, int]:
    pri_samples = frames.shape[1]
    pulse_samples = int(round(pulse_len_us * 1e-6 * fs_hz))
    offsets = np.round(np.asarray(pulse_sequence, dtype=np.float64) * tau_us * 1e-6 * fs_hz).astype(int)
    template_span = int(offsets[-1] + pulse_samples)
    valid_lags = pri_samples - template_span + 1
    if valid_lags <= 0:
        raise RuntimeError("PRI is shorter than the pulse sequence template.")

    env = np.abs(frames).astype(np.float32, copy=False)
    env = np.maximum(env - np.median(env, axis=1, keepdims=True), 0.0)
    cs = np.concatenate(
        [np.zeros((env.shape[0], 1), dtype=np.float32), np.cumsum(env, axis=1, dtype=np.float32)],
        axis=1,
    )
    box = cs[:, pulse_samples:] - cs[:, :-pulse_samples]
    corr = np.zeros((env.shape[0], valid_lags), dtype=np.float32)
    for off in offsets:
        corr += box[:, off : off + valid_lags]
    profile = corr.mean(axis=0)
    best_lag = int(np.argmax(profile))
    return profile, best_lag


def residual_search_hz(
    frames: np.ndarray,
    fs_hz: float,
    pulse_sequence: list[int],
    tau_us: float,
    pulse_len_us: float,
    best_lag: int,
    center_hz: float,
    span_hz: float,
    step_hz: float,
) -> tuple[float, float]:
    if step_hz <= 0.0:
        raise RuntimeError("residual-step-hz must be positive.")

    pulse_samples = int(round(pulse_len_us * 1e-6 * fs_hz))
    offsets = np.round(np.asarray(pulse_sequence, dtype=np.float64) * tau_us * 1e-6 * fs_hz).astype(int)
    t = np.arange(frames.shape[1], dtype=np.float64) / fs_hz
    residuals = np.arange(center_hz - span_hz, center_hz + span_hz + 0.5 * step_hz, step_hz, dtype=np.float64)

    best_residual = float(center_hz)
    best_score = -np.inf
    for residual_hz in residuals:
        phase = np.exp(-2j * np.pi * residual_hz * t).astype(np.complex64)
        mixed = frames * phase[None, :]
        cs = np.concatenate(
            [np.zeros((mixed.shape[0], 1), dtype=np.complex64), np.cumsum(mixed, axis=1, dtype=np.complex64)],
            axis=1,
        )
        series = np.zeros(mixed.shape[0], dtype=np.complex64)
        for off in offsets:
            lo = best_lag + off
            hi = lo + pulse_samples
            series += cs[:, hi] - cs[:, lo]
        score = float(np.median(np.abs(series)))
        if score > best_score:
            best_score = score
            best_residual = float(residual_hz)
    return best_residual, best_score


def matched_filter_stack(
    frames: np.ndarray,
    fs_hz: float,
    pulse_sequence: list[int],
    tau_us: float,
    pulse_len_us: float,
    residual_hz: float,
    lag_start: int,
    lag_stop: int,
) -> np.ndarray:
    pulse_samples = int(round(pulse_len_us * 1e-6 * fs_hz))
    offsets = np.round(np.asarray(pulse_sequence, dtype=np.float64) * tau_us * 1e-6 * fs_hz).astype(int)
    t = np.arange(frames.shape[1], dtype=np.float64) / fs_hz
    phase = np.exp(-2j * np.pi * residual_hz * t).astype(np.complex64)
    mixed = frames * phase[None, :]
    cs = np.concatenate(
        [np.zeros((mixed.shape[0], 1), dtype=np.complex64), np.cumsum(mixed, axis=1, dtype=np.complex64)],
        axis=1,
    )

    lags = np.arange(lag_start, lag_stop, dtype=int)
    corr = np.zeros((mixed.shape[0], lags.size), dtype=np.complex64)
    for i, lag in enumerate(lags):
        series = np.zeros(mixed.shape[0], dtype=np.complex64)
        for off in offsets:
            lo = lag + off
            hi = lo + pulse_samples
            series += cs[:, hi] - cs[:, lo]
        corr[:, i] = series
    return corr


def average_rows(matrix: np.ndarray, average_pris: int) -> np.ndarray:
    if average_pris <= 1:
        return matrix
    usable = (matrix.shape[0] // average_pris) * average_pris
    if usable <= 0:
        raise RuntimeError("Not enough PRI rows for the requested averaging.")
    return matrix[:usable].reshape(usable // average_pris, average_pris, matrix.shape[1]).mean(axis=1)


def make_plot(
    path: Path,
    power: np.ndarray,
    lag_ms: np.ndarray,
    best_lag_ms: float,
    residual_hz: float,
    target_hz: float,
    avg_pris: int,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    row_median = np.median(power, axis=1, keepdims=True)
    rel_db = 10.0 * np.log10(np.maximum(power, 1e-12) / np.maximum(row_median, 1e-12))
    profile_db = 10.0 * np.log10(np.maximum(power.mean(axis=0), 1e-12) / np.maximum(np.median(power.mean(axis=0)), 1e-12))

    vmin = float(np.percentile(rel_db, 10))
    vmax = float(np.percentile(rel_db, 99.5))

    fig, (ax_prof, ax_img) = plt.subplots(
        2,
        1,
        figsize=(12, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [1, 5], "hspace": 0.05},
    )

    ax_prof.plot(lag_ms, profile_db, lw=1.2, color="0.15")
    ax_prof.axvline(best_lag_ms, color="tab:red", ls="--", lw=1.0)
    ax_prof.set_ylabel("Mean MF\n(dB rel)")
    ax_prof.grid(True, alpha=0.2)
    ax_prof.set_title(
        f"Matched-filter stack around {target_hz/1e6:.6f} MHz, residual {residual_hz:+.1f} Hz, avg {avg_pris} PRI"
    )

    extent = [float(lag_ms[0]), float(lag_ms[-1]), 0, power.shape[0]]
    im = ax_img.imshow(
        rel_db,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap="magma",
        vmin=vmin,
        vmax=vmax,
    )
    ax_img.axvline(best_lag_ms, color="cyan", ls="--", lw=1.0)
    ax_img.set_xlabel("Lag within PRI (ms)")
    ax_img.set_ylabel("PRI group index")
    fig.colorbar(im, ax=ax_img, pad=0.01, label="Matched-filter power / row median (dB)")

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    cfg = SEQUENCES[args.sequence]

    reader, channel, reader_mode = open_drf_like_reader(args.dataset_root, args.channel)
    if reader_mode != "digital_rf":
        print(f"Using flat Data/rf@*.h5 reader for channel {channel} under {args.dataset_root}")

    props = reader.get_properties(channel)
    fs_in = float(props["samples_per_second"])
    start_sample, stop_sample = reader.get_bounds(channel)
    start_sample += int(round(args.skip_seconds * fs_in))
    if start_sample > stop_sample:
        raise RuntimeError("Skip exceeds dataset length.")

    total_samples = int(round(args.seconds * fs_in))
    total_samples = min(total_samples, stop_sample - start_sample + 1)
    if total_samples <= 0:
        raise RuntimeError("No samples left to analyze.")

    y = load_decimated_channel(
        reader,
        channel=channel,
        start_sample=start_sample,
        total_samples=total_samples,
        fs_in=fs_in,
        fs_out=args.decimated_rate,
        center_hz=args.center_hz,
        target_hz=args.target_hz,
        lp_hz=args.channel_lp_hz,
        raw_chunk_seconds=args.raw_chunk_seconds,
    )
    if y.size == 0:
        raise RuntimeError("No decimated samples produced.")

    frames, frame_offset = frame_pris(y, args.decimated_rate, start_sample, fs_in, cfg["pri_s"])
    profile, best_lag_auto = envelope_best_lag(
        frames,
        fs_hz=args.decimated_rate,
        pulse_sequence=cfg["pulse_sequence"],
        tau_us=cfg["tau_us"],
        pulse_len_us=cfg["pulse_len_us"],
    )
    if args.lag_center_ms is not None:
        best_lag = int(round(args.lag_center_ms * 1e-3 * args.decimated_rate))
        best_lag = max(0, min(best_lag, profile.size - 1))
    else:
        best_lag = best_lag_auto

    search_rows = min(frames.shape[0], int(round(args.residual_search_seconds / cfg["pri_s"])))
    residual_hz, residual_score = residual_search_hz(
        frames[:search_rows],
        fs_hz=args.decimated_rate,
        pulse_sequence=cfg["pulse_sequence"],
        tau_us=cfg["tau_us"],
        pulse_len_us=cfg["pulse_len_us"],
        best_lag=best_lag,
        center_hz=args.residual_center_hz,
        span_hz=args.residual_span_hz,
        step_hz=args.residual_step_hz,
    )

    half_span_samples = max(1, int(round(0.5 * args.lag_span_ms * 1e-3 * args.decimated_rate)))
    valid_lags = profile.size
    lag_start = max(0, best_lag - half_span_samples)
    lag_stop = min(valid_lags, best_lag + half_span_samples + 1)

    corr = matched_filter_stack(
        frames,
        fs_hz=args.decimated_rate,
        pulse_sequence=cfg["pulse_sequence"],
        tau_us=cfg["tau_us"],
        pulse_len_us=cfg["pulse_len_us"],
        residual_hz=residual_hz,
        lag_start=lag_start,
        lag_stop=lag_stop,
    )
    power = np.abs(corr).astype(np.float32) ** 2
    power = average_rows(power, args.average_pris)

    lag_ms = np.arange(lag_start, lag_stop, dtype=np.float64) * 1e3 / args.decimated_rate
    best_lag_ms = best_lag * 1e3 / args.decimated_rate

    png_path = args.output_prefix.with_suffix(".png")
    json_path = args.output_prefix.with_suffix(".json")
    make_plot(
        png_path,
        power=power,
        lag_ms=lag_ms,
        best_lag_ms=best_lag_ms,
        residual_hz=residual_hz,
        target_hz=args.target_hz,
        avg_pris=args.average_pris,
    )

    result = {
        "dataset_root": str(args.dataset_root),
        "channel": channel,
        "center_hz": float(args.center_hz),
        "target_hz": float(args.target_hz),
        "sequence": args.sequence,
        "tau_us": float(cfg["tau_us"]),
        "pulse_len_us": float(cfg["pulse_len_us"]),
        "pri_s": float(cfg["pri_s"]),
        "skip_seconds": float(args.skip_seconds),
        "seconds": float(total_samples / fs_in),
        "channel_lpf_hz": float(args.channel_lp_hz),
        "decimated_rate_hz": float(args.decimated_rate),
        "envelope_best_lag_ms": float(best_lag_auto * 1e3 / args.decimated_rate),
        "best_lag_ms": float(best_lag_ms),
        "residual_hz": float(residual_hz),
        "residual_search_score": float(residual_score),
        "lag_window_ms": [float(lag_ms[0]), float(lag_ms[-1])],
        "average_pris": int(args.average_pris),
        "pri_groups": int(power.shape[0]),
        "frame_offset_samples": int(frame_offset),
        "reader_mode": reader_mode,
    }
    json_path.write_text(json.dumps(result, indent=2))

    print(f"Saved plot: {png_path}")
    print(f"Saved summary: {json_path}")
    print(f"Best lag: {best_lag_ms:.3f} ms")
    print(f"Best residual: {residual_hz:+.2f} Hz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
