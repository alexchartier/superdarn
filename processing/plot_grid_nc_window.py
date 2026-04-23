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


DEFAULT_PYMIX_DIR = Path("~/data/ampere/pymix/misc_pipeline_import_localf107").expanduser()
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
    parser.add_argument(
        "--pymix-dir",
        default=str(DEFAULT_PYMIX_DIR) if DEFAULT_PYMIX_DIR.is_dir() else None,
        help="Optional directory containing mix_robinson_<hemisphere>_YYYYMMDD.nc files",
    )
    parser.add_argument(
        "--pymix-level-step",
        type=float,
        default=10.0,
        help="Potential contour spacing in kV (default: 10)",
    )
    parser.add_argument(
        "--pymix-max-time-delta-min",
        type=float,
        default=5.0,
        help="Maximum allowed time offset from the plot time to the nearest PyMIX slice, in minutes",
    )
    parser.add_argument(
        "--pymix-color",
        default="k",
        help="Contour color for the PyMIX potential overlay (default: k)",
    )
    parser.add_argument(
        "--pymix-linewidth",
        type=float,
        default=0.6,
        help="Contour linewidth for the PyMIX potential overlay (default: 0.6)",
    )
    parser.add_argument(
        "--pymix-alpha",
        type=float,
        default=0.65,
        help="Contour alpha for the PyMIX potential overlay (default: 0.65)",
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


def load_pymix_slice(
    pymix_dir: Path | None,
    when: datetime,
    hemisphere: str,
    max_time_delta_min: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    if pymix_dir is None:
        return None
    if hemisphere not in {"north", "south"}:
        raise ValueError("PyMIX overlay requires hemisphere north or south")

    path = pymix_dir / f"mix_robinson_{hemisphere}_{when:%Y%m%d}.nc"
    if not path.is_file():
        raise FileNotFoundError(f"PyMIX file not found: {path}")

    with netCDF4.Dataset(path) as ds:
        times = np.asarray(ds.variables["time"][:], dtype=float)
        deltas = np.array([abs((mjd_to_datetime(mjd) - when).total_seconds()) for mjd in times])
        time_idx = int(np.argmin(deltas))
        if deltas[time_idx] > max_time_delta_min * 60.0:
            raise ValueError(
                f"nearest PyMIX time {mjd_to_datetime(times[time_idx]).isoformat()} is "
                f"{deltas[time_idx] / 60.0:.1f} minutes from {when.isoformat()}"
            )

        mlt_hr = np.asarray(ds.variables["mlt_hr"][:], dtype=float)
        clat_deg = np.asarray(ds.variables["cLat_deg"][:], dtype=float)
        pot = np.asarray(ds.variables["Pot"][time_idx], dtype=float)

    theta_deg = np.mod(mlt_hr, 24.0) * 15.0
    theta_deg = np.concatenate([theta_deg, [theta_deg[0] + 360.0]])
    theta = np.deg2rad(theta_deg)
    pot = np.concatenate([pot, pot[:, :1]], axis=1)

    lat = 90.0 - clat_deg
    if hemisphere == "south":
        lat = -lat

    return theta, lat, pot


def overlay_pymix_potential(
    ax: plt.Axes,
    theta: np.ndarray,
    lat: np.ndarray,
    pot: np.ndarray,
    *,
    level_step: float,
    color: str,
    linewidth: float,
    alpha: float,
) -> None:
    max_abs = float(np.nanmax(np.abs(pot)))
    if not np.isfinite(max_abs) or max_abs == 0.0:
        return

    level_step = abs(float(level_step))
    if level_step == 0.0:
        raise ValueError("pymix contour spacing must be non-zero")

    limit = level_step * np.ceil(max_abs / level_step)
    levels = np.arange(-limit, limit + 0.5 * level_step, level_step)
    if levels.size < 2:
        levels = np.array([-level_step, 0.0, level_step])

    ax.contour(
        theta,
        lat,
        pot,
        levels=levels,
        colors=color,
        linewidths=linewidth,
        alpha=alpha,
    )


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
    pymix_dir = Path(args.pymix_dir).expanduser().resolve() if args.pymix_dir else None

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
    ax = plt.gca()

    if pymix_dir is not None:
        if args.hemisphere == "all":
            raise SystemExit("--pymix-dir requires --hemisphere north or south")
        plot_time = datetime(
            record["start.year"],
            record["start.month"],
            record["start.day"],
            record["start.hour"],
            record["start.minute"],
            record["start.second"],
        )
        pymix = load_pymix_slice(
            pymix_dir,
            plot_time,
            args.hemisphere,
            args.pymix_max_time_delta_min,
        )
        if pymix is not None:
            theta, lat, pot = pymix
            overlay_pymix_potential(
                ax,
                theta,
                lat,
                pot,
                level_step=args.pymix_level_step,
                color=args.pymix_color,
                linewidth=args.pymix_linewidth,
                alpha=args.pymix_alpha,
            )

    plt.gcf().savefig(out_path, dpi=180, bbox_inches="tight")

    print(f"output={out_path}")
    print(f"matched_radars={len(matched_files)}")
    print(f"matched_files={','.join(path.name for path in matched_files)}")
    print(f"nvec={int(record['nvec'][0])}")
    if pymix_dir is not None:
        print(f"pymix_dir={pymix_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
