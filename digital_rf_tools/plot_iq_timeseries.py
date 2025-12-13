#!/usr/bin/env python3
"""
Plot a representative I/Q time series from a DigitalRF dataset.

Defaults target: ~/data/hf_data/itsi_rooftop/2025_06_04_14_19_14, channel "cha".
The y-axis is scaled to the full bit depth (if integer) so you can see clipping headroom.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Tuple

import digital_rf as drf
import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot a representative I/Q time series from DigitalRF data.")
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("~/data/hf_data/itsi_rooftop/2025_06_04_14_19_14").expanduser(),
        help="Top-level DigitalRF directory.",
    )
    p.add_argument("--channel", default="cha", help="Channel name (default: cha).")
    p.add_argument(
        "--duration-seconds",
        type=float,
        default=0.01,
        help="Length of time series to plot (seconds). Default: 10 ms.",
    )
    p.add_argument(
        "--offset-seconds",
        type=float,
        default=0.0,
        help="Offset from the start of available data (seconds). Default: 0 s.",
    )
    p.add_argument(
        "--center-hz",
        type=float,
        default=None,
        help="Override center frequency used in the plot title. If omitted, uses drf_properties center_frequency_hz.",
    )
    p.add_argument(
        "--fullscale-bits",
        type=int,
        default=12,
        help="Assumed ADC bit depth for dBFS conversion (default: 12 bits => FS=2048).",
    )
    p.add_argument(
        "--mode",
        choices=["raw", "dbfs"],
        default="dbfs",
        help="Plot mode: raw sample values or dBFS. Default: dbfs.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("iq_timeseries.png"),
        help="Output PNG path. Default: iq_timeseries.png",
    )
    return p.parse_args()


def dtype_limits(arr: np.ndarray) -> Tuple[float, float]:
    """Return symmetric limits covering full bit depth if integer, else data min/max."""
    if np.issubdtype(arr.dtype, np.integer):
        info = np.iinfo(arr.dtype)
        max_abs = max(abs(info.min), abs(info.max))
        return -max_abs, max_abs
    else:
        finite = np.isfinite(arr)
        if not finite.any():
            return -1.0, 1.0
        data = arr[finite]
        lo, hi = float(data.min()), float(data.max())
        span = max(abs(lo), abs(hi))
        return -span, span


def main() -> None:
    args = parse_args()
    reader = drf.DigitalRFReader(str(args.dataset_root))
    props = reader.get_properties(args.channel)
    fs = float(props["samples_per_second"])
    bounds = reader.get_bounds(args.channel)
    start_sample = bounds[0] + int(round(args.offset_seconds * fs))
    nsamp = int(round(args.duration_seconds * fs))
    stop_sample = bounds[1]
    if start_sample + nsamp > stop_sample:
        nsamp = max(1, stop_sample - start_sample)
        print(f"Truncated duration to {nsamp/fs:.6f} s to fit in available data.")

    data = reader.read_vector_1d(start_sample, nsamp, args.channel)
    breakpoint()
    if data.size == 0:
        print("No data read; nothing to plot.")
        return

    # Pull I/Q components
    i = np.real(data)
    q = np.imag(data)
    t = np.arange(nsamp, dtype=np.float64) / fs

    if args.mode == "dbfs":
        fs_counts = float(2 ** (args.fullscale_bits - 1))
        eps = 1e-12
        i_plot = 20.0 * np.log10(np.abs(i) / fs_counts + eps)
        q_plot = 20.0 * np.log10(np.abs(q) / fs_counts + eps)
        ylo, yhi = -120.0, 0.0
        y_label = "Amplitude (dBFS)"
    else:
        fs_counts = float(2 ** (args.fullscale_bits - 1))
        i_plot = i
        q_plot = q
        ylo, yhi = -fs_counts, fs_counts
        y_label = f"Amplitude (counts, ±{int(fs_counts)})"

    # Decide center frequency for labeling
    if args.center_hz is not None:
        center_hz = float(args.center_hz)
    else:
        cf = props.get("center_frequency_hz", None)
        center_hz = float(cf) if cf is not None else None

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # pragma: no cover - optional
        print(f"Plot skipped (matplotlib not available: {exc})")
        return

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t * 1e3, i_plot, label=f"I ({args.mode})")
    ax.plot(t * 1e3, q_plot, label=f"Q ({args.mode})")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel(y_label)
    ax.set_ylim([ylo, yhi])
    title_cf = f"{center_hz/1e6:.3f} MHz" if center_hz is not None else ""
    ax.set_title(f"I/Q time series – {args.dataset_root.name} – {title_cf}")
    ax.grid(True, which="both", axis="both", linestyle=":", linewidth=0.5)
    ax.legend()
    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output)
    plt.close(fig)
    print(f"Saved {args.output} (start sample {start_sample}, {nsamp} samples @ {fs/1e6:.3f} MS/s)")


if __name__ == "__main__":
    main()
