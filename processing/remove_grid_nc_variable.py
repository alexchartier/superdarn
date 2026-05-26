#!/usr/bin/env python3
"""Remove one variable from GRID netCDF files by rewriting them in place."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import netCDF4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Root directory containing .grid.nc files")
    parser.add_argument(
        "--pattern",
        default="**/*.grid.nc",
        help="Glob pattern under root (default: **/*.grid.nc)",
    )
    parser.add_argument(
        "--variable",
        default="vector.vel.dirn",
        help="Variable name to remove (default: vector.vel.dirn)",
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


def copy_without_variable(src_path: Path, variable: str) -> bool:
    with netCDF4.Dataset(src_path) as src:
        if variable not in src.variables:
            return False

        tmp_path = src_path.with_suffix(src_path.suffix + ".tmp")
        with netCDF4.Dataset(tmp_path, "w") as dst:
            for name, dim in src.dimensions.items():
                dst.createDimension(name, None if dim.isunlimited() else len(dim))

            dst.setncatts({name: src.getncattr(name) for name in src.ncattrs()})

            for name, src_var in src.variables.items():
                if name == variable:
                    continue
                dst_var = dst.createVariable(name, src_var.datatype, src_var.dimensions)
                dst_var.setncatts({attr: src_var.getncattr(attr) for attr in src_var.ncattrs()})
                dst_var[:] = src_var[:]

        os.replace(tmp_path, src_path)
        return True


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    files = sorted(root.glob(args.pattern))
    changed = 0
    skipped = 0

    for path in files:
        if args.dry_run:
            with netCDF4.Dataset(path) as ds:
                has_var = args.variable in ds.variables
            if has_var:
                if args.verbose:
                    print(path)
                changed += 1
            else:
                skipped += 1
            continue

        if copy_without_variable(path, args.variable):
            if args.verbose:
                print(path)
            changed += 1
        else:
            skipped += 1

    print(f"changed={changed}")
    print(f"skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
