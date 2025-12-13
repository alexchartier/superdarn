#!/usr/bin/env python3
"""
Downmix, integrate, and decimate a DigitalRF dataset to 100 kS/s centered at 10 MHz.

Defaults target the provided dataset:
    Input:  /Users/chartat1/data/hf_data/itsi_rooftop/2025_06_04_14_19_14
    Output: /Users/chartat1/data/hf_data/itsi_rooftop/2025_06_04_14_19_14_10mhz_100ksps

Processing steps
----------------
- Read 1 s blocks from the input DigitalRF channel.
- Mix from the raw center frequency (default 17.5 MHz) to the desired 10 MHz center.
- Multi-stage IIR decimation down to 100 kS/s with a final integrate-and-dump stage.
- Optional final lowpass (default ±40 kHz) to clean the band edge.
- Write a new DigitalRF dataset aligned in time with the source.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import List
import h5py

import digital_rf as drf
import numpy as np
from scipy import signal
from tqdm import tqdm


# Defaults tuned for the provided dataset
DEFAULT_INPUT_ROOT = Path("/Users/chartat1/data/hf_data/itsi_rooftop/2025_06_04_14_19_14")
DEFAULT_OUTPUT_ROOT = DEFAULT_INPUT_ROOT.parent / (DEFAULT_INPUT_ROOT.name + "_10mhz_100ksps")
DEFAULT_CHANNEL = "cha"
DEFAULT_RAW_CENTER_HZ = 17_500_000.0
DEFAULT_TARGET_CENTER_HZ = 10_000_000.0
DEFAULT_FS_OUT = 100_000.0
DEFAULT_BLOCK_SECONDS = 1.0
DEFAULT_BANDWIDTH_HZ = 80_000.0  # keep ±40 kHz at 100 kS/s
DEFAULT_FINAL_FILTER_ORDER = 6
TWO_PI = 2.0 * math.pi


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mix/integrate/decimate DigitalRF IQ to 100 kS/s at 10 MHz.")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT, help="Top-level DigitalRF directory.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Destination DigitalRF root (channel subdir is created automatically).",
    )
    parser.add_argument("--channel", default=DEFAULT_CHANNEL, help="Channel name inside the DigitalRF dataset.")
    parser.add_argument("--raw-center-hz", type=float, default=DEFAULT_RAW_CENTER_HZ, help="Recorded center frequency.")
    parser.add_argument("--target-center-hz", type=float, default=DEFAULT_TARGET_CENTER_HZ, help="Desired center freq.")
    parser.add_argument("--fs-out", type=float, default=DEFAULT_FS_OUT, help="Output sample rate in Hz.")
    parser.add_argument(
        "--block-seconds",
        type=float,
        default=DEFAULT_BLOCK_SECONDS,
        help="Seconds per processing block (1 s matches the file cadence).",
    )
    parser.add_argument(
        "--bandwidth-hz",
        type=float,
        default=DEFAULT_BANDWIDTH_HZ,
        help="Two-sided bandwidth to keep after decimation (Hz).",
    )
    parser.add_argument(
        "--final-filter-order",
        type=int,
        default=DEFAULT_FINAL_FILTER_ORDER,
        help="Butterworth order for the post-decimation lowpass.",
    )
    parser.add_argument(
        "--no-final-lowpass",
        action="store_true",
        help="Skip the final lowpass (keeps only the integrate-and-dump response).",
    )
    parser.add_argument(
        "--stop-after",
        type=int,
        default=None,
        help="Limit number of files for a quick test run.",
    )
    return parser.parse_args()


def gather_files(channel_dir: Path) -> List[Path]:
    if not channel_dir.is_dir():
        raise FileNotFoundError(f"Channel directory does not exist: {channel_dir}")
    hour_dirs = sorted(channel_dir.glob("20??-??-??T??-??-??"))
    files: List[Path] = []
    for hour_dir in hour_dirs:
        files.extend(sorted(hour_dir.glob("rf@*.h5")))
    if not files:
        raise FileNotFoundError(f"No rf@*.h5 files found under {channel_dir}")
    return files


def parse_timestamp_from_filename(path: Path) -> int:
    name = path.name
    if "@" not in name or "." not in name:
        raise ValueError(f"Cannot parse timestamp from {name}")
    return int(name.split("@")[1].split(".")[0])


def factor_decimation(decimation: int) -> List[int]:
    """Prime factorization limited to small factors, sorted to downsample aggressively early."""
    if decimation < 1:
        raise ValueError("Decimation must be >= 1")
    factors: List[int] = []
    remaining = decimation
    for p in (2, 3, 5, 7, 11, 13):
        while remaining % p == 0:
            factors.append(p)
            remaining //= p
    if remaining > 1:
        factors.append(remaining)
    return sorted(factors, reverse=True)


def integrate_and_decimate(data: np.ndarray, factors: List[int], integrate_last: bool = True) -> np.ndarray:
    """Multi-stage decimation with an optional integrate-and-dump for the final stage."""
    y = data.astype(np.complex64, copy=False)
    for i, q in enumerate(factors):
        last_stage = integrate_last and i == len(factors) - 1
        if last_stage:
            trim = y.shape[0] % q
            if trim:
                y = y[:-trim]
            y = y.reshape(-1, q).mean(axis=1)
        else:
            y = signal.decimate(y, q, ftype="iir", zero_phase=True).astype(np.complex64, copy=False)
    return y


def final_lowpass(data: np.ndarray, fs_out: float, bandwidth_hz: float, order: int) -> np.ndarray:
    cutoff_hz = bandwidth_hz / 2.0
    nyquist = fs_out / 2.0
    norm_cutoff = min(0.99, cutoff_hz / nyquist)
    sos = signal.butter(order, norm_cutoff, btype="low", output="sos")
    return signal.sosfiltfilt(sos, data).astype(np.complex64, copy=False)


def main() -> None:
    args = parse_args()
    input_root = args.input_root
    output_root = args.output_root
    channel_dir = input_root / args.channel

    try:
        files = gather_files(channel_dir)
    except FileNotFoundError as exc:
        print(exc)
        sys.exit(1)

    reader = drf.DigitalRFReader(str(input_root))
    props = reader.get_properties(args.channel)
    fs_in = float(props["samples_per_second"])
    file_cadence_ms = int(props["file_cadence_millisecs"])
    subdir_cadence_secs = int(props["subdir_cadence_secs"])
    file_cadence_seconds = file_cadence_ms / 1000.0

    decimation_ratio = fs_in / args.fs_out
    decimation = int(round(decimation_ratio))
    if abs(decimation_ratio - decimation) > 1e-6 or decimation < 1:
        raise ValueError(f"Input/output rates not integer-related: fs_in={fs_in}, fs_out={args.fs_out}")

    factors = factor_decimation(decimation)
    if math.prod(factors) != decimation:
        raise ValueError(f"Could not factor decimation={decimation}, factors={factors}")

    first_timestamp = parse_timestamp_from_filename(files[0])
    start_global_index_out = int(first_timestamp * args.fs_out)
    output_channel_dir = output_root / args.channel
    output_channel_dir.mkdir(parents=True, exist_ok=True)

    writer = drf.DigitalRFWriter(
        str(output_channel_dir),
        dtype="c8",
        subdir_cadence_secs=subdir_cadence_secs,
        file_cadence_millisecs=file_cadence_ms,
        start_global_index=start_global_index_out,
        sample_rate_numerator=int(args.fs_out),
        sample_rate_denominator=1,
        is_complex=True,
        num_subchannels=1,
        compression_level=0,
    )

    if abs(args.block_seconds - file_cadence_seconds) > 1e-9:
        print(
            f"Warning: block_seconds={args.block_seconds} differs from file cadence "
            f"{file_cadence_seconds}s; reads may overlap or gap."
        )

    samples_per_block = int(round(fs_in * args.block_seconds))
    mix_hz = args.raw_center_hz - args.target_center_hz
    phase_step = TWO_PI * mix_hz / fs_in if mix_hz else 0.0
    phase = 0.0
    next_input_sample = None

    print(
        f"Input fs={fs_in/1e6:.3f} MS/s, output fs={args.fs_out/1e3:.1f} kS/s, "
        f"decimation factors={factors}, mix={mix_hz/1e6:.3f} MHz"
    )
    print(f"Writing to {output_channel_dir}, start_global_index={start_global_index_out}")

    try:
        for idx, fpath in enumerate(tqdm(files, desc="Processing files")):
            if args.stop_after is not None and idx >= args.stop_after:
                break

            unix_time = parse_timestamp_from_filename(fpath)
            start_in = int(unix_time * fs_in)
            block = reader.read_vector_1d(start_in, samples_per_block, args.channel)
            if block.size == 0:
                print(f"Warning: empty read for {fpath.name}")
                continue

            block = block.astype(np.complex64, copy=False)
            if next_input_sample is None:
                next_input_sample = start_in

            if start_in < next_input_sample:
                print(f"Skipping out-of-order block {fpath.name}")
                continue

            if phase_step:
                gap = start_in - next_input_sample
                if gap:
                    phase = (phase + phase_step * gap) % TWO_PI
                n = np.arange(block.shape[0], dtype=np.float64)
                block *= np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
                phase = (phase + phase_step * float(block.shape[0])) % TWO_PI

            block = integrate_and_decimate(block, factors, integrate_last=True)

            if not args.no_final_lowpass:
                block = final_lowpass(block, args.fs_out, args.bandwidth_hz, args.final_filter_order)

            start_out_global = int(unix_time * args.fs_out)
            rel_start = start_out_global - start_global_index_out
            writer.rf_write(block, next_sample=rel_start)

            next_input_sample = start_in + block.shape[0]
    finally:
        writer.close()

    # Store useful metadata in drf_properties.h5
    props_path = output_channel_dir / "drf_properties.h5"
    try:
        with h5py.File(props_path, "a") as f:
            f.attrs["center_frequency_hz"] = float(args.target_center_hz)
            f.attrs["source_center_frequency_hz"] = float(args.raw_center_hz)
            f.attrs["source_sample_rate_hz"] = float(fs_in)
            f.attrs["output_sample_rate_hz"] = float(args.fs_out)
            f.attrs["decimation_factor"] = int(decimation)
    except Exception as exc:
        print(f"Warning: could not write metadata to {props_path}: {exc}")

    print("Done. New DigitalRF dataset written to", output_channel_dir)


if __name__ == "__main__":
    main()
