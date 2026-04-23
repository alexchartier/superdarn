#!/usr/bin/env python3
"""Plot a combined SuperDARN GRID netCDF window across many radar files."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
import netCDF4
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pydarn


VECTOR_KEYS = [
    "vector.mlat",
    "vector.mlon",
    "vector.kvect",
    "vector.vel.median",
    "vector.vel.sd",
    "vector.pwr.median",
    "vector.wdt.median",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate multiple GRID netCDF files for one time window and render a polar plot."
    )
    parser.add_argument("grid_nc_dir", help="Directory containing .grid.nc files")
    parser.add_argument(
        "--pattern",
        default="*.grid.nc",
        help="Glob pattern within grid_nc_dir (default: *.grid.nc)",
    )
    parser.add_argument(
        "--start-time",
        required=True,
        help="Window start time (YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS)",
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=2,
        help="Match points with start times in [start_time, start_time + window_minutes)",
    )
    parser.add_argument(
        "--hemisphere",
        choices=("north", "south", "all"),
        default="north",
        help="Restrict points by hemisphere (default: north)",
    )
    parser.add_argument(
        "--include-radars",
        nargs="+",
        help="Optional list of radar codes to include, e.g. cve cvw hkw",
    )
    parser.add_argument("--parameter", default="vel", help="Grid parameter to plot")
    parser.add_argument("--title", default="", help="Optional plot title")
    parser.add_argument("-o", "--output", required=True, help="Output PNG path")
    return parser.parse_args()


def parse_time(value: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"invalid time format: {value}")


def mjd_to_datetime(mjd: float) -> datetime:
    return datetime(1858, 11, 17) + timedelta(days=float(mjd))


def file_radar_code(path: Path) -> str:
    stem = path.name
    if stem.endswith(".grid.nc"):
        stem = stem[: -len(".grid.nc")]
    if ".fitacf" in stem:
        stem = stem.split(".fitacf", 1)[0]
    return stem.split(".", 1)[1]


def radar_id_for_code(code: str) -> int:
    candidates = [code]
    if "." in code:
        candidates.append(code.split(".", 1)[0])

    for candidate in candidates:
        for radar_id, radar in pydarn.SuperDARNRadars.radars.items():
            if radar.hardware_info.abbrev == candidate:
                return int(radar_id.value)
    raise KeyError(f"unknown radar code: {code}")


def load_nc_vars(path: Path) -> dict[str, np.ndarray]:
    with netCDF4.Dataset(path) as ds:
        return {name: np.asarray(ds.variables[name][:]) for name in ds.variables}


def iter_record_slices(mjd_start: np.ndarray) -> list[slice]:
    mjd_start = np.asarray(mjd_start)
    if mjd_start.size == 0:
        return []

    breaks = np.flatnonzero(np.diff(mjd_start) != 0) + 1
    starts = np.concatenate(([0], breaks))
    stops = np.concatenate((breaks, [mjd_start.size]))
    return [slice(int(start), int(stop)) for start, stop in zip(starts, stops)]


def record_hemisphere(data: dict[str, np.ndarray], rec_slice: slice) -> str | None:
    mlats = np.asarray(data["vector.mlat"][rec_slice])
    if mlats.size == 0:
        return None
    return "north" if float(mlats[0]) >= 0 else "south"


def find_matching_record_slice(
    data: dict[str, np.ndarray],
    start_time: datetime,
    window_minutes: int,
    hemisphere: str,
) -> slice | None:
    window_end = start_time + timedelta(minutes=window_minutes)

    for rec_slice in iter_record_slices(data["mjd_start"]):
        rec_start = mjd_to_datetime(float(data["mjd_start"][rec_slice.start]))
        if not (start_time <= rec_start < window_end):
            continue

        rec_hemi = record_hemisphere(data, rec_slice)
        if hemisphere != "all" and rec_hemi != hemisphere:
            continue

        return rec_slice

    return None


def merge_nc_files(
    files: list[Path],
    start_time: datetime,
    window_minutes: int,
    hemisphere: str,
    include_radars: set[str] | None,
) -> tuple[dict, list[Path]]:
    merged: dict[str, np.ndarray] = {}
    matched_files: list[Path] = []
    stids: list[int] = []
    start_values: list[float] = []
    end_values: list[float] = []

    for path in files:
        radar_code = file_radar_code(path)
        if include_radars is not None and radar_code not in include_radars:
            continue
        data = load_nc_vars(path)
        rec_slice = find_matching_record_slice(data, start_time, window_minutes, hemisphere)
        if rec_slice is None:
            continue

        matched_files.append(path)
        stids.append(radar_id_for_code(radar_code))
        start_values.append(float(data["mjd_start"][rec_slice.start]))
        end_values.append(float(np.max(data["mjd_end"][rec_slice])))

        for key in VECTOR_KEYS:
            values = np.asarray(data[key][rec_slice])
            merged.setdefault(key, [])
            merged[key].append(values)

    if not matched_files:
        raise SystemExit(
            f"no {hemisphere} data matched {start_time.isoformat()} within {window_minutes} minutes"
        )

    for key in VECTOR_KEYS:
        merged[key] = np.concatenate(merged[key])

    start_dt = mjd_to_datetime(min(start_values))
    end_dt = mjd_to_datetime(max(end_values))
    record = {
        "stid": np.asarray(sorted(set(stids)), dtype=np.int16),
        "nvec": np.asarray([len(merged["vector.mlat"])], dtype=np.int16),
        "start.year": int(start_dt.year),
        "start.month": int(start_dt.month),
        "start.day": int(start_dt.day),
        "start.hour": int(start_dt.hour),
        "start.minute": int(start_dt.minute),
        "start.second": int(start_dt.second),
        "end.year": int(end_dt.year),
        "end.month": int(end_dt.month),
        "end.day": int(end_dt.day),
        "end.hour": int(end_dt.hour),
        "end.minute": int(end_dt.minute),
        "end.second": int(end_dt.second),
    }
    record.update(merged)
    return record, matched_files


def main() -> int:
    args = parse_args()
    grid_nc_dir = Path(args.grid_nc_dir).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(grid_nc_dir.glob(args.pattern))
    if not files:
        raise SystemExit(f"no files matched {args.pattern} in {grid_nc_dir}")

    start_time = parse_time(args.start_time)
    include_radars = set(args.include_radars) if args.include_radars else None
    record, matched_files = merge_nc_files(
        files,
        start_time,
        args.window_minutes,
        args.hemisphere,
        include_radars,
    )

    plt.figure(figsize=(10, 10))
    title = args.title or (
        f"{args.hemisphere.title()} GRID-NC vectors {start_time:%Y-%m-%d %H:%M} UTC "
        f"({len(matched_files)} radars, {int(record['nvec'][0])} vectors)"
    )
    pydarn.Grid.plot_grid([record], record=0, parameter=args.parameter, title=title)
    plt.gcf().savefig(out_path, dpi=180, bbox_inches="tight")

    print(f"output={out_path}")
    print(f"matched_radars={len(matched_files)}")
    print(f"matched_files={','.join(path.name for path in matched_files)}")
    print(f"nvec={int(record['nvec'][0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
