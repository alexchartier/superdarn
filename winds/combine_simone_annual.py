"""Build an annual SIMONe wind .mat file using the gradient products.

This reads the 2020 `amn_gradient_YYYYMMDD.001.h5` files from
`/Users/chartat1/data/meteor_winds/SIMONe`, keeps the 1 km altitude grid
from 70–115 km, and writes a MATLAB file with the same field structure
as `riogrande_2019.mat` (lat, lon, counts, u, v, alt, Time, hour).
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import pathlib
import re
from typing import Optional

import h5py
import numpy as np
from scipy.io import savemat


MATLAB_EPOCH = 719529.0  # datenum for 1970-01-01


def matlab_datenum_from_unix(ts: np.ndarray) -> np.ndarray:
    """Convert Unix seconds to MATLAB datenum."""
    return ts / 86400.0 + MATLAB_EPOCH


def load_day(file_path: pathlib.Path, alt_ref: Optional[np.ndarray]):
    """Load one gradient file and return alt, u (east), v (north), time."""
    with h5py.File(file_path, "r") as f:
        alt = f["gdalt"][:]
        u = f["vnea"][:]  # shape (time, alt)
        v = f["vnna"][:]
        ts = f["timestamps"][:]
        lat_vals = f["gdlat"][:]
        lon_vals = f["glon"][:]

    if alt_ref is not None and not np.allclose(alt, alt_ref):
        raise ValueError(f"Altitude grid mismatch in {file_path}")

    # hour dimension is first in the HDF5 (time, alt). We want (alt, hour).
    return (
        alt,
        u.T,
        v.T,
        matlab_datenum_from_unix(ts),
        float(np.nanmean(lat_vals)),
        float(np.nanmean(lon_vals)),
    )


def build_annual(input_dir: pathlib.Path, year: int, output_path: pathlib.Path):
    files = sorted(input_dir.glob("amn_gradient_*.h5"))
    pattern = re.compile(r"amn_gradient_(\d{8})")

    days_in_year = 366 if calendar.isleap(year) else 365
    alt_ref: Optional[np.ndarray] = None
    u_3d = v_3d = counts = None
    # Prefill Time with deterministic UT hours to avoid NaNs in downstream hour grid.
    Time = np.zeros((24, days_in_year), dtype=float)
    for d in range(days_in_year):
        dn = dt.date(year, 1, 1).toordinal() + d
        Time[:, d] = dn + np.arange(24, dtype=float) / 24.0
    lat = lon = np.nan

    for fpath in files:
        m = pattern.search(fpath.name)
        if not m:
            continue
        file_date = dt.datetime.strptime(m.group(1), "%Y%m%d").date()
        if file_date.year != year:
            continue

        day_idx = (file_date - dt.date(year, 1, 1)).days
        if not 0 <= day_idx < days_in_year:
            continue

        alt, u_day, v_day, ts_day, lat_val, lon_val = load_day(fpath, alt_ref)
        if alt_ref is None:
            alt_ref = alt
            alt_len = len(alt_ref)
            u_3d = np.full((alt_len, 24, days_in_year), np.nan, dtype=float)
            v_3d = np.full_like(u_3d, np.nan)
            counts = np.full_like(u_3d, np.nan)  # counts not provided in source
            lat = lat_val
            lon = lon_val

        u_3d[:, :, day_idx] = u_day
        v_3d[:, :, day_idx] = v_day
        Time[: len(ts_day), day_idx] = ts_day
        lat = lat_val if np.isnan(lat) else lat
        lon = lon_val if np.isnan(lon) else lon

    if alt_ref is None:
        raise RuntimeError("No gradient files found for the requested year")

    savemat(
        output_path,
        {
            "lat": np.array([[lat]], dtype=float),
            "lon": np.array([[lon]], dtype=float),
            "counts": counts,
            "u": u_3d,
            "v": v_3d,
            "alt": alt_ref.reshape(-1, 1),
            "Time": Time,
            "hour": np.arange(24, dtype=np.uint8).reshape(-1, 1),
        },
        do_compression=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=pathlib.Path,
        default=pathlib.Path("/Users/chartat1/data/meteor_winds/SIMONe"),
    )
    parser.add_argument("--year", type=int, default=2020)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("simone_2020.mat"),
    )
    args = parser.parse_args()

    build_annual(args.input_dir, args.year, args.output)


if __name__ == "__main__":
    main()
