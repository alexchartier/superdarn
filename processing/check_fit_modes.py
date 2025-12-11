#!/usr/bin/env python3
"""
Identify .fit files that are missing mode information compared to their .fitacf.bz2 sources.

Given a directory of .fit outputs and the original .fitacf.bz2 inputs, this script reports any
.fit files whose names omit or mis-state the mode seen in the source data. It can optionally
delete the problematic .fit files so they can be regenerated.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Optional, Set, Tuple


BZIP_EXT = ".bz2"
FIT_EXTS = {"fit", "fitacf"}


def parse_bzip_entry(path: Path) -> Optional[Tuple[str, str, Optional[str]]]:
    parts = path.name.split(".")
    if len(parts) < 4 or not path.name.endswith(BZIP_EXT):
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
    return ymd, radar, mode


def parse_fit_entry(path: Path) -> Optional[Tuple[str, str, Optional[str]]]:
    parts = path.name.split(".")
    if len(parts) < 3:
        return None
    ext = parts[-1].lower()
    if ext not in FIT_EXTS:
        return None
    ymd = parts[0]
    radar = parts[1]
    mode = ".".join(parts[2:-1]) if len(parts) > 3 else None
    return ymd, radar, mode


def build_bzip_reference(
    bzip_root: Path,
) -> Tuple[DefaultDict[Tuple[str, str], Set[Optional[str]]], Dict[Tuple[str, str, Optional[str]], List[Path]]]:
    modes_by_day_radar: DefaultDict[Tuple[str, str], Set[Optional[str]]] = defaultdict(set)
    paths_by_key: Dict[Tuple[str, str, Optional[str]], List[Path]] = defaultdict(list)

    for root, _, files in os.walk(bzip_root):
        for name in files:
            path = Path(root) / name
            parsed = parse_bzip_entry(path)
            if parsed is None:
                continue
            ymd, radar, mode = parsed
            modes_by_day_radar[(ymd, radar)].add(mode)
            paths_by_key[(ymd, radar, mode)].append(path)
    return modes_by_day_radar, paths_by_key


def scan_fit_outputs(fit_root: Path) -> List[Tuple[str, str, Optional[str], Path]]:
    entries: List[Tuple[str, str, Optional[str], Path]] = []
    for root, _, files in os.walk(fit_root):
        for name in files:
            path = Path(root) / name
            parsed = parse_fit_entry(path)
            if parsed is None:
                continue
            ymd, radar, mode = parsed
            entries.append((ymd, radar, mode, path))
    return entries


def find_mismatches(
    fit_entries: Iterable[Tuple[str, str, Optional[str], Path]],
    modes_by_day_radar: Dict[Tuple[str, str], Set[Optional[str]]],
    paths_by_key: Dict[Tuple[str, str, Optional[str]], List[Path]],
) -> List[Dict[str, object]]:
    mismatches: List[Dict[str, object]] = []
    for ymd, radar, fit_mode, fit_path in fit_entries:
        expected_modes = modes_by_day_radar.get((ymd, radar))
        if not expected_modes:
            continue  # No reference; skip.

        has_mode_sources = any(m is not None for m in expected_modes)
        reason: Optional[str] = None

        if fit_mode is None and has_mode_sources:
            reason = "missing mode suffix"
        elif fit_mode is not None and fit_mode not in expected_modes:
            reason = "mode not present in source data"

        if reason is None:
            continue

        modes_to_list = sorted(expected_modes, key=lambda m: m or "")
        bz2_paths: List[Path] = []
        for mode in modes_to_list:
            bz2_paths.extend(paths_by_key.get((ymd, radar, mode), []))

        mismatches.append(
            {
                "ymd": ymd,
                "radar": radar,
                "fit_mode": fit_mode,
                "fit_path": fit_path,
                "reason": reason,
                "bz2_paths": bz2_paths,
                "expected_modes": modes_to_list,
            }
        )
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find .fit files whose names do not include the mode present in their .fitacf.bz2 sources.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-b",
        "--bzip-dir",
        dest="bzip_dir",
        default="fitacf_bzip",
        help="Directory containing the .fitacf.bz2 source files",
    )
    parser.add_argument(
        "-f",
        "--fit-dir",
        dest="fit_dir",
        default="fitacf_daily",
        help="Directory containing the generated .fit outputs",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete the mismatched .fit files after listing them",
    )
    args = parser.parse_args()

    bzip_root = Path(args.bzip_dir).expanduser()
    fit_root = Path(args.fit_dir).expanduser()

    if not bzip_root.is_dir():
        print(f"Source .bz2 directory not found: {bzip_root}", file=sys.stderr)
        return 1
    if not fit_root.is_dir():
        print(f".fit output directory not found: {fit_root}", file=sys.stderr)
        return 1

    print(f"Scanning .fitacf.bz2 sources under {bzip_root} ...")
    modes_by_day_radar, paths_by_key = build_bzip_reference(bzip_root)
    print(f"  Found {len(paths_by_key)} mode-specific source groups.")

    print(f"Scanning .fit outputs under {fit_root} ...")
    fit_entries = scan_fit_outputs(fit_root)
    print(f"  Found {len(fit_entries)} .fit files.")

    mismatches = find_mismatches(fit_entries, modes_by_day_radar, paths_by_key)

    if not mismatches:
        print("No mismatched .fit files detected.")
        return 0

    print(f"\nDetected {len(mismatches)} mismatched .fit files:\n")
    for item in mismatches:
        mode_label = item["fit_mode"] or "(no mode)"
        expected = ",".join(m or "(no mode)" for m in item["expected_modes"])  # type: ignore[index]
        print(f"* {item['fit_path']}  [mode in filename: {mode_label}]  expected modes: {expected}")
        for bz2_path in item["bz2_paths"]:  # type: ignore[index]
            print(f"    bz2: {bz2_path}")

    if args.delete:
        deleted = 0
        for item in mismatches:
            fit_path: Path = item["fit_path"]  # type: ignore[assignment]
            try:
                fit_path.unlink()
                deleted += 1
                print(f"Deleted {fit_path}")
            except OSError as exc:
                print(f"Failed to delete {fit_path}: {exc}", file=sys.stderr)
        print(f"\nRemoved {deleted} mismatched .fit files.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
