#!/usr/bin/env python3
"""
Match filter WWV 10 MHz tick markers (5 cycles of 1 kHz) in a 100 kS/s DigitalRF dataset.

Assumes the data have already been downmixed/decimated to 100 kS/s and are centered on 10 MHz
as produced by integrate_and_decimate.py.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple, Optional

import digital_rf as drf
import numpy as np
from scipy import signal
from tqdm import tqdm


DEFAULT_ROOT = Path("/Users/chartat1/data/hf_data/itsi_rooftop/2025_06_04_14_19_14_10mhz_100ksps")
DEFAULT_CHANNEL = "cha"
DEFAULT_FS = 100_000.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Match filter WWV 1 kHz tick markers in 100 kS/s DigitalRF data.")
    p.add_argument("--dataset-root", type=Path, default=DEFAULT_ROOT, help="DigitalRF root containing the channel.")
    p.add_argument("--channel", default=DEFAULT_CHANNEL, help="Channel name to read (default: cha).")
    p.add_argument("--tone-hz", type=float, default=1000.0, help="Tone frequency to match (Hz).")
    p.add_argument("--cycles", type=int, default=5, help="Number of cycles in the tick (default: 5).")
    p.add_argument("--chunk-seconds", type=float, default=2.0, help="Seconds per processing chunk.")
    p.add_argument("--sigma-threshold", type=float, default=6.0, help="Peak threshold = sigma_threshold * robust_sigma.")
    p.add_argument("--max-hits", type=int, default=50, help="Print top N hits across the file set.")
    p.add_argument("--no-bandpass", action="store_true", help="Disable 1 kHz bandpass on the envelope.")
    p.add_argument("--no-plot", action="store_true", help="Skip generating a plot of detected ticks.")
    p.add_argument("--plot-file", type=Path, default=Path("tick_hits.png"), help="Where to save the tick plot.")
    p.add_argument("--no-waterfall", action="store_true", help="Skip generating a waterfall of the raw signal.")
    p.add_argument(
        "--waterfall-file",
        type=Path,
        default=Path("tick_waterfall.png"),
        help="Where to save the raw-signal waterfall image.",
    )
    p.add_argument("--waterfall-nfft", type=int, default=2048, help="FFT length for the raw waterfall (Welch PSD).")
    p.add_argument("--stop-after-chunks", type=int, default=None, help="Limit chunks for a quick smoke test.")
    return p.parse_args()


def make_template(fs: float, tone_hz: float, cycles: int) -> np.ndarray:
    samples = int(round(cycles * fs / tone_hz))
    t = np.arange(samples, dtype=np.float64) / fs
    tone = np.sin(2.0 * np.pi * tone_hz * t)
    window = signal.windows.hann(samples)
    tpl = tone * window
    tpl = tpl - tpl.mean()
    tpl = tpl / np.sqrt(np.sum(tpl**2))
    return tpl.astype(np.float32)


def bandpass_1k(fs: float) -> np.ndarray:
    return signal.butter(4, [600.0, 1400.0], btype="band", fs=fs, output="sos")


def robust_sigma(x: np.ndarray) -> float:
    return float(np.median(np.abs(x)) / 0.6745 + 1e-12)


def epoch_to_datetime(epoch_str: str) -> datetime:
    if epoch_str.endswith("Z"):
        epoch_str = epoch_str.replace("Z", "+00:00")
    return datetime.fromisoformat(epoch_str).astimezone(timezone.utc)


def make_plot(
    hits: List[Tuple[float, int]],
    fs: float,
    epoch: datetime,
    threshold: float,
    path: Path,
    span: Tuple[datetime, datetime],
) -> Optional[Path]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # pragma: no cover - optional
        print(f"Plotting skipped (matplotlib not available: {exc})")
        return None

    if not hits:
        print("Plotting skipped (no hits).")
        return None

    scores = np.array([h[0] for h in hits], dtype=np.float32)
    times = [epoch + timedelta(seconds=h[1] / fs) for h in hits]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.stem(times, scores, basefmt=" ", linefmt="C0-", markerfmt="C0o")
    ax.axhline(threshold, color="red", linestyle="--", linewidth=1, label="threshold")
    ax.set_title("WWV 1 kHz tick detections")
    ax.set_ylabel("Matched filter score")
    ax.set_xlabel("UTC time")
    ax.legend(loc="upper right")
    ax.set_xlim(span[0], span[1])
    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved plot: {path}")
    return path


def make_waterfall(
    psd_rows: List[np.ndarray],
    freqs: np.ndarray,
    row_starts: List[datetime],
    chunk_seconds: float,
    path: Path,
    center_hz: float,
) -> Optional[Path]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
        import matplotlib.dates as mdates  # type: ignore
    except Exception as exc:  # pragma: no cover - optional
        print(f"Waterfall skipped (matplotlib not available: {exc})")
        return None

    if not psd_rows:
        print("Waterfall skipped (no PSD rows captured).")
        return None

    data = np.vstack(psd_rows)

    y_start = mdates.date2num(row_starts[0])
    y_end = mdates.date2num(row_starts[-1] + timedelta(seconds=chunk_seconds))

    fig, ax = plt.subplots(figsize=(10, 6))
    freq_mhz = (freqs + center_hz) / 1e6

    im = ax.imshow(
        data,
        aspect="auto",
        origin="lower",
        extent=[freq_mhz[0], freq_mhz[-1], y_start, y_end],
        cmap="magma",
    )
    ax.set_title("Raw signal waterfall (Welch PSD, cropped to 80% BW)")
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("UTC start time")
    ax.yaxis_date()
    ax.yaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.colorbar(im, ax=ax, label="PSD (dB)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved waterfall: {path}")
    return path


def main() -> None:
    args = parse_args()
    reader = drf.DigitalRFReader(str(args.dataset_root))
    props = reader.get_properties(args.channel)
    fs = float(props["samples_per_second"])
    center_hz = float(props.get("center_frequency_hz", 10_000_000.0))
    epoch = epoch_to_datetime(props["epoch"])
    bounds = reader.get_bounds(args.channel)
    start_sample, stop_sample = bounds[0], bounds[1]
    span = (
        epoch + timedelta(seconds=start_sample / fs),
        epoch + timedelta(seconds=stop_sample / fs),
    )

    tpl = make_template(fs, args.tone_hz, args.cycles)
    tpl_len = tpl.shape[0]

    chunk_samples = int(round(fs * args.chunk_seconds))
    overlap = tpl_len - 1
    step = max(1, chunk_samples - overlap)
    sos = None if args.no_bandpass else bandpass_1k(fs)

    hits: List[Tuple[float, int]] = []
    cursor = start_sample
    chunk_count = 0
    total_chunks = int((stop_sample - start_sample) / step) + 1
    psd_rows: List[np.ndarray] = []
    psd_freqs: Optional[np.ndarray] = None
    psd_mask: Optional[np.ndarray] = None
    psd_row_starts: List[datetime] = []

    for _ in tqdm(range(total_chunks), desc="Scanning"):
        if cursor > stop_sample:
            break
        chunk_start = cursor
        chunk_len = min(chunk_samples, stop_sample - chunk_start + 1)
        data = reader.read_vector_1d(cursor, chunk_len, args.channel)
        if data.size == 0:
            cursor += step
            continue

        env = np.abs(data).astype(np.float32)
        env = env - np.mean(env)
        if sos is not None:
            env = signal.sosfiltfilt(sos, env)

        corr = signal.correlate(env, tpl, mode="valid")
        sigma = robust_sigma(corr)
        thresh = args.sigma_threshold * sigma
        peaks, props_pk = signal.find_peaks(corr, height=thresh, distance=tpl_len // 2)

        for p, h in zip(peaks, props_pk["peak_heights"]):
            global_sample = cursor + int(p)
            hits.append((float(h), global_sample))

        if chunk_len == chunk_samples:
            f, pxx = signal.welch(
                data,
                fs=fs,
                nperseg=args.waterfall_nfft,
                noverlap=args.waterfall_nfft // 2,
                return_onesided=False,
                detrend=False,
            )
            f = np.fft.fftshift(f)
            pxx = np.fft.fftshift(pxx)
            if psd_mask is None:
                bw_crop_hz = 0.8 * fs / 2.0
                psd_mask = (f >= -bw_crop_hz) & (f <= bw_crop_hz)
                psd_freqs = f[psd_mask]
            pxx_db = 10.0 * np.log10(pxx[psd_mask] + 1e-12).astype(np.float32)
            psd_rows.append(pxx_db)
            psd_row_starts.append(epoch + timedelta(seconds=chunk_start / fs))

        cursor += step
        chunk_count += 1
        if args.stop_after_chunks is not None and chunk_count >= args.stop_after_chunks:
            break

    hits.sort(key=lambda x: x[0], reverse=True)
    print(f"\nTop {min(len(hits), args.max_hits)} hits (threshold={args.sigma_threshold} * robust sigma):")
    for score, sample in hits[: args.max_hits]:
        t = epoch + timedelta(seconds=sample / fs)
        print(f"{t.isoformat()}Z  sample={sample}  score={score:.3f}")

    if not args.no_plot and hits:
        scores_all = np.array([h[0] for h in hits], dtype=np.float64)
        sigma_all = robust_sigma(scores_all)
        plot_thresh = args.sigma_threshold * sigma_all
        make_plot(hits, fs, epoch, threshold=plot_thresh, path=args.plot_file, span=span)

    if not args.no_waterfall and psd_rows and psd_freqs is not None:
        make_waterfall(
            psd_rows=psd_rows,
            freqs=psd_freqs,
            row_starts=psd_row_starts,
            chunk_seconds=args.chunk_seconds,
            path=args.waterfall_file,
            center_hz=center_hz,
        )


if __name__ == "__main__":
    main()
