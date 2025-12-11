"""
Convert meteor NetCDF files to hourly wind NetCDFs.

This merges the functionality of meteorproc_from_netcdf (single-file
conversion) and meteorproc_batch (date-ranged batch processing) into one
module. Use meteorproc_batch() or the CLI to walk date ranges; use
meteorproc_from_netcdf() to convert a single file to a pandas DataFrame, or
meteorproc() directly if you already have CFIT-style records.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import math
import os
import re
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

import numpy as np
import pandas as pd
from netCDF4 import Dataset


# -----------------------------
# Single-file conversion
# -----------------------------

def meteorproc_from_netcdf(
    ncfile: str | os.PathLike[str],
    *,
    radar_code: str | None = None,
    site: Mapping[str, Any] | None = None,
    **meteor_kwargs: Any,
) -> pd.DataFrame:
    """
    Run meteor wind fitting on a NetCDF meteor catalog and return a DataFrame.

    Parameters
    ----------
    ncfile : path-like
        Path to the NetCDF file (e.g., ~/data/.../20190113.fir.v2.5.nc).
    radar_code : str, optional
        Three-letter radar code; if omitted it is inferred from the filename.
    site : mapping, optional
        Override site metadata normally read from the NetCDF attributes.
    meteor_kwargs :
        Additional keyword arguments forwarded to :func:`meteorproc`.
    """
    nc_path = Path(ncfile)
    radar_code = radar_code or infer_code(nc_path)

    file_data = read_meteor_netcdf(nc_path)
    site_struct = dict(site) if site else build_site_from_attributes(nc_path, file_data, radar_code)
    records = build_meteor_records(file_data, site_struct)

    meteor_kwargs = dict(meteor_kwargs)
    meteor_kwargs.setdefault("SourceName", str(nc_path))
    return meteorproc(records, site_struct, **meteor_kwargs)


def read_meteor_netcdf(ncfile: Path) -> Dict[str, np.ndarray]:
    """Load the needed variables and derived values from the NetCDF."""
    with Dataset(ncfile) as nc:
        data: Dict[str, np.ndarray] = {
            "mjd": np.asarray(nc.variables["mjd"][:], dtype=float),
            "beam": np.asarray(nc.variables["beam"][:], dtype=int),
            "range": np.asarray(nc.variables["range"][:], dtype=float),
            "v": np.asarray(nc.variables["v"][:], dtype=float),
            "p_l": np.asarray(nc.variables["p_l"][:], dtype=float),
            "v_e": np.asarray(nc.variables["v_e"][:], dtype=float),
        }

    data["epoch"] = (data["mjd"] - 40587.0) * 86400.0
    data["time_key"] = np.round(data["epoch"] * 1000).astype(np.int64)  # milliseconds

    unique_range = np.unique(data["range"])
    if unique_range.size < 2:
        raise ValueError("Unable to determine range separation from NetCDF file.")
    data["frang"] = float(unique_range[0])
    data["rsep"] = float(unique_range[1] - unique_range[0])
    data["gate"] = np.rint((data["range"] - data["frang"]) / data["rsep"]).astype(np.int32)
    data["num_points"] = data["mjd"].size
    return data


def build_meteor_records(data: Mapping[str, np.ndarray], site: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Group echoes by time/beam and build CFIT-style records."""
    groups: "OrderedDict[tuple[int, int], List[int]]" = OrderedDict()
    for idx, key in enumerate(zip(data["time_key"], data["beam"])):
        groups.setdefault(tuple(key), []).append(idx)

    records: List[Dict[str, Any]] = []
    for indices in groups.values():
        ranges = data["gate"][indices]
        vel = data["v"][indices]
        snr = data["p_l"][indices]
        verr = data["v_e"][indices]
        beam = int(data["beam"][indices[0]])

        rec = {
            "time": float(data["epoch"][indices[0]]),
            "scan": 0,
            "bmnum": beam,
            "frang": float(data["frang"]),
            "rsep": float(data["rsep"]),
            "rxrise": float(site.get("recrise", 0) or 0),
            "num": len(indices),
            "rng": ranges.astype(int),
            "data": [],
        }

        rec["data"] = [
            {"v": float(v), "p_l": float(s), "v_e": float(e), "w_l": 0.0}
            for v, s, e in zip(vel, snr, verr)
        ]
        records.append(rec)

    return records


