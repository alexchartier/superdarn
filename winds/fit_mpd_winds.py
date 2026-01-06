#!/usr/bin/env python3
"""
Fit hourly horizontal winds from Rio Grande MPD meteor files.

Inputs:
- MPD files like ~/data/meteor_winds/riogrande/MPD_2020/mp2020*.riogrande.mpd

Processing:
- Bin meteors into 2 km altitude bins from 70–110 km (centers 71–109 km).
- Bin in hourly UT intervals (0–1, 1–2, …, 23–24); time coordinate is bin center.
- Assume zero vertical wind and fit u (east) and v (north) from line-of-sight
  velocity using least squares: Vlos = u*sin(phi)*sin(theta) + v*cos(phi)*sin(theta).
- Record the number of meteors used in each bin.

Outputs:
- One NetCDF per day with variables u, v, and counts on (time, alt) dimensions.
"""

from __future__ import annotations

import argparse
import glob
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import numpy as np
import pandas as pd
import xarray as xr


# Altitude and time bin definitions
ALT_EDGES_KM = np.arange(70, 112, 2)  # 70, 72, ..., 110
ALT_CENTERS_KM = 0.5 * (ALT_EDGES_KM[:-1] + ALT_EDGES_KM[1:])
TIME_EDGES_HR = np.arange(0, 25, 1)  # 0, 1, ..., 24
TIME_CENTERS_HR = TIME_EDGES_HR[:-1] + 0.5

# Columns present in the MPD data section (whitespace-delimited)
MPD_COLUMNS = [
    "Date",
    "Time",
    "File",
    "Rge",
    "Ht",
    "Vrad",
    "delVr",
    "Theta",
    "Phi0",
    "Ambig",
    "Delphase",
    "ant",
    "pair",
    "IREX",
    "amax",
    "Tau",
    "vmet",
    "snrdb",
]


@dataclass
class Metadata:
    site_name: str
    lat: float
    lon: float
    timezone_hours: float
    data_start_line: int


def parse_header(path: str) -> Metadata:
    """Read the header to extract site metadata and the data start line."""
    site_name = ""
    lat = np.nan
    lon = np.nan
    tz = 0.0
    data_start = None

    with open(path, "r") as f:
        for idx, line in enumerate(f):
            stripped = line.strip()
            if stripped.startswith("SITENAME"):
                parts = stripped.split()
                if len(parts) > 1:
                    site_name = parts[1]
            elif stripped.startswith("LOCATION"):
                # Form: LOCATION -53.7,-67.7
                parts = stripped.split()
                if len(parts) > 1 and "," in parts[1]:
                    lat_str, lon_str = parts[1].split(",")
                    lat = float(lat_str)
                    lon = float(lon_str)
            elif stripped.startswith("TIME_ZONE"):
                parts = stripped.split()
                if len(parts) > 1:
                    tz = float(parts[1])
            elif stripped.startswith("Date"):
                data_start = idx + 1  # data start is the next line
                break

    if data_start is None:
        raise ValueError(f"Could not locate data header line in {path}")

    return Metadata(site_name=site_name, lat=lat, lon=lon, timezone_hours=tz, data_start_line=data_start)


def load_mpd_dataframe(path: str, metadata: Metadata, apply_timezone: bool) -> pd.DataFrame:
    """Load the MPD file into a DataFrame and attach UTC timestamps."""
    df = pd.read_csv(path, sep=r"\s+", skiprows=metadata.data_start_line, names=MPD_COLUMNS, engine="python")
    dt = pd.to_datetime(df["Date"] + " " + df["Time"], errors="coerce")
    if apply_timezone:
        # TIME_ZONE is typically local offset from UTC (e.g., -3 means UTC-3).
        # Convert to UTC by subtracting the offset (adds 3 hours when tz = -3).
        dt = dt - pd.to_timedelta(metadata.timezone_hours, unit="h")
    df["datetime_utc"] = dt
    return df


def fit_bin(df_bin: pd.DataFrame, min_meteors: int) -> Tuple[float, float, int]:
    """Fit u/v for a single altitude/time bin."""
    sin_theta = np.sin(np.deg2rad(df_bin["Theta"].to_numpy()))
    phi_rad = np.deg2rad(df_bin["Phi0"].to_numpy())
    vlos = df_bin["Vrad"].to_numpy()

    good = np.isfinite(vlos) & np.isfinite(sin_theta) & np.isfinite(phi_rad) & (np.abs(sin_theta) > 1e-6)
    if good.sum() < min_meteors:
        return np.nan, np.nan, good.sum()

    A = np.column_stack([np.sin(phi_rad[good]) * sin_theta[good], np.cos(phi_rad[good]) * sin_theta[good]])
    b = vlos[good]

    if np.linalg.matrix_rank(A) < 2:
        return np.nan, np.nan, good.sum()

    sol, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    u_east = float(sol[0])
    v_north = float(sol[1])
    return u_east, v_north, good.sum()


