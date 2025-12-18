#!/usr/bin/env python3
"""
Concatenate hourly fitacf .bz2 files into daily per-radar/mode files.

This is a Python replacement for concat_fitacf_daily.sh. It scans an input
directory for *.fitacf.bz2 files, groups them by day, radar, and mode, and writes
concatenated daily files to the output directory. Existing outputs are skipped
unless -f is provided.
"""

from __future__ import annotations

import argparse
import bz2
import os
import sys
from datetime import date, datetime
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
    mode: Optional[str]
    hhmm: str
    ss: str
    path: Path


def parse_date_arg(value: str) -> date:
    """Parse CLI date arguments in a few common formats."""
    for fmt in ("%Y,%m,%d", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Invalid date {value!r}. Use YYYY,MM,DD (e.g., 2013,07,01) or YYYY-MM-DD."
    )


def in_date_range(ymd: str, start: Optional[date], end: Optional[date]) -> bool:
    try:
        current = datetime.strptime(ymd, "%Y%m%d").date()
    except ValueError:
        return False
    if start and current < start:
        return False
    if end and current > end:
        return False
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Concatenate hourly fitacf .bz2 files into daily per-radar/mode files.",
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
        "--start",
        dest="start_date",
        type=parse_date_arg,
        default=None,
        help="Start date (inclusive) to process, formats: YYYY,MM,DD or YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        dest="end_date",
        type=parse_date_arg,
        default=None,
        help="End date (inclusive) to process, formats: YYYY,MM,DD or YYYY-MM-DD",
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


def quick_visibility_sample(
    input_dir: Path,
    allowed_radars: Sequence[str],
    start_date: Optional[date],
    end_date: Optional[date],
) -> Optional[Path]:
    """Return the first .fitacf.bz2 match within max depth 3 that passes filters."""
    max_depth = 3
    input_parts = len(input_dir.parts)
    for root, _, files in os.walk(input_dir, followlinks=True):
        root_path = Path(root)
        depth = len(root_path.parts) - input_parts
        if depth > max_depth:
            continue
        for name in files:
            if not name.endswith(".fitacf.bz2"):
                continue
            entry = parse_entry(root_path / name)
            if (
                entry is None
                or not is_allowed_radar(entry.radar, allowed_radars)
                or not in_date_range(entry.ymd, start_date, end_date)
            ):
                continue
            return entry.path
    return None


def parse_entry(path: Path) -> Optional[Entry]:
    base = path.name
    parts = base.split(".")
    if len(parts) < 4:
        return None
    try:
        fit_idx = parts.index("fitacf")
    except ValueError:
        return None
    if fit_idx < 4:
        return None
    ymd, hhmm, ss, radar = parts[:4]
    mode: Optional[str] = None
    if fit_idx > 4:
        extra = ".".join(parts[4:fit_idx]).strip()
        mode = extra or None
    if not ymd or not radar or not hhmm or not ss:
        return None
    return Entry(ymd=ymd, radar=radar, mode=mode, hhmm=hhmm, ss=ss, path=path)


def is_allowed_radar(radar: str, allowlist: Sequence[str]) -> bool:
    return not allowlist or radar in allowlist


def scan_entries(
    input_dir: Path,
    allowed_radars: Sequence[str],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Entry]:
    entries: List[Entry] = []
    index_count = 0

    for root, _, files in os.walk(input_dir, followlinks=True):
        for name in files:
            if not name.endswith(".fitacf.bz2"):
                continue
            entry = parse_entry(Path(root) / name)
            if (
                entry is None
                or not is_allowed_radar(entry.radar, allowed_radars)
                or not in_date_range(entry.ymd, start_date, end_date)
            ):
                continue
            entries.append(entry)
            index_count += 1
            if index_count % 500 == 0:
                print(f"  Indexed {index_count} files so far...", file=sys.stderr)
    return entries


def group_entries(entries: Iterable[Entry]) -> Iterable[Tuple[Tuple[str, str, Optional[str]], List[Entry]]]:
    sorted_entries = sorted(entries, key=lambda e: (e.ymd, e.radar, e.mode or "", e.hhmm, e.ss))
    for key, group in groupby(sorted_entries, key=lambda e: (e.ymd, e.radar, e.mode)):
        yield key, list(group)


def ensure_output_path(out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)


