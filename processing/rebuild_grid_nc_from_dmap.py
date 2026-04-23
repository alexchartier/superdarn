#!/usr/bin/env python3
"""Rebuild GRID netCDF files directly from GRID DMAP files."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import dmap
import netCDF4
import numpy as np

from augment_grid_nc_with_dirn import (
    DIRN_VAR_LONG_NAME,
    DIRN_VAR_UNITS,
    convert_aacgm_to_geo_by_time,
    compute_correct_dirn_values,
)
from fit_to_grid_nc import calc_bearings, def_vars


COPY_VARS = [
    "vector.mlat",
    "vector.mlon",
    "vector.kvect",
    "vector.vel.median",
    "vector.vel.sd",
    "vector.pwr.median",
    "vector.wdt.median",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grid_file", help="Input GRID DMAP file")
    parser.add_argument("template_nc", help="Existing GRID netCDF file to copy metadata from")
    parser.add_argument("output_nc", help="Output GRID netCDF path")
    parser.add_argument("--ref-ht", type=float, default=300.0, help="Reference height in km")
    return parser.parse_args()


def load_grid_records(path: Path) -> list[dict]:
    reader = getattr(dmap, "read_grid_lax", None) or getattr(dmap, "read_grid")
    records = reader(str(path))
    if isinstance(records, tuple) and len(records) == 2 and isinstance(records[0], list):
        records = records[0]
    return records


def datetime_to_mjd(value: datetime) -> float:
    epoch = datetime(1858, 11, 17)
    return (value - epoch).total_seconds() / 86400.0


def record_time(record: dict, prefix: str) -> datetime:
    return datetime(
        int(record[f"{prefix}.year"]),
        int(record[f"{prefix}.month"]),
        int(record[f"{prefix}.day"]),
        int(record[f"{prefix}.hour"]),
        int(record[f"{prefix}.minute"]),
        int(record[f"{prefix}.second"]),
    )


def build_out_vars(records: list[dict], ref_ht: float, attrs: dict[str, object]) -> dict[str, np.ndarray]:
    out_vars = {name: [] for name in COPY_VARS}
    out_vars.update(
        {
            "mjd_start": [],
            "mjd_end": [],
            "vector.glat": [],
            "vector.glon": [],
            "vector.g_kvect": [],
            "vector.vel.dirn": [],
        }
    )

    for record in records:
        if "vector.mlat" not in record:
            continue

        npts = len(record["vector.mlat"])
        if npts == 0:
            continue

        for name in COPY_VARS:
            out_vars[name].append(np.asarray(record[name]))

        mjd_start = datetime_to_mjd(record_time(record, "start"))
        mjd_end = datetime_to_mjd(record_time(record, "end"))
        out_vars["mjd_start"].append(np.full(npts, mjd_start, dtype=float))
        out_vars["mjd_end"].append(np.full(npts, mjd_end, dtype=float))

    for name, parts in out_vars.items():
        if parts:
            out_vars[name] = np.concatenate(parts)
        else:
            dtype = np.int8 if name == "vector.vel.dirn" else np.float64
            out_vars[name] = np.asarray([], dtype=dtype)

    out_vars["vector.glat"], out_vars["vector.glon"] = convert_aacgm_to_geo_by_time(
        out_vars["vector.mlat"],
        out_vars["vector.mlon"],
        out_vars["mjd_start"],
        ref_ht,
    )
    out_vars["vector.g_kvect"] = calc_bearings(
        float(attrs["lat"]),
        float(attrs["lon"]),
        out_vars["vector.glat"],
        out_vars["vector.glon"],
        ref_ht,
    )
    out_vars["vector.vel.dirn"] = compute_correct_dirn_values(
        out_vars["vector.mlat"],
        out_vars["vector.mlon"],
        out_vars["vector.kvect"],
        out_vars["mjd_start"],
        radar_lat=float(attrs["lat"]),
        radar_lon=float(attrs["lon"]),
        radar_alt=float(attrs["alt"]),
    )
    return out_vars


def write_nc(template_nc: Path, output_nc: Path, out_vars: dict[str, np.ndarray]) -> None:
    var_defs = def_vars()

    with netCDF4.Dataset(template_nc) as src, netCDF4.Dataset(output_nc, "w") as dst:
        for attr in src.ncattrs():
            dst.setncattr(attr, src.getncattr(attr))

        dst.createDimension("npts", size=len(out_vars["mjd_start"]))

        for name, defs in var_defs.items():
            src_var = src.variables.get(name)
            dtype = src_var.datatype if src_var is not None else defs["type"]
            dims = src_var.dimensions if src_var is not None else (defs["dims"],)
            dst_var = dst.createVariable(name, dtype, dims)
            dst_var[:] = out_vars[name]
            if src_var is not None:
                dst_var.setncatts({attr: src_var.getncattr(attr) for attr in src_var.ncattrs()})
            else:
                dst_var.units = defs["units"]
                dst_var.long_name = defs["long_name"]


def main() -> int:
    args = parse_args()
    grid_file = Path(args.grid_file).expanduser().resolve()
    template_nc = Path(args.template_nc).expanduser().resolve()
    output_nc = Path(args.output_nc).expanduser().resolve()
    output_nc.parent.mkdir(parents=True, exist_ok=True)

    with netCDF4.Dataset(template_nc) as template:
        attrs = {name: template.getncattr(name) for name in ("lat", "lon", "alt")}

    records = load_grid_records(grid_file)
    out_vars = build_out_vars(records, args.ref_ht, attrs)
    write_nc(template_nc, output_nc, out_vars)
    print(output_nc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
