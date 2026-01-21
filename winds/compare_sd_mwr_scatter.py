#!/usr/bin/env python3
"""
Compare SuperDARN vs MWR winds for the han-and and mcm-mcm cases using
the same weighting approach as sd_mwr_ctmt_multi.m, but without medians.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
from netCDF4 import Dataset
from scipy import io, stats
import matplotlib.pyplot as plt


@dataclass
class CaseConfig:
    name: str
    year: int
    sd_code: str
    mwr_mat: str


def matlab_datenum_to_datetime(dn: float) -> datetime:
    # MATLAB datenum is days since 0000-01-00; convert to Python datetime.
    day = int(np.floor(dn))
    frac = float(dn - day)
    return datetime.fromordinal(day) + timedelta(days=frac) - timedelta(days=366)


def datenum_to_doy(dn: float) -> float:
    if not np.isfinite(dn):
        return np.nan
    try:
        return float(matlab_datenum_to_datetime(dn).timetuple().tm_yday)
    except Exception:
        return np.nan


def fill_missing_linear(arr: np.ndarray, axis: int) -> np.ndarray:
    arr = np.array(arr, dtype=float, copy=True)
    if axis == 0:
        arr = arr.T
    out = arr.copy()
    for i in range(out.shape[0]):
        row = out[i, :]
        idx = np.isfinite(row)
        if idx.sum() < 2:
            continue
        x = np.flatnonzero(idx)
        y = row[idx]
        fill_idx = np.flatnonzero(~idx)
        row[~idx] = np.interp(fill_idx, x, y)
        out[i, :] = row
    if axis == 0:
        out = out.T
    return out


def ut_to_lt(winds: np.ndarray, hrs: np.ndarray, lthri: np.ndarray, lon: float) -> np.ndarray:
    hrs = np.array(hrs, dtype=float).ravel()
    winds = np.array(winds, dtype=float)
    if winds.shape[0] != hrs.size:
        raise ValueError(f"winds first dimension ({winds.shape[0]}) must match hrs length ({hrs.size})")

    lthrs = (hrs + lon / 360.0 * 24.0) % 24.0
    sort_idx = np.argsort(lthrs)
    lthrs_sort = lthrs[sort_idx]
    winds_sort = winds[sort_idx, :]

    lt_out = np.full((len(lthri), winds.shape[1]), np.nan, dtype=float)
    for cc in range(winds.shape[1]):
        ws = winds_sort[:, cc]
        good = np.isfinite(ws)
        if good.sum() < 2:
            continue
        lt = lthrs_sort[good]
        w = ws[good]
        # Periodic extension to cover wrap-around.
        lt_ext = np.concatenate([lt, [lt[0] + 24.0]])
        w_ext = np.concatenate([w, [w[0]]])
        lt_out[:, cc] = np.interp(lthri, lt_ext, w_ext)
    return lt_out


def fallback_sd_pos(code: str) -> Tuple[float, float]:
    # Fallback coordinates for common SuperDARN sites (lat, lon).
    sd_codes = [
        "sye", "inv", "ekb", "gbr", "tig", "sze", "kap", "szw", "unw", "cvw",
        "dce", "hok", "cve", "wal", "fir", "jme", "pyk", "hkw", "fhe", "hal", "sch",
        "fhw", "rkn", "ice", "kod", "mcm", "bpk", "pgr", "icw", "sys", "adw", "sps",
        "ade", "hjw", "san", "hje", "ksr", "lje", "sas", "ljw", "dcn", "han", "bks",
        "tst", "sto", "lyr", "zho", "cly", "ker",
    ]
    sd_coords = np.array([
        [-69.01, 39.61],
        [68.413, -133.769],
        [56.43568, 58.57142],
        [53.31753, -60.46424],
        [-43.40012, 147.21627],
        [41.83265, 111.93369],
        [49.3926, -82.32184],
        [41.83272, 111.93093],
        [-46.5133, 168.37569],
        [43.27101, -120.35856],
        [-75.08952, 123.35125],
        [43.5319, 143.6146],
        [43.27053, -120.35642],
        [37.8573, -75.51019],
        [-51.8314, -58.9793],
        [46.76656, 130.48594],
        [63.77258, -20.54476],
        [43.5374, 143.6073],
        [38.85877, -99.38843],
        [-75.62, -26.219],
        [54.8, -66.8],
        [38.85909, -99.39061],
        [62.828, -92.113],
        [63.77443, -20.54167],
        [57.61215, -152.19116],
        [-77.83777, 166.657],
        [-34.6271, 138.466],
        [53.98, -122.59],
        [63.77396, -20.54578],
        [-69.0, 39.58],
        [51.89337, -176.63121],
        [-89.995, 118.291],
        [51.89309, -176.62827],
        [42.885, 83.709],
        [-71.67714, -2.82816],
        [42.885, 83.709],
        [58.69206, -156.65922],
        [42.82406, 129.42244],
        [52.16, -106.53],
        [42.8267, 129.41775],
        [-75.08629, 123.3599],
        [62.31357, 26.60562],
        [37.10211, -77.95033],
        [53.32, -60.46],
        [63.86045, -21.0315],
        [78.15338, 16.07342],
        [-69.37669, 76.36646],
        [70.487, -68.504],
        [-49.35073, 70.26652],
    ])
    try:
        idx = sd_codes.index(code.lower())
        return float(sd_coords[idx, 0]), float(sd_coords[idx, 1])
    except ValueError:
        return np.nan, np.nan


def load_sd_annual(sd_fn: Path, radarcode: str) -> Dict[str, np.ndarray]:
    with Dataset(sd_fn, "r") as ds:
        sd_hour = np.array(ds.variables["hour"][:], dtype=float)
        sd_doy = np.array(ds.variables["day_of_year"][:], dtype=int)
        u = np.array(ds.variables["u"][:], dtype=float)
        v = np.array(ds.variables["v"][:], dtype=float)
        sdev_u = np.array(ds.variables["sdev_u"][:], dtype=float)
        sdev_v = np.array(ds.variables["sdev_v"][:], dtype=float)
        peak = np.array(ds.variables["Peak"][:], dtype=float)
        fwhm = np.array(ds.variables["FWHM"][:], dtype=float)
        try:
            lat = float(ds.getncattr("radar_latitude"))
            lon = float(ds.getncattr("radar_longitude"))
        except Exception:
            lat, lon = np.nan, np.nan

    if u.shape[0] == sd_doy.size and u.shape[1] == sd_hour.size:
        u = u.T
        v = v.T
        sdev_u = sdev_u.T
        sdev_v = sdev_v.T
        peak = peak.T
        fwhm = fwhm.T
    elif not (u.shape[0] == sd_hour.size and u.shape[1] == sd_doy.size):
        raise ValueError(f"Unexpected SD u/v dimensions {u.shape}")

    if not np.isfinite(lat) or not np.isfinite(lon):
        lat, lon = fallback_sd_pos(radarcode)
    if not np.isfinite(lat) or not np.isfinite(lon):
        raise ValueError(f"Missing SD lat/lon for {radarcode} in {sd_fn}")

    col_mean = np.nanmean(peak, axis=1)
    fwhm_mean = np.nanmean(fwhm, axis=1)
    for d in range(peak.shape[1]):
        if np.all(~np.isfinite(peak[:, d])):
            peak[:, d] = col_mean
            fwhm[:, d] = fwhm_mean
    peak = fill_missing_linear(peak, axis=1)
    fwhm = fill_missing_linear(fwhm, axis=1)
    peak = fill_missing_linear(peak, axis=0)
    fwhm = fill_missing_linear(fwhm, axis=0)

    return {
        "hour": sd_hour,
        "doy": sd_doy,
        "u": u,
        "v": v,
        "sdev_u": sdev_u,
        "sdev_v": sdev_v,
        "peak": peak,
        "fwhm": fwhm,
        "lat": lat,
        "lon": lon,
    }


def load_mwr_mat(mwr_fn: Path) -> Dict[str, np.ndarray]:
    data = io.loadmat(mwr_fn, squeeze_me=True, struct_as_record=False)
    u = np.array(data.get("u"), dtype=float)
    v = np.array(data.get("v"), dtype=float)
    alt = np.array(data.get("alt"), dtype=float).ravel()
    time = np.array(data.get("Time"), dtype=float)
    lat = float(np.array(data.get("lat")).squeeze())
    lon = float(np.array(data.get("lon")).squeeze())

    if time.ndim != 2:
        raise ValueError(f"Unexpected MWR Time dims {time.shape} in {mwr_fn}")

    with np.errstate(all="ignore"):
        hour_grid = np.nanmedian(((time - np.floor(time)) * 24.0), axis=1)
    if not np.all(np.isfinite(hour_grid)):
        hour_grid = np.arange(time.shape[0], dtype=float)

    day_doy = np.full(time.shape[1], np.nan, dtype=float)
    for di in range(time.shape[1]):
        dn = np.nanmedian(time[:, di])
        day_doy[di] = datenum_to_doy(dn)

    return {
        "u": u,
        "v": v,
        "alt": alt,
        "time": time,
        "hour": hour_grid,
        "day_doy": day_doy,
        "lat": lat,
        "lon": lon,
    }


def compute_mwr_modwt(mwr: Dict[str, np.ndarray], sd: Dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    alt = mwr["alt"]
    hour_mwr = mwr["hour"]
    day_doy = mwr["day_doy"]
    u_3d = mwr["u"]
    v_3d = mwr["v"]

    sd_hour = sd["hour"]
    sd_peak = sd["peak"]
    sd_fwhm = sd["fwhm"]
    sd_doy = sd["doy"]
    doy_to_idx = {int(d): i for i, d in enumerate(sd_doy)}

    n_hr = hour_mwr.size
    n_days = day_doy.size
    mod_peak = np.full((n_hr, n_days), np.nan, dtype=float)
    mod_fwhm = np.full((n_hr, n_days), np.nan, dtype=float)

    for di in range(n_days):
        doy = day_doy[di]
        if not np.isfinite(doy):
            continue
        doy_idx = doy_to_idx.get(int(doy))
        if doy_idx is None:
            continue
        mod_peak[:, di] = np.interp(hour_mwr, sd_hour, sd_peak[:, doy_idx])
        mod_fwhm[:, di] = np.interp(hour_mwr, sd_hour, sd_fwhm[:, doy_idx])

    mod_peak = fill_missing_linear(mod_peak, axis=1)
    mod_fwhm = fill_missing_linear(mod_fwhm, axis=1)
    mod_peak = fill_missing_linear(mod_peak, axis=0)
    mod_fwhm = fill_missing_linear(mod_fwhm, axis=0)

    u_modwt = np.full((n_hr, n_days), np.nan, dtype=float)
    v_modwt = np.full((n_hr, n_days), np.nan, dtype=float)
    for hri in range(n_hr):
        for di in range(n_days):
            mean = mod_peak[hri, di]
            fwhm = mod_fwhm[hri, di]
            if not np.isfinite(mean) or not np.isfinite(fwhm) or fwhm <= 0:
                continue
            sigma = fwhm / 2.0
            model_cts = np.exp(-0.5 * ((alt - mean) / sigma) ** 2)
            u_prof = u_3d[:, hri, di]
            v_prof = v_3d[:, hri, di]
            valid_u = np.isfinite(u_prof)
            valid_v = np.isfinite(v_prof)
            if np.any(valid_u):
                denom = np.nansum(model_cts[valid_u])
                if denom > 0:
                    u_modwt[hri, di] = np.nansum(u_prof[valid_u] * model_cts[valid_u]) / denom
            if np.any(valid_v):
                denom = np.nansum(model_cts[valid_v])
                if denom > 0:
                    v_modwt[hri, di] = np.nansum(v_prof[valid_v] * model_cts[valid_v]) / denom
    return u_modwt, v_modwt


def align_sd_to_mwr(sd: Dict[str, np.ndarray], day_doy: np.ndarray) -> Dict[str, np.ndarray]:
    sd_doy = sd["doy"]
    doy_to_idx = {int(d): i for i, d in enumerate(sd_doy)}
    n_days = day_doy.size
    out = {}
    for key in ["u", "v", "sdev_u", "sdev_v"]:
        arr = sd[key]
        out_arr = np.full((arr.shape[0], n_days), np.nan, dtype=float)
        for di in range(n_days):
            doy = day_doy[di]
            if not np.isfinite(doy):
                continue
            idx = doy_to_idx.get(int(doy))
            if idx is None:
                continue
            out_arr[:, di] = arr[:, idx]
        out[key] = out_arr
    return out


def compute_stats(x: np.ndarray, y: np.ndarray, sigma: np.ndarray) -> Dict[str, float]:
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(sigma) & (sigma > 0)
    if not np.any(mask):
        return {k: np.nan for k in [
            "n", "bias", "rmse", "mae", "w_bias", "chi2", "chi2_red", "p_value",
            "within_1sigma", "within_2sigma", "corr", "slope", "intercept",
        ]}

    x = x[mask]
    y = y[mask]
    sigma = sigma[mask]
    diff = y - x
    n = diff.size
    bias = float(np.mean(diff))
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    mae = float(np.mean(np.abs(diff)))
    w = 1.0 / (sigma ** 2)
    w_bias = float(np.sum(w * diff) / np.sum(w))
    chi2 = float(np.sum((diff / sigma) ** 2))
    chi2_red = chi2 / n
    p_value = float(stats.chi2.sf(chi2, df=n))
    within_1sigma = float(np.mean(np.abs(diff) <= sigma))
    within_2sigma = float(np.mean(np.abs(diff) <= 2.0 * sigma))
    corr = float(np.corrcoef(x, y)[0, 1]) if n >= 2 else np.nan
    slope, intercept = (np.polyfit(x, y, 1) if n >= 2 else (np.nan, np.nan))
    return {
        "n": float(n),
        "bias": bias,
        "rmse": rmse,
        "mae": mae,
        "w_bias": w_bias,
        "chi2": chi2,
        "chi2_red": chi2_red,
        "p_value": p_value,
        "within_1sigma": within_1sigma,
        "within_2sigma": within_2sigma,
        "corr": corr,
        "slope": float(slope),
        "intercept": float(intercept),
    }


def plot_scatter(
    out_path: Path,
    case_name: str,
    x_u: np.ndarray,
    y_u: np.ndarray,
    yerr_u: np.ndarray,
    x_v: np.ndarray,
    y_v: np.ndarray,
    yerr_v: np.ndarray,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    comps = [
        ("Zonal", x_u, y_u, yerr_u),
        ("Meridional", x_v, y_v, yerr_v),
    ]
    for ax, (label, x, y, yerr) in zip(axes, comps):
        mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(yerr)
        x = x[mask]
        y = y[mask]
        yerr = yerr[mask]
        ax.errorbar(
            x,
            y,
            xerr=np.zeros_like(yerr),
            yerr=yerr,
            fmt="o",
            markersize=2,
            alpha=0.25,
            ecolor="0.4",
            elinewidth=0.3,
            capsize=0,
        )
        if x.size > 0:
            lim_min = float(np.nanmin([x.min(), y.min()]))
            lim_max = float(np.nanmax([x.max(), y.max()]))
            pad = 0.05 * (lim_max - lim_min) if lim_max > lim_min else 1.0
            ax.plot([lim_min - pad, lim_max + pad], [lim_min - pad, lim_max + pad], "k--", lw=1)
            ax.set_xlim(lim_min - pad, lim_max + pad)
            ax.set_ylim(lim_min - pad, lim_max + pad)
        ax.set_title(f"{case_name} {label}")
        ax.set_xlabel("MWR (m/s)")
        ax.set_ylabel("SuperDARN (m/s)")
        ax.grid(True, alpha=0.3)

    fig.suptitle(f"MWR vs SuperDARN (MWR reference, SD uncertainties)")
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main() -> None:
    cases = [
        CaseConfig(name="han_and", year=2008, sd_code="han", mwr_mat="~/data/meteor_winds/mat/And_2008.mat"),
        CaseConfig(name="mcm_mcm", year=2019, sd_code="mcm", mwr_mat="~/data/meteor_winds/mat/McMurdo_2019.mat"),
    ]
    sd_fn_fmt = "~/data/superdarn/fit_nc_3_winds/annual/{year}/{code}_{year}.nc"
    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    stats_rows = []
    lthri = np.arange(24, dtype=float)

    for cfg in cases:
        sd_fn = Path(sd_fn_fmt.format(year=cfg.year, code=cfg.sd_code)).expanduser()
        mwr_fn = Path(cfg.mwr_mat).expanduser()

        sd = load_sd_annual(sd_fn, cfg.sd_code)
        mwr = load_mwr_mat(mwr_fn)

        u_modwt, v_modwt = compute_mwr_modwt(mwr, sd)
        sd_sub = align_sd_to_mwr(sd, mwr["day_doy"])

        lt_mwr_u = ut_to_lt(u_modwt, mwr["hour"], lthri, mwr["lon"])
        lt_mwr_v = ut_to_lt(v_modwt, mwr["hour"], lthri, mwr["lon"])

        lt_sd_u = ut_to_lt(sd_sub["u"], sd["hour"], lthri, sd["lon"])
        lt_sd_v = ut_to_lt(sd_sub["v"], sd["hour"], lthri, sd["lon"])
        lt_sd_uerr = ut_to_lt(sd_sub["sdev_u"], sd["hour"], lthri, sd["lon"])
        lt_sd_verr = ut_to_lt(sd_sub["sdev_v"], sd["hour"], lthri, sd["lon"])

        x_u = lt_mwr_u.ravel()
        y_u = lt_sd_u.ravel()
        err_u = lt_sd_uerr.ravel()
        x_v = lt_mwr_v.ravel()
        y_v = lt_sd_v.ravel()
        err_v = lt_sd_verr.ravel()

        stats_u = compute_stats(x_u, y_u, err_u)
        stats_v = compute_stats(x_v, y_v, err_v)

        stats_u.update({"case": cfg.name, "component": "zonal"})
        stats_v.update({"case": cfg.name, "component": "meridional"})
        stats_rows.extend([stats_u, stats_v])

        fig_path = out_dir / f"sd_mwr_scatter_{cfg.name}.png"
        plot_scatter(fig_path, cfg.name, x_u, y_u, err_u, x_v, y_v, err_v)

    # Save stats table.
    if stats_rows:
        keys = [
            "case", "component", "n", "bias", "rmse", "mae", "w_bias",
            "chi2", "chi2_red", "p_value", "within_1sigma", "within_2sigma",
            "corr", "slope", "intercept",
        ]
        out_csv = out_dir / "sd_mwr_stats.csv"
        with out_csv.open("w", encoding="utf-8") as f:
            f.write(",".join(keys) + "\n")
            for row in stats_rows:
                f.write(",".join(str(row.get(k, "")) for k in keys) + "\n")

        print(f"Wrote stats: {out_csv}")
    for row in stats_rows:
        print(
            f"{row['case']} {row['component']}: n={row['n']:.0f}, "
            f"bias={row['bias']:.2f} m/s, rmse={row['rmse']:.2f} m/s, "
            f"chi2_red={row['chi2_red']:.2f}, p={row['p_value']:.3g}, "
            f"within_1sigma={row['within_1sigma']:.2f}, within_2sigma={row['within_2sigma']:.2f}"
        )


if __name__ == "__main__":
    main()
