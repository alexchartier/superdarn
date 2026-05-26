#!/usr/bin/env python3
"""Record a single UHD receive stream into DigitalRF."""

from __future__ import annotations

import argparse
import math
import os
import shutil
import shlex
import signal
import subprocess
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path

import digital_rf as drf
import numpy as np


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Record a UHD channel into DigitalRF.")
    p.add_argument("output", type=Path, help="Top-level DigitalRF output directory.")
    p.add_argument("--channel-name", default="ch0", help="DigitalRF channel subdirectory name.")
    p.add_argument("--metadata-name", default="capture", help="Digital metadata file prefix.")
    p.add_argument("--uhd-args", default="", help="UHD device args for uhd_rx_cfile.")
    p.add_argument("--spec", help="UHD subdevice spec.")
    p.add_argument("--channel", type=int, default=0, help="UHD receive channel index.")
    p.add_argument("--antenna", help="RX antenna port name.")
    p.add_argument("--freq-hz", type=float, required=True, help="Center frequency in Hz.")
    p.add_argument("--rate-hz", type=float, default=1_000_000.0, help="Sample rate in Hz.")
    p.add_argument("--gain-db", type=float, help="Receiver gain in dB.")
    p.add_argument("--duration-s", type=float, help="Recording duration in seconds.")
    p.add_argument("--nsamples", type=int, help="Override total sample count.")
    p.add_argument("--sync", choices=["default", "pps"], default="default", help="Pass --sync to uhd_rx_cfile.")
    p.add_argument("--lo-offset-hz", type=float, help="LO offset in Hz.")
    p.add_argument("--stream-args", help="Additional UHD stream args.")
    p.add_argument("--subdir-cadence-secs", type=int, default=3600, help="DigitalRF subdirectory cadence.")
    p.add_argument("--file-cadence-ms", type=int, default=1000, help="DigitalRF file cadence in ms.")
    p.add_argument("--metadata-file-cadence-secs", type=int, default=60, help="Digital metadata file cadence.")
    p.add_argument("--compression-level", type=int, default=0, choices=range(10), help="DigitalRF gzip compression.")
    p.add_argument("--checksum", action="store_true", help="Enable HDF5 checksum.")
    p.add_argument("--uuid", help="Optional UUID string for the DigitalRF channel.")
    p.add_argument("--chunk-samples", type=int, default=262_144, help="Samples per pipe read/write chunk.")
    p.add_argument(
        "--start-epoch-seconds",
        type=float,
        help="Override channel start time in Unix seconds. Default is host wall clock at recorder start.",
    )
    p.add_argument("--verbose", action="store_true", help="Pass -v to uhd_rx_cfile.")
    p.add_argument("--dry-run", action="store_true", help="Print the planned command and exit.")
    return p.parse_args()


def _validate_output(top_dir: Path, channel_name: str, metadata_dir: Path) -> Path:
    top_dir.mkdir(parents=True, exist_ok=True)
    channel_dir = top_dir / channel_name
    if channel_dir.exists() and any(channel_dir.iterdir()):
        raise RuntimeError(f"Refusing to write into non-empty channel directory: {channel_dir}")
    channel_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    return channel_dir


