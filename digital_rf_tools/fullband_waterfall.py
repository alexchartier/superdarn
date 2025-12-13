#!/usr/bin/env python3
"""
Create a waterfall plot from full-band DigitalRF data (e.g., 25 MS/s).

Example:
    python3 fullband_waterfall.py \\
        --dataset-root ~/data/hf_data/itsi_rooftop/2025_06_04_14_19_14 \\
        --center-hz 17.5e6 \\
        --chunk-seconds 1.0 \\
        --step-seconds 1.0 \\
        --nfft 8192 \\
        --freq-span-hz 200e3

The output is a PNG waterfall saved next to the script by default.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import digital_rf as drf
import numpy as np
from scipy import signal


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a waterfall from full-band DigitalRF data.")
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("~/data/hf_data/itsi_rooftop/2025_06_04_14_19_14").expanduser(),
        help="Top-level DigitalRF directory containing the channel (default: provided dataset).",
    )
    p.add_argument("--channel", default="cha", help="Channel name in the DigitalRF dataset (default: cha).")
    p.add_argument(
        "--center-hz",
        type=float,
        default=None,
        help="RF center frequency for labeling (Hz). If omitted, uses drf_properties center_frequency_hz if present.",
    )
    p.add_argument(
        "--chunk-seconds",
        type=float,
        default=1.0,
        help="Seconds per chunk to read and FFT (default: 1 s).",
    )
    p.add_argument(
        "--skip-seconds",
        type=float,
        default=1.0,
        help="Seconds to discard from the start of the capture before plotting (default: 1 s; set 0 to keep all).",
    )
    p.add_argument(
        "--step-seconds",
        type=float,
        default=1.0,
        help="Seconds to advance between chunks (default: 1 s; increase to thin the waterfall).",
    )
    p.add_argument("--nfft", type=int, default=8192, help="FFT length for Welch PSD (default: 8192).")
    p.add_argument(
        "--freq-span-hz",
        type=float,
        default=None,
        help="Optional two-sided span around center (Hz) to crop (e.g., 200e3 keeps ±100 kHz).",
    )
    p.add_argument(
        "--vmin",
        type=float,
        default=None,
        help="Lower limit for color scale (dB). If omitted, autoscale.",
    )
    p.add_argument(
        "--vmax",
        type=float,
        default=None,
        help="Upper limit for color scale (dB). If omitted, autoscale.",
    )
    p.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Limit number of chunks for quicker plots; None = process all in bounds.",
    )
    p.add_argument(
        "--fill-gaps",
        action="store_true",
        default=True,
        help="Insert NaN rows into the waterfall where data is missing between DigitalRF blocks.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output PNG path. If omitted, uses fullband_waterfall_<dataset_basename>.png.",
    )
    return p.parse_args()


def epoch_to_datetime(epoch_str: str) -> datetime:
    if epoch_str.endswith("Z"):
        epoch_str = epoch_str.replace("Z", "+00:00")
    return datetime.fromisoformat(epoch_str).astimezone(timezone.utc)


def fill_center_notch(freqs: np.ndarray, psd_db: np.ndarray, window_bins: int = 1) -> np.ndarray:
    """
    Flatten the DC notch by replacing it with the minimum level seen elsewhere.
    """
    if freqs.size == 0 or psd_db.size != freqs.size:
        return psd_db

    center_idx = int(np.argmin(np.abs(freqs)))
    start = max(0, center_idx - window_bins)
    stop = min(psd_db.size, center_idx + window_bins + 1)

    outside = np.concatenate((psd_db[:start], psd_db[stop:])) if (start > 0 or stop < psd_db.size) else np.array([])
    if outside.size == 0:
        return psd_db

    outside_min = np.nanmin(outside)
    if np.isnan(outside_min):
        return psd_db

    psd_db = psd_db.copy()
    psd_db[start:stop] = outside_min
    return psd_db


def _odd_kernel(max_len: int, preferred: int = 31) -> int:
    if max_len <= 0:
        return 1
    k = min(preferred, max_len)
    if k % 2 == 0:
        k -= 1
    return max(k, 1)


def analyze_regular_spacing(psd_rows: List[np.ndarray], freqs: np.ndarray, row_starts: List[datetime]) -> None:
    if not psd_rows or freqs.size < 2:
        return

    data = np.vstack(psd_rows)
    bin_hz = freqs[1] - freqs[0]

    # Frequency comb check via autocorrelation of line-enhanced median spectrum.
    median_spec = np.nanmedian(data, axis=0)
    k = _odd_kernel(len(median_spec), preferred=31)
    baseline = signal.medfilt(median_spec, kernel_size=k)
    line_enhanced = median_spec - baseline
    line_enhanced = np.nan_to_num(line_enhanced - np.nanmean(line_enhanced))

    corr = np.correlate(line_enhanced, line_enhanced, mode="full")
    lags = np.arange(corr.size) - (line_enhanced.size - 1)
    pos_mask = lags > 0
    corr = corr[pos_mask]
    lags = lags[pos_mask]

    freq_peaks = np.array([], dtype=int)
    if corr.size and np.max(np.abs(corr)) > 0:
        prominence = float(np.max(corr) * 0.05)
        freq_peaks, _ = signal.find_peaks(corr, prominence=prominence)
    freq_spacings_hz = lags[freq_peaks] * bin_hz if freq_peaks.size else np.array([])
    if freq_peaks.size:
        strongest_idx = int(np.argmax(corr[freq_peaks]))
        strongest_spacing_hz = freq_spacings_hz[strongest_idx]
    else:
        strongest_spacing_hz = None

    # Time comb check via autocorrelation of mean row power.
    row_seconds = np.array([(t - row_starts[0]).total_seconds() for t in row_starts], dtype=float)
    if row_seconds.size >= 2:
        step_seconds = float(np.median(np.diff(row_seconds)))
    else:
        step_seconds = None

    time_peaks = np.array([], dtype=int)
    time_spacings = np.array([])
    if step_seconds and step_seconds > 0 and data.shape[0] > 2:
        time_series = np.nanmean(data, axis=1)
        time_series = np.nan_to_num(time_series - np.nanmean(time_series))
        time_corr = np.correlate(time_series, time_series, mode="full")
        time_lags = (np.arange(time_corr.size) - (time_series.size - 1)) * step_seconds
        t_pos_mask = time_lags > 0
        time_corr = time_corr[t_pos_mask]
        time_lags = time_lags[t_pos_mask]
        if time_corr.size and np.max(np.abs(time_corr)) > 0:
            prominence_t = float(np.max(time_corr) * 0.1)
            time_peaks, _ = signal.find_peaks(time_corr, prominence=prominence_t)
        time_spacings = time_lags[time_peaks] if time_peaks.size else np.array([])

    print("Regular-spacing check:")
    print(f"  rows x bins: {data.shape[0]} x {data.shape[1]}, bin width ~{bin_hz:.1f} Hz")
    if freq_spacings_hz.size:
        print(f"  strongest frequency spacing: {strongest_spacing_hz:.1f} Hz")
        print(f"  frequency spacing peaks (Hz, first 10): {freq_spacings_hz[:10]}")
    else:
        print("  frequency spacing peaks: none detected")
    if time_spacings.size:
        print(f"  time spacing peaks (s, first 10): {time_spacings[:10]}")
    else:
        print("  time spacing peaks: none detected")


def make_waterfall(
    psd_rows: List[np.ndarray],
    freqs: np.ndarray,
    row_starts: List[datetime],
    path: Path,
    center_hz: Optional[float],
    dataset_root: Path,
    vmin: Optional[float],
    vmax: Optional[float],
) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore
        import matplotlib.dates as mdates  # type: ignore
        import matplotlib.ticker as mticker  # type: ignore
    except Exception as exc:  # pragma: no cover - optional
        print(f"Plot skipped (matplotlib not available: {exc})")
        return

    if not psd_rows:
        print("Plot skipped (no PSD rows captured).")
        return

    data = np.vstack(psd_rows)
    if center_hz is not None:
        x_axis = (freqs + center_hz) / 1e6  # MHz
        x_label = "Frequency (MHz)"
    else:
        x_axis = freqs / 1e3  # kHz relative
        x_label = "Frequency offset (kHz)"

    y_start = mdates.date2num(row_starts[0])
    y_end = mdates.date2num(row_starts[-1] + (row_starts[-1] - row_starts[0]) / max(len(row_starts), 1))

    fig, (ax_fft, ax_wf) = plt.subplots(
        2,
        1,
        figsize=(12, 7),
        sharex=True,
        gridspec_kw={"height_ratios": [1, 6], "hspace": 0.05},
    )

    finite_rows = np.where(np.isfinite(data).any(axis=1))[0]
    final_row = data[finite_rows[-1]] if finite_rows.size else data[-1]
    if np.isfinite(final_row).any():
        ax_fft.plot(x_axis, final_row, linewidth=1.1)
    ax_fft.set_ylabel("PSD (dB)")
    ax_fft.tick_params(labelbottom=False)
    ax_fft.grid(True, alpha=0.3)

    im = ax_wf.imshow(
        data,
        aspect="auto",
        origin="lower",
        extent=[x_axis[0], x_axis[-1], y_start, y_end],
        cmap="magma",
        vmin=vmin,
        vmax=vmax,
    )
    ax_fft.set_title(f"Full-band waterfall (Welch PSD) – {dataset_root.name}")
    ax_wf.set_xlabel(x_label)
    ax_wf.set_ylabel("UTC start time")
    ax_wf.yaxis_date()
    ax_wf.yaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    locator = ax_wf.xaxis.get_major_locator()
    current_nbins = getattr(locator, "nbins", 5)
    try:
        current_nbins = int(current_nbins)
    except (TypeError, ValueError):
        current_nbins = 5
    ax_wf.xaxis.set_major_locator(mticker.MaxNLocator(nbins=max(3, current_nbins * 3)))
    fig.colorbar(im, ax=[ax_fft, ax_wf], label="PSD (dB)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved waterfall: {path}")


def main() -> None:
    args = parse_args()
    reader = drf.DigitalRFReader(str(args.dataset_root))
    props = reader.get_properties(args.channel)
    fs = float(props["samples_per_second"])
    center_hz = args.center_hz if args.center_hz is not None else props.get("center_frequency_hz", None)
    if center_hz is not None:
        center_hz = float(center_hz)

    dataset_start_sample, stop_sample = reader.get_bounds(args.channel)
    start_sample = dataset_start_sample
    epoch = epoch_to_datetime(props["epoch"])

    chunk_samples = int(round(fs * args.chunk_seconds))
    step_samples = int(round(fs * args.step_seconds))
    skip_seconds = max(args.skip_seconds, 0.0)
    skip_samples = int(round(fs * skip_seconds))
    if skip_samples > 0:
        start_sample = start_sample + skip_samples
        if start_sample > stop_sample:
            available_seconds = max(0.0, (stop_sample - dataset_start_sample + 1) / fs)
            print(
                f"Requested skip of {skip_seconds:.3f} s exceeds available data "
                f"(available {available_seconds:.3f} s)."
            )
            return

    blocks: Dict[int, int] = reader.get_continuous_blocks(start_sample, stop_sample, args.channel)
    if not blocks:
        print("No data blocks found in the specified range.")
        return

    total_available = sum(blocks.values())
    total_span_seconds = (stop_sample - start_sample + 1) / fs
    total_seconds_available = total_available / fs
    est_chunks = max(1, int(total_available // step_samples))
    center_msg = f"{center_hz/1e6:.3f} MHz" if center_hz else "unknown center"
    print(
        f"Input fs={fs/1e6:.3f} MS/s, center={center_msg}"
        f"\nSpan in bounds ~{total_span_seconds:.1f} s, available data ~{total_seconds_available:.1f} s;"
        f" chunk={args.chunk_seconds}s, step={args.step_seconds}s, skip={skip_seconds}s, estimated chunks={est_chunks}"
    )

    psd_rows: List[np.ndarray] = []
    psd_freqs: Optional[np.ndarray] = None
    psd_mask: Optional[np.ndarray] = None
    row_starts: List[datetime] = []
    chunk_count = 0

    prev_block_stop: Optional[int] = None
    block_items = list(blocks.items())

    # Iterate over continuous data blocks to skip gaps cleanly.
    for block_start, block_len in block_items:
        block_stop = block_start + block_len - 1

        # If requested, insert gap rows for missing data between blocks.
        if (
            args.fill_gaps
            and psd_freqs is not None
            and prev_block_stop is not None
            and block_start > prev_block_stop + step_samples
        ):
            gap_cursor = prev_block_stop + step_samples
            while gap_cursor + chunk_samples <= block_start:
                if args.max_chunks is not None and chunk_count >= args.max_chunks:
                    break
                psd_rows.append(np.full_like(psd_freqs, np.nan, dtype=np.float32))
                row_starts.append(epoch + timedelta(seconds=gap_cursor / fs))
                gap_cursor += step_samples
                chunk_count += 1

        cursor = block_start
        while cursor + chunk_samples <= block_stop:
            try:
                data = reader.read_vector_1d(cursor, chunk_samples, args.channel)
            except OSError as exc:
                print(f"Skipping chunk at sample {cursor} (read error: {exc})")
                cursor += step_samples
                continue

            if data.size == 0:
                cursor += step_samples
                continue

            f, pxx = signal.welch(
                data,
                fs=fs,
                nperseg=args.nfft,
                noverlap=args.nfft // 2,
                return_onesided=False,
                detrend=False,
            )
            f = np.fft.fftshift(f)
            pxx = np.fft.fftshift(pxx)

            if psd_freqs is None:
                if args.freq_span_hz is not None:
                    half = args.freq_span_hz / 2.0
                    mask = (f >= -half) & (f <= half)
                else:
                    mask = np.ones_like(f, dtype=bool)
                psd_freqs = f[mask]
                psd_mask = mask
            else:
                if psd_mask is None or psd_mask.shape != f.shape:
                    print("Warning: PSD mask shape mismatch; skipping this chunk to keep dimensions consistent.")
                    cursor += step_samples
                    chunk_count += 1
                    if args.max_chunks is not None and chunk_count >= args.max_chunks:
                        break
                    continue

            pxx_db = 10.0 * np.log10(pxx[psd_mask] + 1e-12).astype(np.float32)
            pxx_db = fill_center_notch(psd_freqs, pxx_db)
            psd_rows.append(pxx_db)
            row_starts.append(epoch + timedelta(seconds=cursor / fs))

            cursor += step_samples
            chunk_count += 1
            if args.max_chunks is not None and chunk_count >= args.max_chunks:
                break
        if args.max_chunks is not None and chunk_count >= args.max_chunks:
            break
        prev_block_stop = block_stop

    if psd_freqs is None or not psd_rows:
        print("No data processed; nothing to plot.")
        return

    if args.output is None:
        default_name = f"fullband_waterfall_{args.dataset_root.name}.png"
        out_path = Path(default_name)
    else:
        out_path = args.output

    analyze_regular_spacing(psd_rows, psd_freqs, row_starts)

    make_waterfall(
        psd_rows=psd_rows,
        freqs=psd_freqs,
        row_starts=row_starts,
        path=out_path,
        center_hz=center_hz,
        dataset_root=args.dataset_root,
        vmin=args.vmin,
        vmax=args.vmax,
    )


if __name__ == "__main__":
    main()
