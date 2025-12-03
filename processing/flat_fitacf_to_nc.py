#!/usr/bin/env python3
"""
Flat fitACF -> netCDF converter.

This script walks a fitACF directory tree (e.g., ~/data/superdarn/fitacf/2005/01/)
and writes one netCDF file per fitACF input while keeping every scalar and vector
field. Vector fields are stored as 1D variables; accompanying record/element
index vectors make it possible to reconstruct per-record groupings. Scalar fields
are stored as netCDF attributes (one element per record) to keep the payload flat.

Field names and meanings follow the RST fitACF documentation:
https://radar-software-toolkit-rst.readthedocs.io/en/latest/references/general/fitacf/
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

import numpy as np

# Attempt to import pyDARNio; fall back to a common local checkout path.
try:
    from pydarnio import SDarnRead
except ImportError:  # pragma: no cover - optional path tweak
    sys.path.append(os.path.expanduser('~/pyDARNio'))
    from pydarnio import SDarnRead  # type: ignore

# netCDF4 imports HDF5; import after pyDARNio to avoid HDF5 version conflicts
# with h5py pulled in by pyDARNio's borealis module.
import netCDF4

RST_REFERENCE_URL = "https://radar-software-toolkit-rst.readthedocs.io/en/latest/references/general/fitacf/"

# Lightweight field metadata pulled from the RST reference. Missing entries fall
# back to the raw field name.
FIELD_DESCRIPTIONS: Dict[str, Tuple[str, str]] = {
    "atten": ("attenuation setting", "dB"),
    "bmazm": ("beam azimuth", "degrees"),
    "bmnum": ("beam number", "count"),
    "channel": ("IF channel", "index"),
    "cp": ("control program ID", "code"),
    "ercod": ("error flag code", "code"),
    "fitacf.revision.major": ("fitacf major revision", "version"),
    "fitacf.revision.minor": ("fitacf minor revision", "version"),
    "frang": ("first range", "km"),
    "gflg": ("ground scatter flag", "flag"),
    "ifmode": ("IF mode", "code"),
    "intt.sc": ("integration time (seconds)", "s"),
    "intt.us": ("integration time (microseconds)", "us"),
    "lagfr": ("lag to first range", "us"),
    "ltab": ("lag table", "lag"),
    "lvmax": ("maximum lag to search", "lag"),
    "mpinc": ("pulse separation", "us"),
    "mplgexs": ("number of additional lags", "count"),
    "mplgs": ("number of lags", "count"),
    "mppul": ("pulses in sequence", "count"),
    "mxpwr": ("max power threshold", "dB"),
    "nave": ("number of averages", "count"),
    "nlag": ("number of lags in fit", "count"),
    "noise.lag0": ("lag 0 noise", "dB"),
    "noise.mean": ("mean noise", "dB"),
    "noise.search": ("search noise", "dB"),
    "noise.sky": ("sky noise", "dB"),
    "noise.vel": ("noise velocity", "m/s"),
    "nrang": ("number of ranges", "count"),
    "offset": ("phase offset", "degrees"),
    "origin.code": ("origin code", "code"),
    "origin.command": ("originating command", "string"),
    "origin.time": ("time of origin command", "string"),
    "p_l": ("lambda power", "dB"),
    "p_l_e": ("lambda power error", "dB"),
    "p_s": ("sigma power", "dB"),
    "p_s_e": ("sigma power error", "dB"),
    "ptab": ("pulse table", "sequence"),
    "pwr0": ("lag 0 power", "dB"),
    "qflg": ("quality flag", "flag"),
    "radar.revision.major": ("radar hardware major revision", "version"),
    "radar.revision.minor": ("radar hardware minor revision", "version"),
    "rsep": ("range separation", "km"),
    "rxrise": ("receiver rise time", "us"),
    "scan": ("scan flag (1 fwd, -1 rev)", "flag"),
    "sd_l": ("lambda spectral width", "m/s"),
    "sd_phi": ("phi spectral width", "deg"),
    "sd_s": ("sigma spectral width", "m/s"),
    "slist": ("list of ranges with fitted ACF", "range"),
    "smsep": ("beam separation", "deg"),
    "stat.agc": ("AGC status", "flag"),
    "stat.lopwr": ("low power status", "flag"),
    "stid": ("station ID", "code"),
    "tfreq": ("transmit frequency", "kHz"),
    "time.dy": ("day of month", "day"),
    "time.hr": ("hour", "hour"),
    "time.mo": ("month", "month"),
    "time.mt": ("minute", "minute"),
    "time.sc": ("second", "second"),
    "time.us": ("microsecond", "us"),
    "time.yr": ("year", "year"),
    "txpl": ("transmit pulse length", "us"),
    "txpow": ("transmit power", "W"),
    "v": ("line-of-sight velocity", "m/s"),
    "v_e": ("line-of-sight velocity error", "m/s"),
    "w_l": ("lambda spectral width", "m/s"),
    "w_l_e": ("lambda spectral width error", "m/s"),
    "w_s": ("sigma spectral width", "m/s"),
    "w_s_e": ("sigma spectral width error", "m/s"),
    "xcf": ("cross-correlation flag", "flag"),
}


def is_vector(value: object) -> bool:
    """Return True for DMAP array-like payloads (ndarray/list/tuple)."""
    return isinstance(value, (list, tuple, np.ndarray))


def infer_attr_fill(value: object):
    """Pick a fill value matching the scalar type."""
    if isinstance(value, (str, bytes)):
        return ""
    if isinstance(value, (bool, np.bool_)):
        return False
    if isinstance(value, (float, np.floating)):
        return np.nan
    if isinstance(value, (np.integer, int)):
        return np.iinfo(np.int64).min
    return ""


def convert_file(in_path: str, out_path: str) -> None:
    """Convert one fitACF file to a flat netCDF."""
    records = SDarnRead(in_path).read_fitacf()
    if not records:
        print(f"Skipping empty file {in_path}")
        return

    n_records = len(records)
    scalar_fields, vector_fields = classify_fields(records)

    # Prepare scalar storage with per-record fill values.
    scalar_storage: Dict[str, List[object]] = {}
    scalar_fill: Dict[str, object] = {}
    for field in scalar_fields:
        first_val = next(
            (rec[field] for rec in records if field in rec),
            None,
        )
        if first_val is None:
            continue
        scalar_fill[field] = infer_attr_fill(first_val)
        scalar_storage[field] = [scalar_fill[field]] * n_records

    # Fill scalar values in record order.
    for rec_idx, rec in enumerate(records):
        for field in scalar_fields:
            if field not in rec or field not in scalar_storage:
                continue
            scalar_storage[field][rec_idx] = rec[field]

    # Flatten vector fields.
    vector_storage: Dict[str, Dict[str, List[object]]] = {}
    for field in vector_fields:
        vector_storage[field] = {
            "values": [],
            "record_index": [],
            "element_index": [],
        }

    for rec_idx, rec in enumerate(records):
        for field in vector_fields:
            if field not in rec:
                continue
            arr = np.asarray(rec[field]).ravel()
            vector_storage[field]["values"].extend(arr.tolist())
            vector_storage[field]["record_index"].extend([rec_idx] * arr.size)
            vector_storage[field]["element_index"].extend(
                list(range(arr.size))
            )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with netCDF4.Dataset(out_path, "w") as nc:
        nc.description = (
            "Flat SuperDARN fitACF export: scalar fields as attributes, "
            "vector fields as 1D variables."
        )
        nc.fitacf_source = in_path
        nc.history = f"Created {datetime.utcnow().isoformat()}Z"
        nc.reference = RST_REFERENCE_URL
        nc.n_records = n_records

        # Store scalar sequences as attributes (one element per record).
        for field, values in scalar_storage.items():
            nc.setncattr(field, np.asarray(values))

        # Store vector payloads as 1D variables with record/element indices.
        for field, payload in vector_storage.items():
            dim_name = f"{field.replace('.', '_')}_n"
            values = np.asarray(payload["values"])
            nc.createDimension(dim_name, size=values.size)

            var = nc.createVariable(field, values.dtype, (dim_name,))
            var[:] = values
            long_name, units = FIELD_DESCRIPTIONS.get(
                field, (field, "unspecified")
            )
            var.long_name = long_name
            var.units = units

            rec_idx_var = nc.createVariable(
                f"{field}_record_index", "i4", (dim_name,)
            )
            rec_idx_var[:] = np.asarray(payload["record_index"], dtype="i4")
            rec_idx_var.long_name = "record index for each element"
            rec_idx_var.units = "index"

            elem_idx_var = nc.createVariable(
                f"{field}_element_index", "i4", (dim_name,)
            )
            elem_idx_var[:] = np.asarray(payload["element_index"], dtype="i4")
            elem_idx_var.long_name = "element index within record"
            elem_idx_var.units = "index"

    print(f"Wrote {out_path}")


def classify_fields(records: Iterable[dict]) -> Tuple[set, set]:
    """Split fields into scalar vs vector buckets."""
    scalar_fields: set = set()
    vector_fields: set = set()
    for rec in records:
        for key, val in rec.items():
            if is_vector(val):
                vector_fields.add(key)
            else:
                scalar_fields.add(key)
    # If a key ever appears as a vector, treat it as vector.
    scalar_fields -= vector_fields
    return scalar_fields, vector_fields


def should_convert(filename: str) -> bool:
    """Check if a filename looks like a fitACF file."""
    lower = filename.lower()
    return lower.endswith(
        (".fit", ".fitacf", ".fitacf2", ".fitacf3", ".despeckled.fit")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert fitACF files to flat netCDF."
    )
    parser.add_argument(
        "--input-root",
        default=os.path.expanduser("~/data/superdarn/fitacf"),
        help="Root directory containing fitACF files (default: %(default)s).",
    )
    parser.add_argument(
        "--output-root",
        default=os.path.expanduser("~/data/superdarn/fitacf_nc_flat"),
        help="Destination root for netCDF output (default: %(default)s).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing netCDF files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    in_root = os.path.abspath(os.path.expanduser(args.input_root))
    out_root = os.path.abspath(os.path.expanduser(args.output_root))

    for dirpath, _, filenames in os.walk(in_root):
        for fname in filenames:
            if not should_convert(fname):
                continue
            in_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(in_path, in_root)
            out_fname = os.path.splitext(rel)[0] + ".nc"
            out_path = os.path.join(out_root, out_fname)
            if os.path.exists(out_path) and not args.overwrite:
                print(f"Skipping existing {out_path}")
                continue
            convert_file(in_path, out_path)


if __name__ == "__main__":
    main()
