#!/usr/bin/env python3
"""
Create a pulse-stacked PRI plot for a narrowband SuperDARN recording.

The tool mixes a chosen RF carrier to baseband, lowpasses/decimates,
computes the envelope, then folds it into rows of one PRI.
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


SEQUENCES_MS = {
    "7p": np.array([0.0, 21.6, 28.8, 48.0, 52.8, 62.4, 64.8], dtype=np.float64),
    "8p": np.array([0.0, 21.0, 33.0, 36.0, 40.5, 46.5, 63.0, 64.5], dtype=np.float64),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create a pulse-stacked PRI envelope plot.")
    p.add_argument("--dataset-root", type=Path, required=True, help="DigitalRF dataset root or channel directory.")
    p.add_argument("--channel", default=None, help="Channel name. Default: inferred.")
    p.add_argument("--center-hz", type=float, required=True, help="Dataset center frequency in Hz.")
    p.add_argument("--target-hz", type=float, required=True, help="Carrier to mix to baseband in Hz.")
    p.add_argument("--sequence", choices=sorted(SEQUENCES_MS), default="7p", help="Expected pulse sequence.")
    p.add_argument("--delay-ms", type=float, default=None, help="Arrival delay modulo PRI in ms. Default: auto-search.")
    p.add_argument("--pri-ms", type=float, default=100.0, help="Pulse repetition interval in ms. Default: 100.")
    p.add_argument("--pulse-width-ms", type=float, default=0.3, help="Pulse width in ms for overlay shading. Default: 0.3.")
    p.add_argument("--skip-seconds", type=float, default=0.0, help="Seconds to skip from dataset start. Default: 0.")
    p.add_argument("--seconds", type=float, default=30.0, help="Seconds to analyze. Default: 30.")
    p.add_argument("--channel-lp-hz", type=float, default=12000.0, help="Lowpass cutoff after mixing in Hz. Default: 12 kHz.")
    p.add_argument("--decimated-rate", type=float, default=100000.0, help="Post-filter sample rate in Hz. Default: 100 kHz.")
    p.add_argument("--raw-chunk-seconds", type=float, default=2.0, help="Raw read chunk size in seconds. Default: 2.")
    p.add_argument("--integrate-ms", type=float, default=0.3, help="Envelope integration time in ms. Default: 0.3.")
    p.add_argument("--bin-ms", type=float, default=0.1, help="Horizontal bin size within PRI in ms. Default: 0.1.")
    p.add_argument("--average-pris", type=int, default=1, help="Average this many consecutive PRI rows. Default: 1.")
    p.add_argument("--output-prefix", type=Path, required=True, help="Prefix for PNG and JSON outputs.")
    return p.parse_args()


def _mix_decimate_envelope(
    reader,
    channel: str,
    start_sample: int,
    total_samples: int,
    fs_in: float,
    center_hz: float,
    target_hz: float,
    fs_out: float,
    lp_hz: float,
    raw_chunk_seconds: float,
    integrate_ms: float,
) -> np.ndarray:
    decim = int(round(fs_in / fs_out))
    if not math.isclose(fs_in / fs_out, decim, rel_tol=0.0, abs_tol=1e-9):
        raise RuntimeError("decimated-rate must divide input sample rate exactly.")

    chunk_samples = max(int(round(raw_chunk_seconds * fs_in)), decim)
    taps = signal.firwin(161, lp_hz, fs=fs_in).astype(np.float32)
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
        n = np.arange(chunk.size, dtype=np.float64)
        mixer = np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
        mixed = chunk * mixer
        phase = (phase + phase_step * chunk.size) % (2.0 * math.pi)

        filt, zi = signal.lfilter(taps, [1.0], mixed, zi=zi)
        out = filt[decim_offset::decim]
        decim_offset = (decim_offset - filt.size) % decim
        if out.size:
            env = np.abs(out).astype(np.float32, copy=False)
            if integrate_ms > 0.0:
                width = max(1, int(round(fs_out * integrate_ms * 1e-3)))
                env = np.convolve(env, np.ones(width, dtype=np.float32) / width, mode="same")
            pieces.append(env.astype(np.float32, copy=False))
        cursor += take

    if not pieces:
        return np.array([], dtype=np.float32)
    return np.concatenate(pieces)


def _fold_matrix(env: np.ndarray, fs_env: float, pri_ms: float, bin_ms: float) -> tuple[np.ndarray, np.ndarray]:
    pri_samps = int(round(fs_env * pri_ms * 1e-3))
    bin_samps = int(round(fs_env * bin_ms * 1e-3))
    if pri_samps <= 0 or bin_samps <= 0:
        raise RuntimeError("PRI and bin size must be positive.")
    bins_per_pri = pri_samps // bin_samps
    if bins_per_pri <= 0:
        raise RuntimeError("bin-ms is too large for the PRI.")

    rows = env.size // (bins_per_pri * bin_samps)
    if rows <= 0:
        raise RuntimeError("Not enough envelope samples for one PRI row.")
    trimmed = env[: rows * bins_per_pri * bin_samps]
    mat = trimmed.reshape(rows, bins_per_pri, bin_samps).mean(axis=2)
    x_ms = np.arange(bins_per_pri, dtype=np.float64) * bin_ms
    return mat.astype(np.float32, copy=False), x_ms


def _auto_delay_ms(profile: np.ndarray, x_ms: np.ndarray, pulse_ms: np.ndarray, pulse_width_ms: float) -> float:
    bin_ms = float(x_ms[1] - x_ms[0]) if x_ms.size > 1 else 0.1
    pri_ms = float(x_ms[-1] + bin_ms)
    half_bins = max(1, int(round(0.5 * pulse_width_ms / bin_ms)))
    n = profile.size
    best_idx = 0
    best_score = -np.inf
    for idx in range(n):
        score = 0.0
        for p in pulse_ms:
            center = int(round(((p + idx * bin_ms) % pri_ms) / bin_ms)) % n
            for k in range(-half_bins, half_bins + 1):
                score += float(profile[(center + k) % n])
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx * bin_ms


def _arrival_times_ms(pulse_ms: np.ndarray, delay_ms: float, pri_ms: float) -> np.ndarray:
    return np.mod(pulse_ms + delay_ms, pri_ms)


def _average_rows(matrix: np.ndarray, average_pris: int) -> np.ndarray:
    if average_pris <= 1:
        return matrix
    usable = (matrix.shape[0] // average_pris) * average_pris
    if usable <= 0:
        raise RuntimeError("Not enough PRI rows for the requested averaging.")
    return matrix[:usable].reshape(usable // average_pris, average_pris, matrix.shape[1]).mean(axis=1)


def _make_plot(
    path: Path,
    matrix: np.ndarray,
    x_ms: np.ndarray,
    pri_ms: float,
    arrival_ms: np.ndarray,
    pulse_width_ms: float,
    seconds: float,
    target_hz: float,
    delay_ms: float,
    average_pris: int,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    profile = np.mean(matrix, axis=0)
    row_median = np.median(matrix, axis=1, keepdims=True)
    rel_db = 20.0 * np.log10(np.maximum(matrix, 1e-9) / np.maximum(row_median, 1e-9))

    vmin = float(np.percentile(rel_db, 10))
    vmax = float(np.percentile(rel_db, 99.5))

    fig, (ax_prof, ax_img) = plt.subplots(
        2,
        1,
        figsize=(12, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [1, 5], "hspace": 0.05},
    )

    prof_db = 20.0 * np.log10(np.maximum(profile, 1e-9) / np.maximum(np.median(profile), 1e-9))
    ax_prof.plot(x_ms, prof_db, lw=1.2, color="0.15")
    for t in arrival_ms:
        ax_prof.axvspan(t, t + pulse_width_ms, color="tab:red", alpha=0.12, lw=0)
        ax_prof.axvline(t, color="tab:red", ls="--", lw=0.9, alpha=0.8)
    ax_prof.set_ylabel("Mean env\n(dB rel)")
    ax_prof.grid(True, alpha=0.2)
    ax_prof.set_title(
        f"Pulse stack around {target_hz/1e6:.6f} MHz, delay {delay_ms:.2f} ms, "
        f"span {seconds:.1f} s, avg {average_pris} PRI"
    )

    extent = [0.0, pri_ms, 0, matrix.shape[0]]
    im = ax_img.imshow(
        rel_db,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap="magma",
        vmin=vmin,
        vmax=vmax,
    )
    for t in arrival_ms:
        ax_img.axvspan(t, t + pulse_width_ms, color="cyan", alpha=0.08, lw=0)
        ax_img.axvline(t, color="cyan", ls="--", lw=0.8, alpha=0.7)
    ax_img.set_xlabel("Time within 100 ms PRI (ms)")
    ax_img.set_ylabel("PRI index")
    fig.colorbar(im, ax=ax_img, pad=0.01, label="Envelope / row median (dB)")

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> int:
    args = parse_args()
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

    env = _mix_decimate_envelope(
        reader,
        channel=channel,
        start_sample=start_sample,
        total_samples=total_samples,
        fs_in=fs_in,
        center_hz=args.center_hz,
        target_hz=args.target_hz,
        fs_out=args.decimated_rate,
        lp_hz=args.channel_lp_hz,
        raw_chunk_seconds=args.raw_chunk_seconds,
        integrate_ms=args.integrate_ms,
    )
    if env.size == 0:
        raise RuntimeError("No envelope samples produced.")

    matrix, x_ms = _fold_matrix(env, args.decimated_rate, args.pri_ms, args.bin_ms)
    matrix = _average_rows(matrix, args.average_pris)
    profile = np.mean(matrix, axis=0)
    pulse_ms = SEQUENCES_MS[args.sequence]
    delay_ms = args.delay_ms
    if delay_ms is None:
        delay_ms = _auto_delay_ms(profile, x_ms, pulse_ms, args.pulse_width_ms)
    arrival_ms = _arrival_times_ms(pulse_ms, delay_ms, args.pri_ms)

    png_path = args.output_prefix.with_suffix(".png")
    json_path = args.output_prefix.with_suffix(".json")
    _make_plot(
        png_path,
        matrix=matrix,
        x_ms=x_ms,
        pri_ms=args.pri_ms,
        arrival_ms=arrival_ms,
        pulse_width_ms=args.pulse_width_ms,
        seconds=(total_samples / fs_in),
        target_hz=args.target_hz,
        delay_ms=delay_ms,
        average_pris=args.average_pris,
    )

    result = {
        "dataset_root": str(args.dataset_root),
        "channel": channel,
        "center_hz": float(args.center_hz),
        "target_hz": float(args.target_hz),
        "sequence": args.sequence,
        "pulse_start_ms": pulse_ms.tolist(),
        "delay_ms": float(delay_ms),
        "arrival_ms": arrival_ms.tolist(),
        "pri_ms": float(args.pri_ms),
        "pulse_width_ms": float(args.pulse_width_ms),
        "skip_seconds": float(args.skip_seconds),
        "seconds": float(total_samples / fs_in),
        "channel_lpf_hz": float(args.channel_lp_hz),
        "decimated_rate_hz": float(args.decimated_rate),
        "integrate_ms": float(args.integrate_ms),
        "average_pris": int(args.average_pris),
        "rows": int(matrix.shape[0]),
        "bins_per_pri": int(matrix.shape[1]),
        "reader_mode": reader_mode,
    }
    json_path.write_text(json.dumps(result, indent=2))

    print(f"Saved plot: {png_path}")
    print(f"Saved summary: {json_path}")
    print(f"Delay modulo PRI: {delay_ms:.3f} ms")
    print("Arrival times within PRI (ms): " + ", ".join(f"{t:.3f}" for t in arrival_ms))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
