#!/usr/bin/env python3
"""Rewrite GRID netCDF files in place with a corrected vector.vel.dirn field."""

from __future__ import annotations

import argparse
from pathlib import Path

from augment_grid_nc_with_dirn import rewrite_in_place_with_correct_dirn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Root directory containing .grid.nc files")
    parser.add_argument(
        "--pattern",
        default="**/*.grid.nc",
        help="Glob pattern under root (default: **/*.grid.nc)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report matching files without rewriting them",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each changed file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    files = sorted(root.glob(args.pattern))

    changed = 0
    for path in files:
        if args.dry_run:
            changed += 1
            if args.verbose:
                print(path)
            continue

        rewrite_in_place_with_correct_dirn(path)
        changed += 1
        if args.verbose:
            print(path)

    print(f"changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
