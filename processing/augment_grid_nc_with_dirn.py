#!/usr/bin/env python3
"""Create a temporary GRID netCDF copy with a corrected vector.vel.dirn field."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path

import aacgmv2
import netCDF4
import numpy as np


DIRN_VAR_NAME = "vector.vel.dirn"
DIRN_VAR_UNITS = "None"
DIRN_VAR_LONG_NAME = "Velocity direction (+1 away from radar, -1 towards)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", help="Input .grid.nc file")
    parser.add_argument("output_file", help="Output .grid.nc file")
    return parser.parse_args()


def mjd_to_datetime(mjd: float) -> datetime:
    return datetime(1858, 11, 17) + timedelta(days=float(mjd))


def wrap_longitudes(lons: np.ndarray | float) -> np.ndarray:
    return ((np.asarray(lons, dtype=float) + 180.0) % 360.0) - 180.0


def calc_bearings(rlat: float, rlon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    lat1 = np.deg2rad(np.asarray(lats, dtype=float))
    lon1 = np.deg2rad(wrap_longitudes(lons))
    lat2 = np.deg2rad(float(rlat))
    lon2 = np.deg2rad(float(wrap_longitudes(rlon)))

    dlon = np.arctan2(np.sin(lon2 - lon1), np.cos(lon2 - lon1))
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return np.rad2deg(np.arctan2(y, x))


def angle_between(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    xr = np.deg2rad(x)
    yr = np.deg2rad(y)
    return np.rad2deg(np.arctan2(np.sin(xr - yr), np.cos(xr - yr)))


def normalize_radar_altitude_km(radar_alt: float) -> float:
    radar_alt = float(radar_alt)
    if radar_alt > 20.0:
        return radar_alt / 1000.0
    return radar_alt


def compute_correct_dirn_values(
    mlat: np.ndarray,
    mlon: np.ndarray,
    kvect: np.ndarray,
    mjd_start: np.ndarray,
    *,
    radar_lat: float,
    radar_lon: float,
    radar_alt: float,
) -> np.ndarray:
    mlat = np.asarray(mlat, dtype=float)
    mlon = np.asarray(mlon, dtype=float)
    kvect = np.asarray(kvect, dtype=float)
    mjd_start = np.asarray(mjd_start, dtype=float)
    radar_alt_km = normalize_radar_altitude_km(radar_alt)

    dirn = np.ones(mlat.shape, dtype=np.int8)
    unique_times, inverse = np.unique(mjd_start, return_inverse=True)

    for time_idx, mjd in enumerate(unique_times):
        mask = inverse == time_idx
        dtime = mjd_to_datetime(mjd)
        r_mlat, r_mlon, _ = aacgmv2.convert_latlon_arr(
            np.asarray([radar_lat]),
            np.asarray([radar_lon]),
            radar_alt_km,
            dtime,
            method_code="G2A",
        )
        cell_to_radar = calc_bearings(float(r_mlat[0]), float(r_mlon[0]), mlat[mask], mlon[mask])
        delta = angle_between(cell_to_radar, kvect[mask])
        # GRID stores a velocity magnitude plus the vector azimuth. For
        # single-radar files, kvect aligns with the cell-to-radar bearing for
        # flow toward the radar, so the signed scalar flips in that case.
        dirn[mask] = np.where(np.abs(delta) <= 90.0, -1, 1).astype(np.int8)

    return dirn


def compute_correct_dirn(ds: netCDF4.Dataset) -> np.ndarray:
    return compute_correct_dirn_values(
        ds.variables["vector.mlat"][:],
        ds.variables["vector.mlon"][:],
        ds.variables["vector.kvect"][:],
        ds.variables["mjd_start"][:],
        radar_lat=float(ds.getncattr("lat")),
        radar_lon=float(ds.getncattr("lon")),
        radar_alt=float(ds.getncattr("alt")),
    )


def copy_with_correct_dirn(src_path: Path, dst_path: Path) -> None:
    with netCDF4.Dataset(src_path) as src, netCDF4.Dataset(dst_path, "w") as dst:
        for name, dim in src.dimensions.items():
            dst.createDimension(name, None if dim.isunlimited() else len(dim))

        dst.setncatts({name: src.getncattr(name) for name in src.ncattrs()})

        for name, src_var in src.variables.items():
            if name == DIRN_VAR_NAME:
                continue
            dst_var = dst.createVariable(name, src_var.datatype, src_var.dimensions)
            dst_var.setncatts({attr: src_var.getncattr(attr) for attr in src_var.ncattrs()})
            dst_var[:] = src_var[:]

        dirn = compute_correct_dirn(src)
        dirn_var = dst.createVariable(DIRN_VAR_NAME, "i1", ("npts",))
        dirn_var[:] = dirn
        dirn_var.units = DIRN_VAR_UNITS
        dirn_var.long_name = DIRN_VAR_LONG_NAME


def rewrite_in_place_with_correct_dirn(path: Path) -> None:
    path = path.expanduser().resolve()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        copy_with_correct_dirn(path, tmp_path)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def main() -> int:
    args = parse_args()
    src_path = Path(args.input_file).expanduser().resolve()
    dst_path = Path(args.output_file).expanduser().resolve()
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    copy_with_correct_dirn(src_path, dst_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