def build_site_from_attributes(
    ncfile: Path, data: Mapping[str, np.ndarray], radar_code: str
) -> Dict[str, Any]:
    """Derive site metadata from NetCDF global attributes."""
    with Dataset(ncfile) as nc:
        attrs = {name: nc.getncattr(name) for name in nc.ncattrs()}

    def attr(name: str, default: Any) -> Any:
        return attrs.get(name, default)

    bmsep = float(attr("bmsep", math.nan))
    boresite = float(attr("boresight", math.nan))
    geolat = float(attr("lat", math.nan))
    geolon = float(attr("lon", math.nan))
    alt = float(attr("alt", 0))
    beam_list = np.asarray(attr("beams", []))
    beam_az_deg = np.asarray(attr("brng_at_15deg_el", []))

    if math.isnan(bmsep) or math.isnan(boresite):
        raise ValueError("NetCDF file is missing bmsep or boresight attributes.")
    if math.isnan(geolat) or math.isnan(geolon):
        warnings.warn(
            "lat/lon attributes not found; using 0 for geographic position.",
            RuntimeWarning,
        )
        geolat = 0.0
        geolon = 0.0

    if beam_list.size == 0:
        beam_list = np.unique(data["beam"])

    site: Dict[str, Any] = {
        "code": str(radar_code).lower(),
        "bmsep": bmsep,
        "boresite": boresite,
        "maxbeam": int(len(beam_list)),
        "geolat": geolat,
        "geolon": geolon,
        "alt": alt,
        "recrise": 0.0,
    }

    if beam_az_deg.size > 0:
        site["beam_azimuths_rad"] = np.deg2rad(beam_az_deg.astype(float))

    return site


# -----------------------------
# Meteor wind solver (Python port of meteorproc.m)
# -----------------------------

