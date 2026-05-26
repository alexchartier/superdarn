#!/usr/bin/env python3
"""Detect WWV-style 1 kHz tick energy in raw cf32 recordings.

This is a lightweight adaptation for raw complex float32 files (no DigitalRF metadata).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import numpy as np
from scipy import signal


@dataclass
class Decimated:
    data: np.ndarray
    fs: float
    epoch: datetime


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect WWV 1 kHz tick energy in raw cf32 files.")
    p.add_argument("--raw-cf32", type=Path, required=True, help="Path to raw complex float32 file.")
    p.add_argument("--sample-rate", type=float, required=True, help="Sample rate (Hz).")
    p.add_argument("--center-hz", type=float, required=True, help="Recording center frequency (Hz).")
    p.add_argument("--target-hz", type=float, default=15e6, help="Target carrier to inspect (Hz). Default: 15 MHz.")
    p.add_argument("--decimate", type=int, default=250, help="Decimation factor after mixing. Default: 250 (2.5 MS/s -> 10 kHz).")
    p.add_argument("--chunk-seconds", type=float, default=2.0, help="Seconds per processing chunk. Default: 2.")
    p.add_argument("--overlap-seconds", type=float, default=0.2, help="Chunk overlap (seconds). Default: 0.2.")
    p.add_argument("--max-seconds", type=float, default=None, help="Optional max seconds to process.")
    p.add_argument("--start-epoch", type=str, default=None, help="UTC ISO-8601 start time. Default: file mtime.")
    p.add_argument("--output", type=Path, default=Path("wwv_ticks_cf32.png"), help="Output PNG.")
    return p.parse_args()


def get_epoch(path: Path, start_epoch: str | None) -> datetime:
    if start_epoch:
        ts = start_epoch
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def decimate_stream(
    path: Path,
    fs: float,
    center_hz: float,
    target_hz: float,
    decimate: int,
    chunk_seconds: float,
    overlap_seconds: float,
    max_seconds: float | None,
    epoch: datetime,
) -> Decimated:
    x = np.memmap(path, dtype=np.complex64, mode="r")
    total_samples = int(x.size)
    if max_seconds is not None:
        total_samples = min(total_samples, int(max_seconds * fs))

    chunk_samples = int(round(chunk_seconds * fs))
    overlap_samples = int(round(overlap_seconds * fs))
    if overlap_samples >= chunk_samples:
        raise ValueError("overlap-seconds must be smaller than chunk-seconds")
    step = chunk_samples - overlap_samples
    if step <= 0:
        raise ValueError("chunk-seconds too small for overlap")

    freq_shift = target_hz - center_hz
    two_pi = 2.0 * np.pi

    out: List[np.ndarray] = []
    dec_overlap = int(round(overlap_samples / decimate))

    start = 0
    while start < total_samples:
        stop = min(total_samples, start + chunk_samples)
        xs = np.asarray(x[start:stop], dtype=np.complex64)
        if xs.size == 0:
            break
        t = (start + np.arange(xs.size, dtype=np.float64)) / fs
        mixer = np.exp(-1j * two_pi * freq_shift * t).astype(np.complex64)
        mixed = xs * mixer

        dec = signal.resample_poly(mixed, up=1, down=decimate)
        if out:
            dec = dec[dec_overlap:]
        out.append(dec.astype(np.complex64, copy=False))

        if stop >= total_samples:
            break
        start += step

    y = np.concatenate(out) if out else np.array([], dtype=np.complex64)
    return Decimated(data=y, fs=fs / decimate, epoch=epoch)


def main() -> None:
    args = parse_args()
    raw = args.raw_cf32.expanduser()
    epoch = get_epoch(raw, args.start_epoch)

    dec = decimate_stream(
        path=raw,
        fs=args.sample_rate,
        center_hz=args.center_hz,
        target_hz=args.target_hz,
        decimate=args.decimate,
        chunk_seconds=args.chunk_seconds,
        overlap_seconds=args.overlap_seconds,
        max_seconds=args.max_seconds,
        epoch=epoch,
    )

    if dec.data.size == 0:
        print("No data to process.")
        return

    # STFT on complex baseband to look for 1 kHz AM sidebands.
    f, t, z = signal.stft(
        dec.data,
        fs=dec.fs,
        nperseg=1024,
        noverlap=512,
        detrend=False,
        return_onesided=False,
    )
    f = np.fft.fftshift(f)
    z = np.fft.fftshift(z, axes=0)
    p_db = 20.0 * np.log10(np.abs(z) + 1e-12)

    # Focus on +/- 2 kHz and estimate 1 kHz band energy.
    band_mask = (f >= 900.0) & (f <= 1100.0)
    if not np.any(band_mask):
        print("No 1 kHz band in STFT.")
        return
    band_power = np.nanmean(p_db[band_mask, :], axis=0)

    # Peak detection on band power.
    med = np.median(band_power)
    mad = np.median(np.abs(band_power - med)) + 1e-9
    thresh = med + 6.0 * mad
    peaks, _ = signal.find_peaks(band_power, height=thresh, distance=int(0.8 * dec.fs / 512))

    # Plot.
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except Exception as exc:
        print(f"Plot skipped (matplotlib not available: {exc})")
        return

    # Time axis in UTC
    t0 = epoch
    times = np.array([t0 + np.timedelta64(int(tt * 1e3), "ms") for tt in t])

    fig, ax = plt.subplots(figsize=(11, 6))
    extent = [mdates.date2num(times[0]), mdates.date2num(times[-1]), f[0], f[-1]]
    im = ax.imshow(
        p_db,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap="magma",
    )
    ax.set_title(f"STFT near {args.target_hz/1e6:.3f} MHz (baseband) – {raw.name}")
    ax.set_ylabel("Baseband frequency (Hz)")
    ax.set_xlabel("UTC time")
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.colorbar(im, ax=ax, label="Amplitude (dB)")

    if peaks.size:
        ax.scatter(mdates.date2num(times[peaks]), np.full(peaks.size, 1000.0), color="red", s=10, label="1 kHz energy peaks")
        ax.legend(loc="upper right")

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    print(f"Saved plot: {out}")


if __name__ == "__main__":
    main()
