"""
Python port of meteorproc_from_netcdf.m.

Reads a SuperDARN meteor NetCDF file, rebuilds CFIT-style beam records, and
runs the meteor wind solver. Global metadata in the NetCDF file (beam
headings, boresite, etc.) are used to populate the site structure, so no
external hardware tables are required.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

import numpy as np
import pandas as pd
from netCDF4 import Dataset


def meteorproc_from_netcdf(
    ncfile: str | os.PathLike[str],
    *,
    radar_code: str | None = None,
    site: Mapping[str, Any] | None = None,
    **meteor_kwargs: Any,
) -> pd.DataFrame:
    """
    Run meteor wind fitting on a NetCDF meteor catalog.

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


def infer_code(ncfile: Path) -> str:
    name = ncfile.stem
    parts = name.split(".")
    if len(parts) >= 2:
        return parts[1]
    return "fir"