def _remove_tree_if_exists(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _rate_fraction(rate_hz: float) -> Fraction:
    return Fraction(rate_hz).limit_denominator(1_000_000)


def _build_uhd_command(args: argparse.Namespace, nsamples: int | None) -> list[str]:
    cmd = ["uhd_rx_cfile", "/dev/stdout", "-r", str(args.rate_hz), "-f", str(args.freq_hz), "-c", str(args.channel)]
    if args.uhd_args:
        cmd.extend(["-a", args.uhd_args])
    if args.spec:
        cmd.append(f"--spec={args.spec}")
    if args.antenna:
        cmd.extend(["-A", args.antenna])
    if args.gain_db is not None:
        cmd.extend(["-g", str(args.gain_db)])
    if args.lo_offset_hz is not None:
        cmd.append(f"--lo-offset={args.lo_offset_hz}")
    if args.stream_args:
        cmd.append(f"--stream-args={args.stream_args}")
    if args.sync != "default":
        cmd.append(f"--sync={args.sync}")
    if nsamples is not None:
        cmd.extend(["-N", str(nsamples)])
    if args.verbose:
        cmd.append("-v")
    return cmd


def _forward_stderr(pipe) -> None:
    try:
        for line in iter(pipe.readline, b""):
            if not line:
                break
            sys.stderr.buffer.write(line)
            sys.stderr.flush()
    finally:
        pipe.close()


def run(args: argparse.Namespace) -> int:
    if args.nsamples is not None and args.nsamples <= 0:
        raise ValueError("--nsamples must be positive")
    if args.duration_s is not None and args.duration_s <= 0:
        raise ValueError("--duration-s must be positive")
    if args.file_cadence_ms <= 0 or args.subdir_cadence_secs <= 0:
        raise ValueError("Cadence values must be positive")
    if (args.subdir_cadence_secs * 1000) % args.file_cadence_ms != 0:
        raise ValueError("(subdir_cadence_secs * 1000) must be divisible by file_cadence_ms")
    if args.subdir_cadence_secs % args.metadata_file_cadence_secs != 0:
        raise ValueError("subdir_cadence_secs must be divisible by metadata_file_cadence_secs")

    rate = _rate_fraction(args.rate_hz)
    nsamples = args.nsamples
    if nsamples is None and args.duration_s is not None:
        nsamples = int(math.floor(args.duration_s * rate.numerator / rate.denominator))
    if nsamples is not None and nsamples <= 0:
        raise ValueError("Requested duration produced zero samples")

    top_dir = args.output.expanduser().resolve()
    metadata_dir = top_dir / "metadata"
    channel_dir = _validate_output(top_dir, args.channel_name, metadata_dir)

    start_epoch = float(args.start_epoch_seconds) if args.start_epoch_seconds is not None else time.time()
    start_index = int(math.floor(start_epoch * rate.numerator / rate.denominator))
    cmd = _build_uhd_command(args, nsamples)

    capture_meta = {
        "channel_name": args.channel_name,
        "uhd_command": cmd,
        "uhd_command_shell": " ".join(shlex.quote(part) for part in cmd),
        "freq_hz": float(args.freq_hz),
        "rate_hz": float(args.rate_hz),
        "rate_fraction": [int(rate.numerator), int(rate.denominator)],
        "gain_db": None if args.gain_db is None else float(args.gain_db),
        "uhd_args": args.uhd_args,
        "spec": args.spec,
        "antenna": args.antenna,
        "channel": int(args.channel),
        "sync": args.sync,
        "lo_offset_hz": None if args.lo_offset_hz is None else float(args.lo_offset_hz),
        "stream_args": args.stream_args,
        "chunk_samples": int(args.chunk_samples),
        "start_epoch_seconds": start_epoch,
        "start_global_index": int(start_index),
        "host": os.uname().nodename,
        "timestamp_note": (
            "Channel start index uses host wall clock at recorder start unless "
            "--start-epoch-seconds is supplied."
        ),
    }

    if args.dry_run:
        _eprint(f"channel_dir={channel_dir}")
        _eprint(f"metadata_dir={metadata_dir}")
        _eprint(f"start_global_index={start_index}")
        _eprint("command=" + capture_meta["uhd_command_shell"])
        return 0

    writer = None
    meta_writer = None

    sample_nbytes = np.dtype(np.complex64).itemsize
    read_nbytes = int(args.chunk_samples) * sample_nbytes
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    stderr_thread = threading.Thread(target=_forward_stderr, args=(proc.stderr,), daemon=True)
    stderr_thread.start()

    bytes_buffer = bytearray()
    total_written = 0
    interrupted = False
    failed_before_data = False
    try:
        while True:
            chunk = proc.stdout.read(read_nbytes)
            if not chunk:
                break
            bytes_buffer.extend(chunk)
            full_nbytes = (len(bytes_buffer) // sample_nbytes) * sample_nbytes
            if full_nbytes == 0:
                continue
            raw = bytes(bytes_buffer[:full_nbytes])
            del bytes_buffer[:full_nbytes]
            samples = np.frombuffer(raw, dtype=np.complex64)
            if samples.size == 0:
                continue
            if writer is None:
                writer = drf.DigitalRFWriter(
                    str(channel_dir),
                    np.complex64,
                    args.subdir_cadence_secs,
                    args.file_cadence_ms,
                    start_index,
                    rate.numerator,
                    rate.denominator,
                    uuid_str=args.uuid,
                    compression_level=args.compression_level,
                    checksum=args.checksum,
                    is_complex=True,
                    num_subchannels=1,
                    is_continuous=True,
                    marching_periods=False,
                )
                meta_writer = drf.DigitalMetadataWriter(
                    str(metadata_dir),
                    args.subdir_cadence_secs,
                    args.metadata_file_cadence_secs,
                    rate.numerator,
                    rate.denominator,
                    args.metadata_name,
                )
                meta_writer.write(start_index, capture_meta)
            writer.rf_write(np.ascontiguousarray(samples).reshape(-1, 1))
            total_written += int(samples.size)
    except KeyboardInterrupt:
        interrupted = True
        _eprint("Interrupted, terminating uhd_rx_cfile...")
        proc.send_signal(signal.SIGINT)
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        return_code = proc.wait()
        stderr_thread.join(timeout=1.0)
        if bytes_buffer:
            _eprint(f"Dropping {len(bytes_buffer)} trailing bytes that did not form a complete complex64 sample.")
        failed_before_data = (writer is None and return_code != 0 and not interrupted)
        if writer is not None:
            writer.close()

    stop_epoch = time.time()
    if meta_writer is not None:
        meta_writer.write(
            start_index + max(total_written - 1, 0),
            {
                "total_samples_written": int(total_written),
                "stop_epoch_seconds": float(stop_epoch),
                "duration_seconds_observed": float(total_written * rate.denominator / rate.numerator),
                "uhd_return_code": int(return_code),
                "interrupted": bool(interrupted),
            },
        )

    if failed_before_data:
        _remove_tree_if_exists(top_dir)

    if interrupted:
        return 130
    if return_code != 0:
        raise RuntimeError(f"uhd_rx_cfile exited with status {return_code}")

    _eprint(
        "Wrote "
        f"{total_written} samples ({total_written * rate.denominator / rate.numerator:.3f} s) "
        f"to {channel_dir}"
    )
    return 0


def main() -> int:
    try:
        return run(parse_args())
    except Exception as exc:
        _eprint(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
