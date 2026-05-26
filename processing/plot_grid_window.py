#!/usr/bin/env python3
"""Plot a combined SuperDARN GRID DMAP window across many radar files."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import dmap
import pydarn


VECTOR_KEYS = [
    "vector.mlat",
    "vector.mlon",
    "vector.kvect",
    "vector.vel.median",
    "vector.vel.sd",
    "vector.pwr.median",
    "vector.pwr.sd",
    "vector.wdt.median",
    "vector.wdt.sd",
    "vector.srng",
    "vector.stid",
    "vector.channel",
    "vector.index",
    "gsct",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate multiple GRID DMAP files for one time window and render a polar plot."
    )
    parser.add_argument("grid_dir", help="Directory containing .grid files")
    parser.add_argument(
        "--pattern",
        default="*.grid",
        help="Glob pattern within grid_dir (default: *.grid)",
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
        help="Match records starting in [start_time, start_time + window_minutes)",
    )
    parser.add_argument(
        "--hemisphere",
        choices=("north", "south", "all"),
        default="north",
        help="Restrict records by hemisphere (default: north)",
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


def load_grid(path: Path) -> list[dict]:
    reader = getattr(dmap, "read_grid_lax", None) or getattr(dmap, "read_grid")
    records = reader(str(path))
    if isinstance(records, tuple) and len(records) == 2 and isinstance(records[0], list):
        records = records[0]
    return records


def record_start(record: dict) -> datetime:
    return datetime(
        int(record["start.year"]),
        int(record["start.month"]),
        int(record["start.day"]),
        int(record["start.hour"]),
        int(record["start.minute"]),
        int(record["start.second"]),
    )


def record_end(record: dict) -> datetime:
    return datetime(
        int(record["end.year"]),
        int(record["end.month"]),
        int(record["end.day"]),
        int(record["end.hour"]),
        int(record["end.minute"]),
        int(record["end.second"]),
    )


def nvec_value(record: dict) -> int:
    value = record["nvec"]
    return int(value[0] if hasattr(value, "__len__") else value)


def record_hemisphere(record: dict) -> str | None:
    mlats = record.get("vector.mlat")
    if mlats is None or len(mlats) == 0:
        return None
    return "north" if float(mlats[0]) >= 0 else "south"


def within_window(record: dict, start_time: datetime, window_minutes: int) -> bool:
    rec_start = record_start(record)
    return start_time <= rec_start < start_time + timedelta(minutes=window_minutes)


def merge_records(matches: list[tuple[Path, dict]], start_time: datetime) -> dict:
    merged = copy.deepcopy(matches[0][1])
    arrays: dict[str, list[np.ndarray]] = {key: [] for key in VECTOR_KEYS}
    stids: list[int] = []
    end_times: list[datetime] = []

    for path, record in matches:
        del path
        end_times.append(record_end(record))
        stids.extend(int(stid) for stid in np.atleast_1d(record["stid"]))
        for key in VECTOR_KEYS:
            value = record.get(key)
            if value is None:
                continue
            arrays[key].append(np.asarray(value))

    for key, parts in arrays.items():
        if not parts:
            merged[key] = None
            continue
        merged[key] = np.concatenate(parts)

    stid_dtype = matches[0][1]["stid"].dtype if hasattr(matches[0][1]["stid"], "dtype") else np.int16
    nvec_dtype = matches[0][1]["nvec"].dtype if hasattr(matches[0][1]["nvec"], "dtype") else np.int16
    merged["stid"] = np.asarray(sorted(set(stids)), dtype=stid_dtype)
    merged["nvec"] = np.asarray([len(merged["vector.mlat"])], dtype=nvec_dtype)

    end_time = max(end_times)
    merged["start.year"] = start_time.year
    merged["start.month"] = start_time.month
    merged["start.day"] = start_time.day
    merged["start.hour"] = start_time.hour
    merged["start.minute"] = start_time.minute
    merged["start.second"] = start_time.second
    merged["end.year"] = end_time.year
    merged["end.month"] = end_time.month
    merged["end.day"] = end_time.day
    merged["end.hour"] = end_time.hour
    merged["end.minute"] = end_time.minute
    merged["end.second"] = end_time.second

    for prefix in ("vel", "pwr", "wdt"):
        key = f"vector.{prefix}.median"
        if merged.get(key) is None or len(merged[key]) == 0:
            continue
        values = np.asarray(merged[key], dtype=float)
        min_key = f"{prefix[0]}.min" if prefix != "wdt" else "w.min"
        max_key = f"{prefix[0]}.max" if prefix != "wdt" else "w.max"
        if prefix == "vel":
            min_key = "v.min"
            max_key = "v.max"
        elif prefix == "pwr":
            min_key = "p.min"
            max_key = "p.max"
        elif prefix == "wdt":
            min_key = "w.min"
            max_key = "w.max"
        merged[min_key] = np.asarray([np.nanmin(values)], dtype=values.dtype)
        merged[max_key] = np.asarray([np.nanmax(values)], dtype=values.dtype)

    return merged


def find_matching_records(
    files: list[Path], start_time: datetime, window_minutes: int, hemisphere: str
) -> list[tuple[Path, dict]]:
    matches: list[tuple[Path, dict]] = []
    for path in files:
        for record in load_grid(path):
            if nvec_value(record) <= 0:
                continue
            rec_hemi = record_hemisphere(record)
            if hemisphere != "all" and rec_hemi != hemisphere:
                continue
            if within_window(record, start_time, window_minutes):
                matches.append((path, record))
                break
    return matches


def main() -> int:
    args = parse_args()
    grid_dir = Path(args.grid_dir).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(grid_dir.glob(args.pattern))
    if not files:
        raise SystemExit(f"no files matched {args.pattern} in {grid_dir}")

    start_time = parse_time(args.start_time)
    matches = find_matching_records(files, start_time, args.window_minutes, args.hemisphere)
    if not matches:
        raise SystemExit(
            f"no non-empty {args.hemisphere} records matched {start_time.isoformat()} "
            f"within {args.window_minutes} minutes"
        )

    merged = merge_records(matches, start_time)
    plt.figure(figsize=(10, 10))
    title = args.title or (
        f"{args.hemisphere.title()} GRID vectors {start_time:%Y-%m-%d %H:%M} UTC "
        f"({len(matches)} radars, {int(merged['nvec'][0])} vectors)"
    )
    pydarn.Grid.plot_grid([merged], record=0, parameter=args.parameter, title=title)
    plt.gcf().savefig(out_path, dpi=180, bbox_inches="tight")

    print(f"output={out_path}")
    print(f"matched_radars={len(matches)}")
    print(f"matched_files={','.join(path.name for path, _ in matches)}")
    print(f"nvec={int(merged['nvec'][0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
