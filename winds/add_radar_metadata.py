#!/usr/bin/env python3
"""Add radar metadata (name, latitude, longitude) to annual netCDF files."""

from __future__ import annotations

import argparse
import shlex
import os
from pathlib import Path
from typing import Dict, Tuple

os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

import h5py
from netCDF4 import Dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Attach radar name and location metadata to converted annual "
            "meteor wind netCDF files."
        )
    )
    home = Path.home()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=home / "data/superdarn/meteorwindnc_converted_annual",
        help="Directory that contains per-radar subdirectories of annual files.",
    )
    parser.add_argument(
        "--radar-table",
        type=Path,
        default=home / "rst/tables/superdarn/radar.dat",
        help="Path to RST radar.dat table.",
    )
    parser.add_argument(
        "--hdw-dir",
        type=Path,
        default=home / "rst/tables/superdarn/hdw",
        help="Directory that contains hdw.dat.* files.",
    )
    return parser.parse_args()


def load_radar_metadata(
    radar_table: Path, hdw_dir: Path
) -> Dict[str, Tuple[str, float, float]]:
    """Build mapping from 3-letter code to (name, lat, lon)."""
    metadata: Dict[str, Tuple[str, float, float]] = {}
    with radar_table.expanduser().open() as fp:
        for raw_line in fp:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = shlex.split(line)
            if len(fields) < 8:
                continue
            code = fields[7].lower()
            name = fields[4]
            hdw_filename = fields[6]
            latlon = read_hdw_latlon(hdw_dir / hdw_filename)
            if latlon is None:
                continue
            metadata[code] = (name, latlon[0], latlon[1])
    return metadata


def read_hdw_latlon(path: Path) -> Tuple[float, float] | None:
    """Read first valid latitude/longitude from an hdw.dat.* file."""
    try:
        with path.expanduser().open() as fp:
            for raw_line in fp:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                pieces = line.split()
                if len(pieces) < 6:
                    continue
                return float(pieces[4]), float(pieces[5])
    except FileNotFoundError:
        return None
    return None


def update_netcdf(path: Path, code: str, name: str, lat: float, lon: float) -> None:
    """Modify global attributes on a single netCDF file."""
    try:
        with Dataset(str(path), "r+") as dataset:
            dataset.setncattr("radar_code", code)
            dataset.setncattr("radar_name", name)
            dataset.setncattr("radar_latitude", lat)
            dataset.setncattr("radar_longitude", lon)
            return
    except OSError:
        pass
    with h5py.File(path, "r+") as dataset:
        dataset.attrs["radar_code"] = code
        dataset.attrs["radar_name"] = name
        dataset.attrs["radar_latitude"] = lat
        dataset.attrs["radar_longitude"] = lon


def main() -> None:
    args = parse_args()
    metadata = load_radar_metadata(args.radar_table, args.hdw_dir)
    if not metadata:
        raise SystemExit("No radar metadata could be loaded.")

    updated = 0
    skipped = []
    for radar_dir in sorted(args.data_root.expanduser().iterdir()):
        if not radar_dir.is_dir():
            continue
        code = radar_dir.name.lower()
        meta = metadata.get(code)
        if meta is None:
            skipped.append(code)
            continue
        name, lat, lon = meta
        for nc_path in sorted(radar_dir.glob("*.nc")):
            update_netcdf(nc_path, code, name, lat, lon)
            updated += 1
    msg = f"Updated {updated} files."
    if skipped:
        msg += f" Skipped radars without metadata: {', '.join(sorted(skipped))}."
    print(msg)


if __name__ == "__main__":
    main()
