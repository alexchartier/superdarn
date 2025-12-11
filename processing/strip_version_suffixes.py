#!/usr/bin/env python3
"""
Remove version codes (e.g., ".v3.0") from filenames in year/month directories.

Example:
    1994/12/19941231.sto.v3.0.fit -> 1994/12/19941231.sto.fit
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, List, Set


VERSION_RE = re.compile(r"\.v\d+(?:\.\d+)*(?=\.[^.]+$)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove version codes (e.g., .v3.0) from filenames under year/month directories.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-r",
        "--root",
        dest="root",
        default="fitacf_daily",
        help="Root directory containing year/month subdirectories",
    )
    parser.add_argument(
        "-e",
        "--extensions",
        dest="extensions",
        default="fit,fitacf",
        help="Comma-separated list of file extensions to process",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Show planned renames without changing any files",
    )
    return parser.parse_args()


def iter_month_dirs(root: Path) -> Iterable[Path]:
    for year_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for month_dir in sorted(p for p in year_dir.iterdir() if p.is_dir()):
            yield month_dir


def strip_version_suffix(name: str) -> str | None:
    """Return name without version suffix; None if no version suffix was found."""
    if not VERSION_RE.search(name):
        return None
    return VERSION_RE.sub("", name)


def find_targets(month_dir: Path, allowed_exts: Set[str]) -> List[tuple[Path, Path]]:
    renames: List[tuple[Path, Path]] = []
    print(f"Scanning {month_dir}")
    for entry in sorted(month_dir.iterdir()):
        if not entry.is_file():
            continue
        ext = entry.suffix.lower().lstrip(".")
        if ext not in allowed_exts:
            continue
        new_name = strip_version_suffix(entry.name)
        if new_name is None or new_name == entry.name:
            continue
        target = entry.with_name(new_name)
        renames.append((entry, target))
    return renames


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser()
    allowed_exts = {ext.strip().lower() for ext in args.extensions.split(",") if ext.strip()}

    if not root.is_dir():
        print(f"Root directory not found: {root}")
        return 1

    total_planned = 0
    total_skipped = 0

    for month_dir in iter_month_dirs(root):
        renames = find_targets(month_dir, allowed_exts)
        if not renames:
            continue
        for src, dst in renames:
            if dst.exists():
                print(f"  SKIP (exists): {dst}")
                total_skipped += 1
                continue
            total_planned += 1
            print(f"  {'WOULD RENAME' if args.dry_run else 'RENAMING'}: {src} -> {dst}")
            if not args.dry_run:
                src.rename(dst)

    if total_planned == 0:
        print("No files with version suffixes found.")
    else:
        print(f"Completed. Planned/renamed: {total_planned}, skipped (target existed): {total_skipped}")
        if args.dry_run:
            print("Dry run only; no files were changed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
