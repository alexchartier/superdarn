"""
Python port of the meteorproc_batch MATLAB helper.

This module expands filename patterns (similar to filename.m), walks a date
range, executes the meteor-processing routine for each day, and writes the
results into per-day NetCDF files tagged with descriptive attributes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

try:
    from meteorproc_from_netcdf import meteorproc_from_netcdf
    METEORPROC_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - surfaced at runtime
    meteorproc_from_netcdf = None  # type: ignore
    METEORPROC_IMPORT_ERROR = exc


def meteorproc_batch(
    input_pattern: str,
    start_date: dt.date | dt.datetime | str | Sequence[int],
    end_date: dt.date | dt.datetime | str | Sequence[int],
    *,
    output_pattern: str | None = None,
    **meteor_kwargs,
) -> None:
    """
    Run the meteor wind fit for each day in the requested range.

    Parameters
    ----------
    input_pattern : str
        Path to the NetCDF files, using filename.m-style tokens
        (e.g., '~/data/{yyyy}/{mm}/{yyyymmdd}.fir.v2.5.nc').
    start_date, end_date :
        Inclusive bounds of the date range. Accepted forms include datetime/date
        objects, 'YYYYMMDD' strings, 'YYYY-mm-dd' strings, or (Y, M, D) tuples.
    output_pattern : str, optional
        Output NetCDF pattern; defaults to appending '.winds.nc' to the input.
    meteor_kwargs :
        Additional keyword arguments forwarded to meteorproc_from_netcdf.
    """
    if meteorproc_from_netcdf is None:
        raise ImportError(
            "meteorproc_from_netcdf is unavailable. "
            "Ensure a Python implementation is on the path."
        ) from METEORPROC_IMPORT_ERROR

    start = to_datetime(start_date)
    end = to_datetime(end_date)
    if end < start:
        start, end = end, start

    if output_pattern is None:
        output_pattern = input_pattern + ".winds.nc"

    for when in daterange(start, end):
        in_file = expand_path(apply_pattern(input_pattern, when))
        if not in_file:
            continue
        if not Path(in_file).is_file():
            print(f"[meteorproc_batch] Skipping missing input {in_file}")
            continue

        out_file = expand_path(apply_pattern(output_pattern, when))
        print(f"[meteorproc_batch] Processing {in_file} -> {out_file}")
        try:
            results = meteorproc_from_netcdf(in_file, **meteor_kwargs)
        except Exception as exc:  # pragma: no cover - surfaced at runtime
            print(
                f"[meteorproc_batch] meteorproc_from_netcdf failed for {in_file}: {exc}"
            )
            continue

        if results is None:
            print(f"[meteorproc_batch] No results for {in_file}")
            continue

        write_results_netcdf(out_file, results, source_file=in_file)


def daterange(start: dt.datetime, end: dt.datetime) -> Iterable[dt.datetime]:
    current = dt.datetime(start.year, start.month, start.day)
    last = dt.datetime(end.year, end.month, end.day)
    one_day = dt.timedelta(days=1)
    while current <= last:
        yield current
        current += one_day


def to_datetime(value: dt.date | dt.datetime | str | Sequence[int]) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return dt.datetime.strptime(value, fmt)
            except ValueError:
                continue
        raise ValueError(f"Unrecognised date string: {value}")
    if isinstance(value, Sequence) and len(value) >= 3:
        year, month, day = (int(value[0]), int(value[1]), int(value[2]))
        return dt.datetime(year, month, day)
    raise TypeError(f"Unsupported date representation: {value!r}")


def expand_path(raw_path: str) -> str:
    if not raw_path:
        return ""
    expanded = os.path.expanduser(raw_path)
    return os.path.abspath(expanded)


TOKEN_MAP = [
    ("yyyy", "%Y"),
    ("YYYY", "%Y"),
    ("yy", "%y"),
    ("YY", "%y"),
    ("mmm", "%b"),
    ("MMM", "%b"),
    ("mm", "%m"),
    ("dd", "%d"),
    ("HH", "%H"),
    ("hh", "%H"),
    ("MM", "%M"),
    ("SS", "%S"),
]


def apply_pattern(pattern: str, timestamp: dt.datetime) -> str:
    """Expand filename.m-style tokens using the provided datetime."""

    def replace_token(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.upper() == "NAME":
            return ""
        fmt = token
        for src, repl in TOKEN_MAP:
            fmt = fmt.replace(src, repl)
        return timestamp.strftime(fmt)

    return re.sub(r"\{([^}]+)\}", replace_token, pattern)


def write_results_netcdf(
    output_file: str,
    results: Mapping[str, Sequence[float]] | "pandas.DataFrame",
    *,
    source_file: str | None = None,
) -> None:
    """Persist the hourly results into a simple NetCDF file."""
    data = normalise_results(results)
    if not data:
        print(f"[meteorproc_batch] No variables to write for {output_file}")
        return

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    npts = len(next(iter(data.values())))
    meta = variable_metadata()

    with Dataset(out_path, "w") as nc:
        nc.createDimension("record", npts)
        for name, values in data.items():
            arr = np.asarray(values)
            var = nc.createVariable(name, arr.dtype, ("record",))
            var[:] = arr
            attrs = meta.get(name, {})
            for key, val in attrs.items():
                setattr(var, key, val)

        nc.description = "Hourly meteor winds from meteorproc"
        nc.generated = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        if source_file:
            nc.source = source_file


def normalise_results(
    results: Mapping[str, Sequence[float]] | "pandas.DataFrame",
) -> Dict[str, Sequence[float]]:
    if hasattr(results, "to_dict"):  # pandas DataFrame
        data = {col: np.asarray(results[col]) for col in results.columns}  # type: ignore
    else:
        data = {key: np.asarray(val) for key, val in results.items()}
    return data


def variable_metadata() -> Dict[str, Dict[str, str]]:
    return {
        "year": {"long_name": "Calendar year", "units": "year"},
        "month": {"long_name": "Month of year", "units": "month"},
        "day": {"long_name": "Day of month", "units": "day"},
        "hour": {"long_name": "Hour (UT)", "units": "hour"},
        "num_avgs": {
            "long_name": "Number of vlos samples included in averages",
            "units": "count",
        },
        "frang": {"long_name": "First range gate", "units": "km"},
        "rsep": {"long_name": "Range separation", "units": "km"},
        "vx": {
            "long_name": "Meridional wind component (positive southward)",
            "units": "m/s",
        },
        "vy": {
            "long_name": "Zonal wind component (positive eastward)",
            "units": "m/s",
        },
        "lat": {"long_name": "Geographic latitude of fit", "units": "deg"},
        "lon": {"long_name": "Geographic longitude of fit", "units": "deg"},
        "vm": {"long_name": "Line-of-sight velocity on vm beam", "units": "m/s"},
        "vm_lat": {"long_name": "Latitude of vm beam intersection", "units": "deg"},
        "vm_lon": {"long_name": "Longitude of vm beam intersection", "units": "deg"},
        "sdev_vx": {"long_name": "Uncertainty of Vx", "units": "m/s"},
        "sdev_vy": {"long_name": "Uncertainty of Vy", "units": "m/s"},
    }


def parse_cli_options(values: Sequence[str]) -> Dict[str, object]:
    options: Dict[str, object] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Option '{item}' must be in key=value form.")
        key, raw = item.split("=", 1)
        options[key] = auto_convert(raw)
    return options


def auto_convert(raw: str) -> object:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover - CLI glue
    parser = argparse.ArgumentParser(description="Batch meteor wind processing.")
    parser.add_argument("input_pattern")
    parser.add_argument("start_date")
    parser.add_argument("end_date")
    parser.add_argument(
        "--output-pattern",
        default=None,
        help="Optional pattern for output files (defaults to input + '.winds.nc').",
    )
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        help="Extra key=value pairs forwarded to meteorproc_from_netcdf.",
    )
    args = parser.parse_args(argv)
    extra = parse_cli_options(args.option)
    meteorproc_batch(
        args.input_pattern,
        args.start_date,
        args.end_date,
        output_pattern=args.output_pattern,
        **extra,
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