def remove_empty_outputs(
    output_dir: Path,
    extensions: Sequence[str] = (".fit", ".fitacf"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> int:
    """Delete zero-byte output files (optionally filtered by date) so they can be regenerated."""
    if not output_dir.exists():
        return 0

    removed = 0
    lowered_exts = tuple(ext.lower() for ext in extensions)

    for root, _, files in os.walk(output_dir):
        for name in files:
            if not name.lower().endswith(lowered_exts):
                continue
            if start_date or end_date:
                # Skip outputs outside the requested range.
                ymd = name.split(".")[0]
                if not in_date_range(ymd, start_date, end_date):
                    continue
            path = Path(root) / name
            try:
                if path.stat().st_size == 0:
                    path.unlink()
                    removed += 1
            except FileNotFoundError:
                continue
            except OSError as exc:
                print(f"  Failed to remove empty output {path}: {exc}", file=sys.stderr)
    return removed


def decompress_files(
    out_file: Path, files: Sequence[Path], ymd: str, radar: str, mode: Optional[str]
) -> Tuple[str, str, Optional[str], int, bool]:
    total = len(files)
    mode_suffix = f".{mode}" if mode else ""
    if total == 0:
        print(f"  [{ymd} {radar}{mode_suffix}] no files found in list, skipping", file=sys.stderr)
        return ymd, radar, mode, 0, False

    print(f"  [{ymd} {radar}{mode_suffix}] concatenating {total} files -> {out_file}")
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
                    print(f"  [{ymd} {radar}{mode_suffix}] FAILED to decompress {fpath}: {exc}", file=sys.stderr)
                    return ymd, radar, mode, written, False
                written += 1
                if idx % 100 == 0:
                    print(f"  [{ymd} {radar}{mode_suffix}] {idx}/{total} files done", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"  [{ymd} {radar}{mode_suffix}] FAILED writing to {out_file}: {exc}", file=sys.stderr)
        return ymd, radar, mode, written, False

    print(f"  [{ymd} {radar}{mode_suffix}] completed {written} files -> {out_file}")
    return ymd, radar, mode, written, True


def process_chunk(
    entries: List[Entry],
    output_dir: Path,
    force: bool,
    parallel_jobs: int,
    chunk_label: str = "",
) -> Tuple[int, int, int, int]:
    """Process a batch of entries and return counters: processed, skipped, ok, fail."""
    label = f"[{chunk_label}] " if chunk_label else ""

    entry_count = len(entries)
    group_counter = Counter((e.ymd, e.radar, e.mode) for e in entries)

    print(f"{label}Indexed {entry_count} files before sorting.")
    print(f"{label}Unique day/radar/mode groups: {len(group_counter)}")
    print(f"{label}Top groups (count day.radar[.mode]):")
    for (ymd, radar, mode), count in sorted(group_counter.items(), key=lambda kv: kv[1], reverse=True)[:10]:
        mode_suffix = f".{mode}" if mode else ""
        print(f"{label}{count:7d} {ymd}\t{radar}{mode_suffix}")

    if entry_count == 0:
        print(f"{label}No .fitacf.bz2 files found in this chunk.", file=sys.stderr)
        return 0, 0, 0, 0

    processed_files = 0
    skipped_existing = 0
    jobs: List[Tuple[str, str, Optional[str], Path, List[Path]]] = []

    for (ymd, radar, mode), group in group_entries(entries):
        out_dir = output_dir / ymd[:4] / ymd[4:6]
        mode_suffix = f".{mode}" if mode else ""
        out_file = out_dir / f"{ymd}.{radar}{mode_suffix}.fit"

        if out_file.exists() and not force:
            print(f"{label}Skipping existing output: {out_file}")
            skipped_existing += 1
            continue

        ensure_output_path(out_file)
        files = [e.path for e in group]
        processed_files += len(files)
        jobs.append((ymd, radar, mode, out_file, files))

    if processed_files == 0:
        if skipped_existing > 0:
            print(f"{label}All {skipped_existing} outputs already exist. Use -f to overwrite.", file=sys.stderr)
            return 0, skipped_existing, 0, 0
        print(f"{label}No .fitacf.bz2 files queued for processing in this chunk.", file=sys.stderr)
        return 0, 0, 0, 0

    ok_groups = 0
    fail_groups = 0

    if parallel_jobs == 1 or len(jobs) == 1:
        for ymd, radar, mode, out_file, files in jobs:
            mode_suffix = f".{mode}" if mode else ""
            print(f"{label}Launching {len(files)} files for {ymd} {radar}{mode_suffix} -> {out_file}")
            _, _, _, _, success = decompress_files(out_file, files, ymd, radar, mode)
            if success:
                ok_groups += 1
            else:
                fail_groups += 1
    else:
        with ProcessPoolExecutor(max_workers=parallel_jobs) as executor:
            future_map = {}
            for ymd, radar, mode, out_file, files in jobs:
                mode_suffix = f".{mode}" if mode else ""
                print(f"{label}Launching {len(files)} files for {ymd} {radar}{mode_suffix} -> {out_file}")
                future = executor.submit(decompress_files, out_file, files, ymd, radar, mode)
                future_map[future] = (ymd, radar, mode)

            for future in as_completed(future_map):
                ymd, radar, mode = future_map[future]
                mode_suffix = f".{mode}" if mode else ""
                try:
                    _, _, _, _, success = future.result()
                    if success:
                        ok_groups += 1
                    else:
                        fail_groups += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"{label}[{ymd} {radar}{mode_suffix}] failed with exception: {exc}", file=sys.stderr)
                    fail_groups += 1

    return processed_files, skipped_existing, ok_groups, fail_groups


def main() -> int:
    args = parse_args()

    input_dir = Path(args.input_dir.rstrip("/"))
    output_dir = Path(args.output_dir.rstrip("/"))
    radar_allow = [r for r in args.radars.split(",") if r] if args.radars else []

    if args.start_date and args.end_date and args.start_date > args.end_date:
        print("Start date must be on or before end date.", file=sys.stderr)
        return 1

    print("Starting concat_fitacf_daily")
    print(f"  Input directory: {input_dir}")
    print(f"  Output directory: {output_dir}")
    print(f"  Radar filter: {args.radars if args.radars else 'all'}")
    start_label = args.start_date.isoformat() if args.start_date else "unbounded"
    end_label = args.end_date.isoformat() if args.end_date else "unbounded"
    print(f"  Date range: {start_label} to {end_label}")
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
    sample = quick_visibility_sample(input_dir, radar_allow, args.start_date, args.end_date)
    if sample:
        print(f"  Found: {sample}")
    else:
        print("  No files seen in the quick sample; continuing to full scan...", file=sys.stderr)

    removed_empty = remove_empty_outputs(
        output_dir, start_date=args.start_date, end_date=args.end_date
    )
    if removed_empty:
        print(f"Removed {removed_empty} empty .fit/.fitacf output files before processing.")

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
            entries = scan_entries(subdir, radar_allow, args.start_date, args.end_date)
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
    entries = scan_entries(input_dir, radar_allow, args.start_date, args.end_date)
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
