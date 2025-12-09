#!/usr/bin/env python3
"""
Concatenate hourly fitacf .bz2 files into daily per-radar files.

This is a Python replacement for concat_fitacf_daily.sh. It scans an input
directory for *.fitacf.bz2 files, groups them by day and radar, and writes
concatenated daily files to the output directory. Existing outputs are skipped
unless -f is provided.
"""

from __future__ import annotations

import argparse
import bz2
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


# Size for chunked decompression writes
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class Entry:
    ymd: str
    radar: str
    hhmm: str
    ss: str
    path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Concatenate hourly fitacf .bz2 files into daily per-radar files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i",
        dest="input_dir",
        default="fitacf_bzip",
        help="Root directory containing the year/month subfolders with *.fitacf.bz2 files",
    )
    parser.add_argument(
        "-o",
        dest="output_dir",
        default="fitacf_daily",
        help="Output directory for concatenated daily files",
    )
    parser.add_argument(
        "-r",
        dest="radars",
        default="",
        help="Comma-separated radar codes to include; if omitted, process all radars",
    )
    parser.add_argument(
        "-p",
        dest="parallel_jobs",
        type=int,
        default=1,
        help="Number of radar/day concatenations to run in parallel",
    )
    parser.add_argument(
        "-f",
        dest="force",
        action="store_true",
        help="Overwrite existing daily outputs instead of skipping them",
    )
    parser.add_argument(
        "--per-dir",
        dest="per_dir",
        action="store_true",
        help="Process each immediate subdirectory of input_dir separately to shorten the upfront scan (useful when input is organized by month). Default behavior.",
    )
    parser.add_argument(
        "--no-per-dir",
        dest="per_dir",
        action="store_false",
        help="Disable per-directory processing and scan the full tree in one pass.",
    )
    parser.set_defaults(per_dir=True)
    return parser.parse_args()


def quick_visibility_sample(input_dir: Path) -> Optional[Path]:
    """Return the first .fitacf.bz2 match within max depth 3 for visibility."""
    max_depth = 3
    input_parts = len(input_dir.parts)
    for root, _, files in os.walk(input_dir, followlinks=True):
        root_path = Path(root)
        depth = len(root_path.parts) - input_parts
        if depth > max_depth:
            continue
        for name in files:
            if name.endswith(".fitacf.bz2"):
                return root_path / name
    return None


def parse_entry(path: Path) -> Optional[Entry]:
    base = path.name
    parts = base.split(".")
    if len(parts) < 4:
        return None
    ymd, hhmm, ss, radar = parts[:4]
    if not ymd or not radar or not hhmm or not ss:
        return None
    return Entry(ymd=ymd, radar=radar, hhmm=hhmm, ss=ss, path=path)


def is_allowed_radar(radar: str, allowlist: Sequence[str]) -> bool:
    return not allowlist or radar in allowlist


def scan_entries(input_dir: Path, allowed_radars: Sequence[str]) -> List[Entry]:
    entries: List[Entry] = []
    index_count = 0

    for root, _, files in os.walk(input_dir, followlinks=True):
        for name in files:
            if not name.endswith(".fitacf.bz2"):
                continue
            entry = parse_entry(Path(root) / name)
            if entry is None or not is_allowed_radar(entry.radar, allowed_radars):
                continue
            entries.append(entry)
            index_count += 1
            if index_count % 500 == 0:
                print(f"  Indexed {index_count} files so far...", file=sys.stderr)
    return entries


def group_entries(entries: Iterable[Entry]) -> Iterable[Tuple[Tuple[str, str], List[Entry]]]:
    sorted_entries = sorted(entries, key=lambda e: (e.ymd, e.radar, e.hhmm, e.ss))
    for key, group in groupby(sorted_entries, key=lambda e: (e.ymd, e.radar)):
        yield key, list(group)


def ensure_output_path(out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)


def decompress_files(out_file: Path, files: Sequence[Path], ymd: str, radar: str) -> Tuple[str, str, int, bool]:
    total = len(files)
    if total == 0:
        print(f"  [{ymd} {radar}] no files found in list, skipping", file=sys.stderr)
        return ymd, radar, 0, False

    print(f"  [{ymd} {radar}] concatenating {total} files -> {out_file}")
    written = 0
    try:
        with open(out_file, "wb") as dest:
            for idx, fpath in enumerate(files, start=1):
                try:
                    with bz2.open(fpath, "rb") as src:
                        while True:
                            chunk = src.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            dest.write(chunk)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [{ymd} {radar}] FAILED to decompress {fpath}: {exc}", file=sys.stderr)
                    return ymd, radar, written, False
                written += 1
                if idx % 100 == 0:
                    print(f"  [{ymd} {radar}] {idx}/{total} files done", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"  [{ymd} {radar}] FAILED writing to {out_file}: {exc}", file=sys.stderr)
        return ymd, radar, written, False

    print(f"  [{ymd} {radar}] completed {written} files -> {out_file}")
    return ymd, radar, written, True


def main() -> int:
    args = parse_args()

    input_dir = Path(args.input_dir.rstrip("/"))
    output_dir = Path(args.output_dir.rstrip("/"))
    radar_allow = [r for r in args.radars.split(",") if r] if args.radars else []

    print("Starting concat_fitacf_daily")
    print(f"  Input directory: {input_dir}")
    print(f"  Output directory: {output_dir}")
    print(f"  Radar filter: {args.radars if args.radars else 'all'}")
    print(f"  Force overwrite: {int(args.force)}")
    print(f"  Parallel jobs: {args.parallel_jobs}")

    if not input_dir.is_dir():
        print(f"Input directory not found: {input_dir}", file=sys.stderr)
        return 1
    if args.parallel_jobs < 1:
        print(f"Parallel jobs must be a positive integer: {args.parallel_jobs}", file=sys.stderr)
        return 1

    print("Scanning input directory for .fitacf.bz2 files (progress every 500 files)...")
    print("  This step sorts the full list first, so a large tree can take a while before concatenation starts.")

    print("Quick visibility check (first match, maxdepth 3)...")
    sample = quick_visibility_sample(input_dir)
    if sample:
        print(f"  Found: {sample}")
    else:
        print("  No files seen in the quick sample; continuing to full scan...", file=sys.stderr)

    # When per-dir is enabled, process each immediate subdirectory independently.
    if args.per_dir:
        subdirs = sorted([p for p in input_dir.iterdir() if p.is_dir()])
        if not subdirs:
            subdirs = [input_dir]
        total_processed = 0
        total_skipped = 0
        total_ok = 0
        total_fail = 0

        for subdir in subdirs:
            print(f"\nProcessing subdirectory: {subdir}")
            entries = scan_entries(subdir, radar_allow)
            processed, skipped, ok, fail = process_chunk(
                entries,
                output_dir,
                force=args.force,
                parallel_jobs=args.parallel_jobs,
                chunk_label=str(subdir),
            )
            total_processed += processed
            total_skipped += skipped
            total_ok += ok
            total_fail += fail

        print(
            f"Summary: queued {total_processed} files into {total_ok} completed groups; "
            f"{total_fail} groups failed; skipped existing outputs: {total_skipped}"
        )
        return 1 if total_fail > 0 else 0

    # Default: single full-tree pass
    entries = scan_entries(input_dir, radar_allow)
    processed, skipped, ok, fail = process_chunk(
        entries,
        output_dir,
        force=args.force,
        parallel_jobs=args.parallel_jobs,
    )
    print(
        f"Summary: queued {processed} files into {ok} completed groups; "
        f"{fail} groups failed; skipped existing outputs: {skipped}"
    )
    return 1 if fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