def process_file(
    path: str,
    out_dir: str,
    min_meteors: int,
    apply_timezone: bool,
) -> str:
    """Process one MPD file and write a daily NetCDF."""
    metadata = parse_header(path)
    df = load_mpd_dataframe(path, metadata, apply_timezone)

    # Infer date from filename (mpYYYYMMDD)
    basename = os.path.basename(path)
    date_str = basename[2:10]
    day_start = datetime.strptime(date_str, "%Y%m%d")
    day_end = day_start + timedelta(days=1)

    # Limit to the target day (UTC)
    mask = (df["datetime_utc"] >= day_start) & (df["datetime_utc"] < day_end)
    df = df.loc[mask].copy()
    if df.empty:
        raise ValueError(f"No data found within {day_start:%Y-%m-%d} UTC for {path}")

    df["ut_hours"] = (df["datetime_utc"] - day_start).dt.total_seconds() / 3600.0

    n_time = len(TIME_CENTERS_HR)
    n_alt = len(ALT_CENTERS_KM)
    u = np.full((n_time, n_alt), np.nan, dtype=float)
    v = np.full((n_time, n_alt), np.nan, dtype=float)
    counts = np.zeros((n_time, n_alt), dtype=int)

    for ti in range(n_time):
        t0, t1 = TIME_EDGES_HR[ti], TIME_EDGES_HR[ti + 1]
        df_t = df[(df["ut_hours"] >= t0) & (df["ut_hours"] < t1)]
        if df_t.empty:
            continue
        for ai in range(n_alt):
            a0, a1 = ALT_EDGES_KM[ai], ALT_EDGES_KM[ai + 1]
            df_bin = df_t[(df_t["Ht"] >= a0) & (df_t["Ht"] < a1)]
            if df_bin.empty:
                continue
            u_val, v_val, n_used = fit_bin(df_bin, min_meteors=min_meteors)
            u[ti, ai] = u_val
            v[ti, ai] = v_val
            counts[ti, ai] = int(n_used)

    times = np.array([day_start + timedelta(hours=float(hr)) for hr in TIME_CENTERS_HR], dtype="datetime64[ns]")
    ds = xr.Dataset(
        data_vars={
            "u": (("time", "alt"), u),
            "v": (("time", "alt"), v),
            "counts": (("time", "alt"), counts),
        },
        coords={
            "time": times,
            "alt": ALT_CENTERS_KM,
        },
        attrs={
            "title": "Hourly meteor winds from Rio Grande MPD",
            "source_file": os.path.abspath(path),
            "site_name": metadata.site_name,
            "site_latitude_deg": metadata.lat,
            "site_longitude_deg": metadata.lon,
            "timezone_header_hours": metadata.timezone_hours,
            "processing": "Hourly UT bins; 2-km altitude bins 70-110 km; zero vertical wind assumption",
            "min_meteors_per_bin": min_meteors,
            "history": f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} fit_mpd_winds.py",
        },
    )

    ds["time"].attrs.update(
        {
            "long_name": "UTC time at bin center",
        }
    )
    ds["alt"].attrs.update({"units": "km", "long_name": "Altitude (bin center)"})
    ds["u"].attrs.update({"units": "m/s", "long_name": "Zonal wind (east positive)"})
    ds["v"].attrs.update({"units": "m/s", "long_name": "Meridional wind (north positive)"})
    ds["counts"].attrs.update({"units": "1", "long_name": "Meteors used in fit"})

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{date_str}_riogrande_winds.nc")
    ds.to_netcdf(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Fit meteor winds from Rio Grande MPD files and emit daily NetCDFs.")
    parser.add_argument(
        "--input-glob",
        default="~/data/meteor_winds/riogrande/MPD_2020/mp2020*.riogrande.mpd",
        help="Glob for input MPD files.",
    )
    parser.add_argument(
        "--out-dir",
        default="~/data/meteor_winds/riogrande/MPD_2020_nc",
        help="Directory to write daily NetCDF files.",
    )
    parser.add_argument(
        "--min-meteors",
        type=int,
        default=5,
        help="Minimum meteors required to emit a wind fit for a bin.",
    )
    parser.add_argument(
        "--apply-timezone",
        action="store_true",
        help="Apply TIME_ZONE header offset to convert timestamps to UTC (default assumes times already UTC).",
    )

    args = parser.parse_args()
    in_files = sorted(glob.glob(os.path.expanduser(args.input_glob)))
    out_dir = os.path.expanduser(args.out_dir)

    if not in_files:
        raise SystemExit(f"No files matched {args.input_glob}")

    written: List[str] = []
    for path in in_files:
        out_path = process_file(
            os.path.expanduser(path),
            out_dir=out_dir,
            min_meteors=args.min_meteors,
            apply_timezone=args.apply_timezone,
        )
        written.append(out_path)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