def meteorproc(
    records: Sequence[Mapping[str, Any]],
    site: Mapping[str, Any],
    **kwargs: Any,
) -> pd.DataFrame:
    """Estimate horizontal meteor winds from CFIT-style records."""
    required = {"bmsep", "boresite", "maxbeam", "geolat", "recrise"}
    missing = required - set(site.keys())
    if missing:
        raise ValueError(f"site struct is missing required fields: {', '.join(sorted(missing))}")

    opts: Dict[str, Any] = {
        "MaxVelocity": 100.0,
        "MinSN": 3.0,
        "MaxVelocityErr": 50.0,
        "MaxLineWidth": 25.0,
        "MaxRange": 405.0,
        "BeamNumber": None,
        "MinBeams": 5,
        "BeamType": "meridional",
        "RequestedHour": None,
        "PositionFunction": None,
        "SourceName": "",
    }
    opts.update(kwargs)

    beam_type = str(opts["BeamType"]).lower()
    if beam_type not in {"meridional", "zonal"}:
        raise ValueError("BeamType must be 'meridional' or 'zonal'.")

    METEOR_HEIGHT = 95.0
    mxbm = int(site["maxbeam"])

    num = np.zeros(24, dtype=int)
    met: List[List[Dict[str, Any]]] = [[] for _ in range(24)]
    frang_val = None
    rsep_val = None
    vm_beam = opts.get("BeamNumber")

    for rec in records:
        if frang_val is None:
            frang_val = rec["frang"]
            rsep_val = rec["rsep"]
            if vm_beam is None:
                if site["geolat"] > 0:
                    bstp = site["boresite"] / site["bmsep"]
                    vm_beam_calc = round(site["maxbeam"] / 2.0 - 0.5 - bstp)
                else:
                    bstp = (180.0 - site["boresite"]) / site["bmsep"]
                    vm_beam_calc = round(site["maxbeam"] / 2.0 - 0.5 + bstp)
                vm_beam = max(0, min(int(site["maxbeam"]) - 1, int(vm_beam_calc)))

        yr, mo, dy, hr, mt, sc = epoch_to_date(rec["time"])
        requested_hour = opts.get("RequestedHour")
        if requested_hour is not None and hr != int(requested_hour):
            continue
        if rec.get("scan", 0) < 0 or rec["frang"] == 0 or rec["rsep"] == 0:
            continue

        hour_idx = hr
        entry: Dict[str, Any] = {
            "yr": yr,
            "mo": mo,
            "dy": dy,
            "hr": hr,
            "mt": mt,
            "sc": sc,
            "bmnum": rec["bmnum"],
            "frang": rec["frang"],
            "rsep": rec["rsep"],
            "rxrise": rec.get("rxrise", 0.0),
        }
        if entry["rxrise"] == 0:
            entry["rxrise"] = site["recrise"]

        entry["max_gate"] = int(math.floor((opts["MaxRange"] - rec["frang"]) / rec["rsep"]))
        if entry["max_gate"] <= 0:
            continue

        entry["flg"] = np.zeros(entry["max_gate"], dtype=bool)
        entry["vlos"] = np.zeros(entry["max_gate"], dtype=float)

        for echo, gate in zip(rec["data"], rec["rng"]):
            gate_idx = int(gate)
            if gate_idx >= entry["max_gate"]:
                continue
            if abs(echo["v"]) > opts["MaxVelocity"]:
                continue
            if echo["p_l"] < opts["MinSN"]:
                continue
            if echo["v_e"] >= opts["MaxVelocityErr"]:
                continue
            if echo["w_l"] > opts["MaxLineWidth"]:
                continue
            entry["flg"][gate_idx] = True
            entry["vlos"][gate_idx] = echo["v"]

        cnt = num[hour_idx]
        met[hour_idx].append(entry)
        num[hour_idx] = cnt + 1

    if frang_val is None:
        warnings.warn("No valid records were ingested.")
        return pd.DataFrame()

    coseps = calc_coseps(opts["MaxRange"] / 2.0, METEOR_HEIGHT)
    print(f"# Vlos(max)={opts['MaxVelocity']:.2f}")
    print(f"# S/N(min)={opts['MinSN']:.2f}")
    print(f"# range(max)={opts['MaxRange']:.0f}")
    print(f"# Verr(max)={opts['MaxVelocityErr']:.2f}")
    print(f"# num_beams(min)={int(opts['MinBeams'])}")
    print(f"# w_l(max)={opts['MaxLineWidth']:.2f}")
    if beam_type == "meridional":
        print(f"# beam_num={int(vm_beam)}")
        print("# wind=meridional")
    else:
        print(f"# beam_num={int(vm_beam)}")
        print("# wind=zonal")
    src_str = str(opts.get("SourceName", "")).strip()
    if src_str:
        print(f"# source={src_str}")
    else:
        print("# source=unknown")
    print("# year month day hour num_avgs frang rsep Vx Vy lat long Vm Vm_lat Vm_long sdev_Vx sdev_Vy")

    rows: List[Dict[str, float]] = []
    hour_iter: Iterable[int] = range(24) if opts.get("RequestedHour") is None else [int(opts["RequestedHour"])]

    for hr in hour_iter:
        entries = met[hr]
        cnt = len(entries)
        if cnt == 0:
            continue

        bm_total = np.zeros(mxbm, dtype=float)
        bm_count = np.zeros(mxbm, dtype=int)
        bm_sdtmp = np.zeros(mxbm, dtype=float)

        num_avgs = 0
        for entry in entries:
            beam_idx = int(entry["bmnum"])
            for gate in range(entry["max_gate"]):
                if not entry["flg"][gate]:
                    continue
                bm_total[beam_idx] += entry["vlos"][gate]
                bm_count[beam_idx] += 1
                num_avgs += 1

        vlos = np.zeros(mxbm, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            mask = bm_count > 0
            vlos[mask] = bm_total[mask] / bm_count[mask]

        for entry in entries:
            beam_idx = int(entry["bmnum"])
            for gate in range(entry["max_gate"]):
                if not entry["flg"][gate]:
                    continue
                diff = entry["vlos"][gate] - vlos[beam_idx]
                bm_sdtmp[beam_idx] += diff * diff

        sdev = np.ones(mxbm, dtype=float)
        for ii in range(mxbm):
            if bm_count[ii] > 1:
                sdev[ii] = math.sqrt(bm_sdtmp[ii] / (bm_count[ii] - 1))
            else:
                vlos[ii] = 0.0

        beams_used = int(np.sum(bm_count > 1))
        if beams_used < int(opts["MinBeams"]):
            warnings.warn(
                f"Hour {hr:02d} skipped: only {beams_used} beams with >=2 echoes.",
                RuntimeWarning,
            )
            continue

        valid_idx = np.where(bm_count > 1)[0]
        bc = valid_idx.size
        azimuth = np.zeros(bc, dtype=float)
        y = np.zeros(bc, dtype=float)
        sig = np.zeros(bc, dtype=float)

        for kk, beam_idx in enumerate(valid_idx):
            beam_num = int(beam_idx)
            azimuth[kk] = calc_azi(beam_num, site)
            y[kk] = vlos[beam_idx] / coseps
            sig[kk] = sdev[beam_idx]

        print(f"Fitting {bc} of {mxbm} beams")

        design = np.column_stack((-np.cos(azimuth), np.sin(azimuth)))
        weights = 1.0 / np.maximum(sig**2, np.finfo(float).eps)
        normal = design.T @ (design * weights[:, None])
        rhs = design.T @ (weights * y)

        try:
            if not np.isfinite(np.linalg.cond(normal)) or np.linalg.cond(normal) > 1 / np.finfo(float).eps:
                coeffs = np.linalg.pinv(normal) @ rhs
            else:
                coeffs = np.linalg.solve(normal, rhs)
        except np.linalg.LinAlgError:
            coeffs = np.linalg.pinv(normal) @ rhs

        vx = float(coeffs[0])
        vy = float(coeffs[1])
        residuals = ((design @ coeffs) - y) * np.sqrt(weights)
        _chisq = float(np.sum(residuals**2))

        cvm = np.linalg.pinv(normal)
        sdvx = math.sqrt(max(float(cvm[0, 0]), 0.0))
        sdvy = math.sqrt(max(float(cvm[1, 1]), 0.0))

        vm_beam_idx = min(int(vm_beam) if vm_beam is not None else 0, len(vlos) - 1)
        vm = vlos[vm_beam_idx] / coseps

        frang_out = entries[0]["frang"]
        rsep_out = entries[0]["rsep"]
        rxrise_out = entries[0]["rxrise"]

        if callable(opts.get("PositionFunction")):
            pos_func: Callable[..., Sequence[float]] = opts["PositionFunction"]
            _, lat, lon = pos_func(0, 7, 3, site, frang_out, rsep_out, rxrise_out, METEOR_HEIGHT)
            _, vmlat, vmlon = pos_func(0, vm_beam_idx, 3, site, frang_out, rsep_out, rxrise_out, METEOR_HEIGHT)
        else:
            lat = math.nan
            lon = math.nan
            vmlat = math.nan
            vmlon = math.nan

        print(
            f"{entries[0]['yr']:4d} {entries[0]['mo']:02d} {entries[0]['dy']:02d} "
            f"{hr:02d} {num_avgs} {int(frang_out)} {int(rsep_out)} "
            f"{vx:.0f} {vy:.0f} {lat:.1f} {lon:.1f} {vm:.0f} {vmlat:.1f} {vmlon:.1f} "
            f"{sdvx:.2f} {sdvy:.2f}"
        )

        rows.append(
            {
                "year": entries[0]["yr"],
                "month": entries[0]["mo"],
                "day": entries[0]["dy"],
                "hour": hr,
                "num_avgs": num_avgs,
                "frang": frang_out,
                "rsep": rsep_out,
                "vx": vx,
                "vy": vy,
                "lat": lat,
                "lon": lon,
                "vm": vm,
                "vm_lat": vmlat,
                "vm_lon": vmlon,
                "sdev_vx": sdvx,
                "sdev_vy": sdvy,
            }
        )

    return pd.DataFrame(rows)


def epoch_to_date(epoch: float) -> tuple[int, int, int, int, int, int]:
    ts = dt.datetime.utcfromtimestamp(epoch)
    return ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second


def calc_coseps(rng: float, height: float) -> float:
    if rng <= height:
        rng = height + 1e-6
    eps_ang = math.asin(height / rng)
    return math.cos(eps_ang)


def calc_azi(bmnum: int, site: Mapping[str, Any]) -> float:
    az_list = site.get("beam_azimuths_rad")
    if az_list is not None and len(az_list) > bmnum:
        return float(az_list[bmnum])
    azi_deg = site["bmsep"] * (bmnum - 7.5) + site["boresite"]
    return float(azi_deg) * math.pi / 180.0


def days_in_year(year: int) -> int:
    return 366 if ((year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)) else 365


def infer_code(ncfile: Path) -> str:
    name = ncfile.stem
    parts = name.split(".")
    if len(parts) >= 2:
        return parts[1]
    return "fir"


# -----------------------------
# Batch driver and helpers
# -----------------------------

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


def meteorproc_batch(
    input_dir: str,
    start_date: dt.date | dt.datetime | str | Sequence[int] | None,
    end_date: dt.date | dt.datetime | str | Sequence[int] | None,
    *,
    output_dir: str,
    annual_dir: str | None = None,
    make_annual: bool = False,
    **meteor_kwargs,
) -> None:
    """
    Run the meteor wind fit for each day in the requested range.

    Parameters
    ----------
    input_dir : str
        Directory template containing daily NetCDF files
        (strftime/filename.m-style tokens allowed, e.g., '~/data/netcdf/{yyyy}/{mm}').
    start_date, end_date :
        Inclusive bounds of the date range.
    output_dir : str
        Directory template for wind NetCDF outputs (tokens allowed).
    annual_dir : str, optional
        Directory root for annual per-radar NetCDFs (tokens allowed, defaults to output_dir).
    make_annual : bool
        When true, aggregate processed days into annual per-radar files resembling legacy outputs.
    meteor_kwargs :
        Additional keyword arguments forwarded to meteorproc_from_netcdf.
    """
    if start_date is None and end_date is None:
        dates = find_available_dates(input_dir)
        if not dates:
            print(f"[meteorproc_batch] No dates found under {input_dir}")
            return
    else:
        start = to_datetime(start_date) if start_date is not None else to_datetime(end_date)
        end = to_datetime(end_date) if end_date is not None else to_datetime(start_date)
        if end < start:
            start, end = end, start
        dates = list(daterange(start, end))

    annual_root_template = annual_dir if annual_dir is not None else output_dir
    annual_map: Dict[tuple[str, int], Dict[str, Any]] = {}

    for when in dates:
        day_str = when.strftime("%Y%m%d")
        in_root = Path(expand_path(apply_pattern(input_dir, when)))
        out_root = Path(expand_path(apply_pattern(output_dir, when)))

        if not in_root.is_dir():
            print(f"[meteorproc_batch] Skipping {in_root} (not a directory)")
            continue

        matches = sorted(in_root.glob(f"{day_str}*.nc"))
        if not matches:
            print(f"[meteorproc_batch] No inputs matching {day_str}*.nc in {in_root}")
            continue

        out_root.mkdir(parents=True, exist_ok=True)

        for in_file in matches:
            out_name = in_file.name
            if out_name.endswith(".nc"):
                out_name = out_name[:-3] + ".winds.nc"
            else:
                out_name = out_name + ".winds.nc"
            out_file = out_root / out_name

            print(f"[meteorproc_batch] Processing {in_file} -> {out_file}")
            try:
                results = meteorproc_from_netcdf(in_file, **meteor_kwargs)
            except Exception as exc:
                print(f"[meteorproc_batch] meteorproc_from_netcdf failed for {in_file}: {exc}")
                continue

            if results is None or len(results) == 0:
                print(f"[meteorproc_batch] No results for {in_file}")
                continue

            write_results_netcdf(str(out_file), results, source_file=str(in_file))

            if make_annual:
                try:
                    update_annual_map(annual_map, results, in_file)
                except Exception as exc:
                    print(f"[meteorproc_batch] Failed to aggregate {in_file}: {exc}")

    if make_annual and annual_map:
        write_annual_outputs(annual_map, annual_root_template)


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


def glob_pattern_from_template(template: str) -> str:
    """Replace token blocks with '*' for filesystem globbing."""
    return re.sub(r"\{[^}]+\}", "*", template)


def find_available_dates(input_dir_template: str) -> List[dt.datetime]:
    """Scan input directory template for files with YYYYMMDD in the name."""
    glob_dir = expand_path(glob_pattern_from_template(input_dir_template))
    dates: List[dt.datetime] = []
    for root_str in sorted(glob.glob(glob_dir)):
        root = Path(root_str)
        if not root.is_dir():
            continue
        for f in root.glob("*.nc"):
            m = re.search(r"(\d{8})", f.name)
            if not m:
                continue
            try:
                dt_obj = dt.datetime.strptime(m.group(1), "%Y%m%d")
                dates.append(dt_obj)
            except ValueError:
                continue
    # Deduplicate and sort
    unique_dates = sorted({d for d in dates})
    return unique_dates


def write_results_netcdf(
    output_file: str,
    results: Mapping[str, Sequence[float]] | "pd.DataFrame",
    *,
    source_file: str | None = None,
) -> None:
    """Persist the hourly results into a simple NetCDF file."""
    data = normalise_results(results)
    data = legacy_wind_mapping(data)
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
    results: Mapping[str, Sequence[float]] | "pd.DataFrame",
) -> Dict[str, Sequence[float]]:
    if hasattr(results, "to_dict"):  # pandas DataFrame
        data = {col: np.asarray(results[col]) for col in results.columns}  # type: ignore
    else:
        data = {key: np.asarray(val) for key, val in results.items()}
    return data


