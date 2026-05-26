#!/usr/bin/env python3
"""Stream IQ samples from an HDF5 raw RF file into dumphfdl.

This is a thin wrapper that:
- opens an HDF5 file and selects a dataset with IQ samples
- infers (or accepts) sample format compatible with dumphfdl
- selects HFDL channel frequencies from a systable (or explicit list)
- pipes raw IQ bytes to dumphfdl via stdin
"""

from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
from typing import Iterable, List, Optional, Tuple

import h5py
import numpy as np


_NUMERIC_KINDS = {"i", "u", "f", "c"}


def _print(msg: str) -> None:
    print(msg, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect HFDL using dumphfdl over HDF5 raw RF data")
    parser.add_argument("--input", required=True, help="Path to raw RF HDF5 file")
    parser.add_argument("--dataset", help="HDF5 dataset path with IQ samples (auto-detect if omitted)")
    parser.add_argument("--sample-rate-hz", type=float, help="Sample rate in Hz")
    parser.add_argument("--center-freq-khz", type=float, help="Center frequency in kHz")
    parser.add_argument("--sample-format", choices=["U8", "CS16", "CF32"], help="IQ sample format for dumphfdl")
    parser.add_argument("--systable", help="Path to dumphfdl systable.conf (optional)")
    parser.add_argument("--freqs-khz", nargs="*", type=float, help="Explicit HFDL frequencies (kHz)")
    parser.add_argument("--usable-bw-frac", type=float, default=0.8,
                        help="Usable fraction of sample rate (default: 0.8)")
    parser.add_argument("--chunk-samples", type=int, default=1_000_000, help="Samples per read chunk")
    parser.add_argument("--start-s", type=float, default=0.0, help="Start time offset in seconds")
    parser.add_argument("--duration-s", type=float, default=None, help="Duration to process in seconds")
    parser.add_argument("--dumphfdl", default="dumphfdl", help="Path to dumphfdl binary")
    parser.add_argument("--dry-run", action="store_true", help="Print inferred settings and exit")
    return parser.parse_args()


def _is_numeric_dataset(obj: h5py.Dataset) -> bool:
    return isinstance(obj, h5py.Dataset) and obj.dtype.kind in _NUMERIC_KINDS


def _dataset_size(ds: h5py.Dataset) -> int:
    try:
        size = int(np.prod(ds.shape))
    except Exception:
        size = 0
    return size


def auto_select_dataset(h5: h5py.File) -> h5py.Dataset:
    candidates: List[Tuple[int, str, h5py.Dataset]] = []

    def _visit(name: str, obj: h5py.Dataset) -> None:
        if _is_numeric_dataset(obj):
            candidates.append((_dataset_size(obj), name, obj))

    h5.visititems(_visit)
    if not candidates:
        raise RuntimeError("No numeric datasets found in HDF5 file")

    candidates.sort(key=lambda t: t[0], reverse=True)
    size, name, ds = candidates[0]
    _print(f"Auto-selected dataset '{name}' (size={size}, shape={ds.shape}, dtype={ds.dtype})")
    return ds


def _find_attr(obj: h5py.Dataset, keys: List[str]) -> Optional[Tuple[str, float]]:
    for key in keys:
        if key in obj.attrs:
            val = obj.attrs[key]
            try:
                return key, float(val)
            except Exception:
                pass
    return None


def _find_attr_recursive(h5: h5py.File, keys: List[str]) -> Optional[Tuple[str, float]]:
    # Check file attrs first
    res = _find_attr(h5, keys)
    if res:
        return res
    # Then datasets and groups
    found: Optional[Tuple[str, float]] = None

    def _visit(name: str, obj: h5py.Dataset) -> None:
        nonlocal found
        if found is not None:
            return
        if hasattr(obj, "attrs"):
            res = _find_attr(obj, keys)
            if res:
                found = res

    h5.visititems(_visit)
    return found


def _normalize_hz_from_key(key: str, value: float) -> float:
    k = key.lower()
    if "khz" in k:
        return value * 1_000.0
    if "mhz" in k:
        return value * 1_000_000.0
    return value


def _normalize_khz_from_key(key: str, value: float) -> float:
    k = key.lower()
    if "khz" in k:
        return value
    if "mhz" in k:
        return value * 1_000.0
    # assume Hz
    return value / 1_000.0


def parse_systable_frequencies(path: str) -> List[float]:
    text = open(path, "r", encoding="utf-8").read()
    freqs: List[float] = []
    for block in re.findall(r"frequencies\s*=\s*\(([^)]*)\)", text):
        for num in re.findall(r"\b\d+\.\d+\b", block):
            try:
                freqs.append(float(num))
            except Exception:
                pass
    return sorted(set(freqs))


def select_channels(freqs_khz: List[float], center_khz: float, sample_rate_hz: float,
                    usable_bw_frac: float) -> List[float]:
    half_bw_khz = (sample_rate_hz / 1000.0) * usable_bw_frac / 2.0
    return [f for f in freqs_khz if abs(f - center_khz) <= half_bw_khz]


def infer_sample_format(ds: h5py.Dataset) -> Tuple[str, str]:
    dt = ds.dtype
    if dt.kind == "c":
        if dt.itemsize == 8:
            return "CF32", "complex64"
        if dt.itemsize == 16:
            return "CF32", "complex128"
    if dt.kind in {"i", "u"} and ds.ndim >= 2 and ds.shape[1] == 2:
        if dt.kind == "u" and dt.itemsize == 1:
            return "U8", "uint8 iq interleaved"
        if dt.kind == "i" and dt.itemsize == 2:
            return "CS16", "int16 iq interleaved"
    if dt.kind == "f" and ds.ndim >= 2 and ds.shape[1] == 2 and dt.itemsize == 4:
        return "CF32", "float32 iq interleaved"
    raise RuntimeError(f"Cannot infer sample format from dtype={dt}, shape={ds.shape}")


def iter_iq_bytes(ds: h5py.Dataset, fmt: str, start_idx: int, count: Optional[int],
                  chunk_samples: int) -> Iterable[bytes]:
    total = ds.shape[0]
    end = total if count is None else min(total, start_idx + count)
    idx = start_idx
    while idx < end:
        n = min(chunk_samples, end - idx)
        chunk = ds[idx: idx + n]
        if fmt == "CF32":
            if chunk.dtype.kind == "c":
                if chunk.dtype.itemsize != 8:
                    chunk = chunk.astype(np.complex64)
                yield chunk.tobytes()
            elif chunk.dtype.kind == "f" and chunk.ndim >= 2 and chunk.shape[1] == 2 and chunk.dtype.itemsize == 4:
                yield np.asarray(chunk, dtype=np.float32).tobytes()
            else:
                raise RuntimeError(f"Cannot convert dtype={chunk.dtype}, shape={chunk.shape} to CF32")
        elif fmt == "CS16":
            if chunk.dtype.kind == "i" and chunk.dtype.itemsize == 2 and chunk.ndim >= 2 and chunk.shape[1] == 2:
                yield np.asarray(chunk, dtype=np.int16).tobytes()
            else:
                raise RuntimeError(f"Cannot convert dtype={chunk.dtype}, shape={chunk.shape} to CS16")
        elif fmt == "U8":
            if chunk.dtype.kind == "u" and chunk.dtype.itemsize == 1 and chunk.ndim >= 2 and chunk.shape[1] == 2:
                yield np.asarray(chunk, dtype=np.uint8).tobytes()
            else:
                raise RuntimeError(f"Cannot convert dtype={chunk.dtype}, shape={chunk.shape} to U8")
        else:
            raise RuntimeError(f"Unsupported sample format: {fmt}")
        idx += n


def main() -> int:
    args = parse_args()

    if not os.path.isfile(args.input):
        _print(f"Input not found: {args.input}")
        return 2

    with h5py.File(args.input, "r") as h5:
        ds = h5[args.dataset] if args.dataset else auto_select_dataset(h5)

        fmt = args.sample_format
        fmt_note = None
        if fmt is None:
            fmt, fmt_note = infer_sample_format(ds)

        # Infer sample rate and center frequency from attrs if missing
        sample_rate_hz = args.sample_rate_hz
        if sample_rate_hz is None:
            res = _find_attr_recursive(h5, [
                "sample_rate_hz", "sample_rate", "sampling_rate", "samp_rate", "fs", "rx_rate"
            ])
            if res:
                key, val = res
                sample_rate_hz = _normalize_hz_from_key(key, val)

        center_khz = args.center_freq_khz
        if center_khz is None:
            res = _find_attr_recursive(h5, [
                "center_freq_khz", "center_freq", "center_frequency", "fc", "rx_center_freq", "frequency"
            ])
            if res:
                key, val = res
                center_khz = _normalize_khz_from_key(key, val)

        if sample_rate_hz is None:
            _print("Sample rate unknown. Provide --sample-rate-hz.")
            return 2
        if center_khz is None:
            _print("Center frequency unknown. Provide --center-freq-khz.")
            return 2

        # Build frequency list
        if args.freqs_khz:
            freqs_khz = args.freqs_khz
        elif args.systable:
            all_freqs = parse_systable_frequencies(args.systable)
            freqs_khz = select_channels(all_freqs, center_khz, sample_rate_hz, args.usable_bw_frac)
        else:
            _print("Provide --freqs-khz or --systable to select HFDL channels.")
            return 2

        if not freqs_khz:
            _print("No HFDL channels fall within the usable bandwidth. Adjust center/sample rate or list.")
            return 2

        start_idx = int(math.floor(args.start_s * sample_rate_hz))
        count = None
        if args.duration_s is not None:
            count = int(math.floor(args.duration_s * sample_rate_hz))

        _print(f"Dataset: shape={ds.shape} dtype={ds.dtype}")
        _print(f"Sample format: {fmt}" + (f" ({fmt_note})" if fmt_note else ""))
        _print(f"Sample rate: {sample_rate_hz} Hz")
        _print(f"Center freq: {center_khz} kHz")
        _print(f"HFDL channels: {', '.join(f'{f:.1f}' for f in freqs_khz)}")

        cmd = [
            args.dumphfdl,
            "--iq-file", "-",
            "--sample-rate", f"{sample_rate_hz}",
            "--sample-format", fmt,
            "--centerfreq", f"{center_khz}",
        ]
        if args.systable:
            cmd += ["--system-table", args.systable]
        cmd += [f"{f:.1f}" for f in freqs_khz]

        if args.dry_run:
            _print("Dry run. dumphfdl command:")
            _print(" ".join(cmd))
            return 0

        _print("Starting dumphfdl...")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        assert proc.stdin is not None

        try:
            for b in iter_iq_bytes(ds, fmt, start_idx, count, args.chunk_samples):
                proc.stdin.write(b)
        finally:
            proc.stdin.close()

        return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
