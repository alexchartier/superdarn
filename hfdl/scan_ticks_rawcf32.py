#!/usr/bin/env python3
"""Scan raw cf32 channels for WWV/CHU tick periodicity."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
from scipy import signal


@dataclass
class TickResult:
    channel: str
    target_hz: float
    peaks: int
    median_dt: float | None
    frac_near_1s: float | None


def iter_decimated(
    x: np.memmap,
    fs: float,
    center_hz: float,
    target_hz: float,
    decimate: int,
    chunk_seconds: float,
    overlap_seconds: float,
    max_seconds: float | None,
) -> Iterable[np.ndarray]:
    total_samples = int(x.size)
    if max_seconds is not None:
        total_samples = min(total_samples, int(max_seconds * fs))

    chunk_samples = int(round(chunk_seconds * fs))
    overlap_samples = int(round(overlap_seconds * fs))
    if overlap_samples >= chunk_samples:
        raise ValueError("overlap_seconds must be smaller than chunk_seconds")
    step = chunk_samples - overlap_samples

    freq_shift = target_hz - center_hz
    two_pi = 2.0 * math.pi

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
        if start > 0:
            dec = dec[dec_overlap:]
        yield dec.astype(np.complex64, copy=False)
        if stop >= total_samples:
            break
        start += step


def detect_ticks(
    path: Path,
    fs: float,
    center_hz: float,
    target_hz: float,
    max_seconds: float = 40.0,
) -> TickResult:
    x = np.memmap(path, dtype=np.complex64, mode="r")
    decimate = 250  # 2.5 MS/s -> 10 kS/s
    fsd = fs / decimate

    # Bandpass around 1 kHz on the AM envelope.
    sos = signal.butter(4, [900.0, 1100.0], btype="bandpass", fs=fsd, output="sos")
    zi = signal.sosfilt_zi(sos) * 0.0

    # accumulate 0.1 s RMS bins
    bin_hz = 10.0
    bin_samples = int(round(fsd / bin_hz))
    bins: List[float] = []

    for dec in iter_decimated(
        x,
        fs=fs,
        center_hz=center_hz,
        target_hz=target_hz,
        decimate=decimate,
        chunk_seconds=2.0,
        overlap_seconds=0.2,
        max_seconds=max_seconds,
    ):
        if dec.size == 0:
            continue
        env = np.abs(dec).astype(np.float32, copy=False)
        filt, zi = signal.sosfilt(sos, env, zi=zi)
        # RMS in 0.1 s bins
        n = (filt.size // bin_samples) * bin_samples
        if n <= 0:
            continue
        f2 = filt[:n].reshape(-1, bin_samples)
        rms = np.sqrt(np.mean(f2 * f2, axis=1))
        bins.extend(rms.tolist())

    if not bins:
        return TickResult(path.parent.name, target_hz, 0, None, None)

    series = np.array(bins, dtype=np.float32)
    med = float(np.median(series))
    mad = float(np.median(np.abs(series - med))) + 1e-12
    thresh = med + 6.0 * mad

    min_dist = int(round(0.8 * bin_hz))
    peaks, props = signal.find_peaks(series, height=thresh, distance=min_dist)
    if peaks.size < 2:
        return TickResult(path.parent.name, target_hz, int(peaks.size), None, None)

    dt = np.diff(peaks) / bin_hz
    median_dt = float(np.median(dt)) if dt.size else None
    frac_near = float(np.mean((dt > 0.8) & (dt < 1.2))) if dt.size else None
    return TickResult(path.parent.name, target_hz, int(peaks.size), median_dt, frac_near)


def main() -> None:
    root = Path("/Users/chartat1/superdarn/hfdl/data/rawrf_14600_2p5m_aa")
    channels = [p.name for p in sorted(root.iterdir()) if p.is_dir() and (p / "rawrf_continuous.cf32").exists()]
    fs = 2.5e6
    center = 14.6e6
    targets = [14.670e6, 15.000e6]

    results: List[TickResult] = []
    for ch in channels:
        path = root / ch / "rawrf_continuous.cf32"
        for target in targets:
            res = detect_ticks(path, fs, center, target)
            results.append(res)
            label = "CHU" if abs(target - 14.670e6) < 1 else "WWV"
            print(f"{ch:>3} {label} peaks={res.peaks:3d} median_dt={res.median_dt} frac_1s={res.frac_near_1s}")

    # Best candidates by frac_near_1s then peaks
    scored = [r for r in results if r.frac_near_1s is not None]
    scored.sort(key=lambda r: (r.frac_near_1s, r.peaks), reverse=True)
    if scored:
        best = scored[:5]
        print("\nTop candidates:")
        for r in best:
            label = "CHU" if abs(r.target_hz - 14.670e6) < 1 else "WWV"
            print(f"{r.channel} {label} peaks={r.peaks} median_dt={r.median_dt:.3f} frac_1s={r.frac_near_1s:.2f}")


if __name__ == "__main__":
    main()