def legacy_wind_mapping(data: Dict[str, Sequence[float]]) -> Dict[str, Sequence[float]]:
    """Map vx/vy naming to legacy v/u with vy sign flipped."""
    mapped = dict(data)
    if "vx" in mapped:
        mapped["v"] = np.asarray(mapped["vx"], dtype=float)
    if "vy" in mapped:
        mapped["u"] = -np.asarray(mapped["vy"], dtype=float)
    if "sdev_vx" in mapped:
        mapped["sdev_v"] = np.asarray(mapped["sdev_vx"], dtype=float)
    if "sdev_vy" in mapped:
        mapped["sdev_u"] = np.asarray(mapped["sdev_vy"], dtype=float)
    return mapped


def update_annual_map(
    annual_map: Dict[tuple[str, int], Dict[str, Any]],
    results: "pd.DataFrame",
    source_path: Path,
) -> None:
    data_raw = normalise_results(results)
    data = legacy_wind_mapping(data_raw)

    if not {"year", "month", "day"}.issubset(set(data_raw.keys())):
        raise ValueError("Results missing year/month/day columns for annual aggregation.")

    year = int(np.asarray(data_raw["year"])[0])
    month = int(np.asarray(data_raw["month"])[0])
    day = int(np.asarray(data_raw["day"])[0])
    day_of_year = dt.date(year, month, day).timetuple().tm_yday

    name_parts = source_path.name.split(".")
    radar = name_parts[1] if len(name_parts) >= 2 else "radar"
    key = (radar.lower(), year)

    sample_len = len(next(iter(data.values()))) if data else 0
    hours = np.asarray(data_raw.get("hour", np.arange(sample_len)), dtype=int)
    valid_hours = (hours >= 0) & (hours < 24)

    if key not in annual_map:
        ndays = days_in_year(year)
        annual_map[key] = {
            "radar": radar.lower(),
            "year": year,
            "hour": np.arange(24, dtype=float) + 0.5,
            "day_values": np.arange(1, ndays + 1, dtype=int),
            "data": {
                "v": np.full((24, ndays), np.nan, dtype=float),
                "u": np.full((24, ndays), np.nan, dtype=float),
                "sdev_v": np.full((24, ndays), np.nan, dtype=float),
                "sdev_u": np.full((24, ndays), np.nan, dtype=float),
            },
        }

    group = annual_map[key]
    day_idx = day_of_year - 1
    for var_name, src_name in [
        ("v", "v"),
        ("u", "u"),
        ("sdev_v", "sdev_v"),
        ("sdev_u", "sdev_u"),
    ]:
        if src_name not in data:
            continue
        values = np.asarray(data[src_name], dtype=float)
        arr = group["data"][var_name]
        arr[hours[valid_hours], day_idx] = values[valid_hours]
        group["data"][var_name] = arr


