#!/usr/bin/env python3
"""Render a SuperDARN .grid DMAP file to a PNG using pydarn."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import dmap
import pydarn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot a SuperDARN .grid DMAP file.")
    parser.add_argument("grid_file", help="Path to the input .grid file")
    parser.add_argument("-o", "--output", help="Path to the output PNG")
    parser.add_argument(
        "--start-time",
        help="Start time to plot (YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS). Defaults to first record.",
    )
    parser.add_argument("--record", type=int, default=0, help="Record index if --start-time is not provided")
    parser.add_argument("--time-delta", type=int, default=2, help="Minutes around start time for the plot selection")
    parser.add_argument("--parameter", default="vel", help="Grid parameter to plot")
    parser.add_argument("--title", default="", help="Optional plot title override")
    return parser.parse_args()


def load_grid(path: str):
    reader = getattr(dmap, "read_grid_lax", None) or getattr(dmap, "read_grid")
    records = reader(path)
    if isinstance(records, tuple) and len(records) == 2 and isinstance(records[0], list):
        records = records[0]
    return records


def parse_start_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid --start-time format: {value}")


def main() -> int:
    args = parse_args()
    grid_path = Path(args.grid_file).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve() if args.output else grid_path.with_suffix(".png")

    records = load_grid(str(grid_path))
    fig = plt.figure(figsize=(9, 9))
    ax = fig.add_subplot(111)

    start_time = parse_start_time(args.start_time)
    kwargs = {
        "ax": ax,
        "parameter": args.parameter,
        "title": args.title or grid_path.name,
    }
    if start_time is not None:
        kwargs["start_time"] = start_time
        kwargs["time_delta"] = args.time_delta
    else:
        kwargs["record"] = args.record

    pydarn.Grid.plot_grid(records, **kwargs)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