def write_annual_outputs(annual_map: Dict[tuple[str, int], Dict[str, Any]], annual_dir_template: str) -> None:
    for (radar, year), group in annual_map.items():
        base_dir = Path(expand_path(apply_pattern(annual_dir_template, dt.datetime(year, 1, 1))))
        radar_dir = base_dir / radar
        radar_dir.mkdir(parents=True, exist_ok=True)
        out_file = radar_dir / f"{radar}_{year}.nc"
        tmp_file = out_file.with_suffix(out_file.suffix + ".tmp")

        with Dataset(tmp_file, "w") as nc:
            nc.createDimension("hour", len(group["hour"]))
            nc.createDimension("day_of_year", len(group["day_values"]))

            hour_var = nc.createVariable("hour", "f8", ("hour",))
            hour_var[:] = group["hour"]
            hour_var.long_name = "hour of day (centered)"
            hour_var.units = "hours"

            day_var = nc.createVariable("day_of_year", "i4", ("day_of_year",))
            day_var[:] = group["day_values"]
            day_var.long_name = "day of year"
            day_var.units = "day"

            meta = {
                "v": ("meridional wind", "(m/s)"),
                "u": ("zonal wind", "(m/s)"),
                "sdev_v": ("meridional wind error", "(m/s)"),
                "sdev_u": ("zonal wind error", "(m/s)"),
            }

            for name, (long_name, units) in meta.items():
                var = nc.createVariable(name, "f8", ("hour", "day_of_year"), zlib=True, complevel=6, fill_value=np.nan)
                var[:, :] = group["data"][name]
                var.long_name = long_name
                var.units = units

            nc.title = "Annual meteor wind grid (24 x 365/366)"
            nc.radar = radar
            nc.year = year
            nc.days_in_year = len(group["day_values"])
            nc.history = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") + " aggregated by fitnc_to_meteornc.py"

        tmp_file.replace(out_file)


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


def parse_date(val: str) -> str:
    """Accept YYYYMMDD, YYYY-MM-DD, or YYYY/MM/DD strings."""
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt.datetime.strptime(val, fmt)
            return val
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Invalid date format: {val}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert meteor NetCDF files to wind NetCDFs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Example:\n"
            "  python3 fitnc_to_meteornc.py \\\n"
            "    -i ~/data/netcdf/{yyyy}/{mm} \\\n"
            "    -s 2019-01-13 -e 2019-01-15 \\\n"
            "    -o ~/data/netcdf/{yyyy}/{mm} \\\n"
            "    --option MaxVelocity=120 --option RequestedHour=5"
        ),
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        dest="input_dir",
        default="~/data/netcdf/{yyyy}/{mm}",
        help="Input directory template containing daily NetCDF files (tokens allowed).",
    )
    parser.add_argument(
        "-s",
        "--start",
        required=False,
        type=parse_date,
        help="Start date (YYYYMMDD or YYYY-MM-DD)",
    )
    parser.add_argument(
        "-e",
        "--end",
        required=False,
        type=parse_date,
        help="End date inclusive (YYYYMMDD or YYYY-MM-DD)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        dest="output_dir",
        required=True,
        help="Output directory template for wind NetCDFs (tokens allowed).",
    )
    parser.add_argument(
        "--annual",
        action="store_true",
        help="Aggregate processed days into per-radar annual files (legacy layout).",
    )
    parser.add_argument(
        "--annual-dir",
        default=None,
        help="Output root for annual files (defaults to --output-dir template).",
    )
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        help="Extra key=value pairs forwarded to meteorproc_from_netcdf/meteorproc.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    extra = parse_cli_options(args.option)
    meteorproc_batch(
        args.input_dir,
        args.start,
        args.end,
        output_dir=args.output_dir,
        annual_dir=args.annual_dir,
        make_annual=args.annual,
        **extra,
    )


if __name__ == "__main__":
    main()
