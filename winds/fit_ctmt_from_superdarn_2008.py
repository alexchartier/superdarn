#!/usr/bin/env python3
"""
Estimate modifications to CTMT tidal component amplitudes and phases
using SuperDARN annual meteor wind files (e.g., 2008).

The script:
 - loads CTMT diurnal and semidiurnal coefficients,
 - loads all annual SuperDARN wind files in a directory,
 - builds altitude-weighted design matrices using Mod_Peak/Mod_FWHM (or Peak/FWHM),
 - subtracts the mean SuperDARN winds (u, v) before fitting,
 - solves weighted least squares for amplitude scale factors AND phase shifts for each tidal component (u/v separately).

Run from the repo root:
    python3 fit_ctmt_from_superdarn_2008.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
import xarray as xr

# Component ordering matches the MATLAB tooling in this repo.
COMPONENTS: Dict[str, List[str]] = {
    "d": ["w2", "w1", "s0", "e1", "e2", "e3"],  # diurnal
    "s": ["w4", "w3", "w2", "w1", "s0", "e1", "e2", "e3"],  # semidiurnal
}


def hour_to_float(hour_var: xr.DataArray) -> np.ndarray:
    """Return hour values as float hours (handles timedelta64 or float)."""
    vals = hour_var.values
    if np.issubdtype(vals.dtype, np.timedelta64):
        return vals.astype("timedelta64[s]").astype(float) / 3600.0
    return np.asarray(vals, dtype=float)


def gaussian_weights(alts: np.ndarray, peak: float, fwhm: float) -> np.ndarray | None:
    """Normalized Gaussian weights for altitude averaging."""
    if not np.isfinite(peak) or not np.isfinite(fwhm) or fwhm <= 0:
        return None
    weights = np.exp(-((alts - peak) ** 2) / (fwhm ** 2))
    if not np.isfinite(weights).any():
        return None
    weights /= np.nansum(weights)
    return weights


def point_weight(std: float | None, floor: float = 5.0) -> float:
    """Inverse-variance weight with a floor to avoid overweighting tiny std values."""
    if std is None or not np.isfinite(std):
        return 1.0 / (floor**2)
    return 1.0 / (max(std, floor) ** 2)


class CtmtAtSite:
    """CTMT amplitude/phase interpolated to a single site latitude."""

    def __init__(
        self,
        diurnal_path: Path,
        semidiurnal_path: Path,
        lat: float,
        lon: float,
        alt_range: Tuple[float, float] = (70.0, 110.0),
    ):
        self.lat = float(lat)
        self.lon = float(lon) % 360.0
        self.alt_range = alt_range

        ds_d = xr.open_dataset(diurnal_path)
        ds_s = xr.open_dataset(semidiurnal_path)

        alt_mask = (ds_d["lev"].values >= alt_range[0]) & (
            ds_d["lev"].values <= alt_range[1]
        )
        self.alts = ds_d["lev"].values[alt_mask]

        self.months = ds_d["month"].values.astype(int)
        self.fields: Dict[str, Dict[str, Dict[Tuple[str, str], np.ndarray]]] = {
            "d": {"amp": {}, "phase": {}},
            "s": {"amp": {}, "phase": {}},
        }

        for key, ds in (("d", ds_d), ("s", ds_s)):
            for comp in COMPONENTS[key]:
                for dirn in ("u", "v"):
                    amp_name = f"amp_{comp}_{dirn}"
                    phase_name = f"phase_{comp}_{dirn}"
                    amp = (
                        ds[amp_name]
                        .interp(lat=self.lat)
                        .transpose("month", "lev")
                        .values[:, alt_mask]
                    )
                    phase = (
                        ds[phase_name]
                        .interp(lat=self.lat)
                        .transpose("month", "lev")
                        .values[:, alt_mask]
                    )
                    # Replace fill values (-999) with NaN for safe averaging.
                    amp = np.where(np.abs(amp) > 900, np.nan, amp)
                    phase = np.where(np.abs(phase) > 900, np.nan, phase)
                    self.fields[key]["amp"][(comp, dirn)] = amp
                    self.fields[key]["phase"][(comp, dirn)] = phase

        ds_d.close()
        ds_s.close()

    def component_profile(
        self, ds_key: str, comp: str, dirn: str, month: int, hour_ut: float
    ) -> np.ndarray:
        """Return CTMT wind profile vs altitude for one component/direction."""
        m_idx = int(month) - 1
        amp = self.fields[ds_key]["amp"][(comp, dirn)][m_idx]
        phase = self.fields[ds_key]["phase"][(comp, dirn)][m_idx]

        dir_mult = 1 if comp[0] == "e" else -1 if comp[0] == "w" else 0
        ds_mult = 1 if ds_key == "d" else 2
        s = int(comp[1])

        ang = (
            ds_mult * np.pi / 12.0 * hour_ut
            - dir_mult * s * np.deg2rad(self.lon)
            - phase * ds_mult * np.pi / 12.0
        )
        return amp * np.cos(ang)


def component_rows_cos_sin(
    site: CtmtAtSite,
    comp_order: Sequence[Tuple[str, str]],
    month: int,
    hour_ut: float,
    alt_weights: np.ndarray,
) -> Tuple[List[float], List[float]]:
    """
    Altitude-weighted cosine/sine contributions of each component for u and v.

    For each component we return two columns (C, S) such that a phase shift
    delta (in radians) and amplitude scale A map to linear coefficients:
        coeff_cos = A * cos(delta), coeff_sin = A * sin(delta)
    and the predicted value is coeff_cos * C + coeff_sin * S.
    """
    row_u: List[float] = []
    row_v: List[float] = []

    for ds_key, comp in comp_order:
        ds_mult = 1 if ds_key == "d" else 2
        dir_mult = 1 if comp[0] == "e" else -1 if comp[0] == "w" else 0
        s = int(comp[1])

        # u
        amp_u = site.fields[ds_key]["amp"][(comp, "u")][int(month) - 1]
        phase_u = site.fields[ds_key]["phase"][(comp, "u")][int(month) - 1]
        ang_u = (
            ds_mult * np.pi / 12.0 * hour_ut
            - dir_mult * s * np.deg2rad(site.lon)
            - phase_u * ds_mult * np.pi / 12.0
        )
        C_u = np.nansum(amp_u * np.cos(ang_u) * alt_weights)
        S_u = np.nansum(amp_u * np.sin(ang_u) * alt_weights)
        row_u.extend([float(C_u), float(S_u)])

        # v
        amp_v = site.fields[ds_key]["amp"][(comp, "v")][int(month) - 1]
        phase_v = site.fields[ds_key]["phase"][(comp, "v")][int(month) - 1]
        ang_v = (
            ds_mult * np.pi / 12.0 * hour_ut
            - dir_mult * s * np.deg2rad(site.lon)
            - phase_v * ds_mult * np.pi / 12.0
        )
        C_v = np.nansum(amp_v * np.cos(ang_v) * alt_weights)
        S_v = np.nansum(amp_v * np.sin(ang_v) * alt_weights)
        row_v.extend([float(C_v), float(S_v)])

    return row_u, row_v


def build_design_matrices(
    ds: xr.Dataset,
    site: CtmtAtSite,
    comp_order: Sequence[Tuple[str, str]],
    year: int,
    error_floor: float = 5.0,
) -> Tuple[
    List[List[float]],
    List[float],
    List[float],
    List[List[float]],
    List[float],
    List[float],
    float,
    float,
]:
    """Create design matrices and observations for a single radar."""
    hours = hour_to_float(ds["hour"])
    doys = ds["day_of_year"].values
    u_obs = ds["u"].values
    v_obs = ds["v"].values
    sdev_u = ds["sdev_u"].values if "sdev_u" in ds else None
    sdev_v = ds["sdev_v"].values if "sdev_v" in ds else None

    u_mean = float(np.nanmean(u_obs)) if np.isfinite(np.nanmean(u_obs)) else 0.0
    v_mean = float(np.nanmean(v_obs)) if np.isfinite(np.nanmean(v_obs)) else 0.0
    u_obs = u_obs - u_mean
    v_obs = v_obs - v_mean

    peak_var = "Mod_Peak" if "Mod_Peak" in ds else "Peak"
    fwhm_var = "Mod_FWHM" if "Mod_FWHM" in ds else "FWHM"
    peaks = ds[peak_var].values
    fwhms = ds[fwhm_var].values

    base_date = dt.datetime(year, 1, 1)

    G_u: List[List[float]] = []
    y_u: List[float] = []
    w_u: List[float] = []
    G_v: List[List[float]] = []
    y_v: List[float] = []
    w_v: List[float] = []

    for di, doy in enumerate(doys):
        month = (base_date + dt.timedelta(days=int(doy) - 1)).month
        for hi, hour_ut in enumerate(hours):
            u_val = u_obs[di, hi]
            v_val = v_obs[di, hi]
            if not np.isfinite(u_val) and not np.isfinite(v_val):
                continue

            peak = peaks[di, hi]
            fwhm = fwhms[di, hi]
            alt_wt = gaussian_weights(site.alts, peak, fwhm)
            if alt_wt is None:
                continue

            row_u, row_v = component_rows_cos_sin(site, comp_order, month, hour_ut, alt_wt)

            if np.isfinite(u_val):
                G_u.append(row_u)
                y_u.append(float(u_val))
                w_u.append(point_weight(sdev_u[di, hi] if sdev_u is not None else None, error_floor))
            if np.isfinite(v_val):
                G_v.append(row_v)
                y_v.append(float(v_val))
                w_v.append(point_weight(sdev_v[di, hi] if sdev_v is not None else None, error_floor))

    return G_u, y_u, w_u, G_v, y_v, w_v, u_mean, v_mean


def weighted_lstsq(G: np.ndarray, y: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted least squares solution."""
    if G.size == 0 or y.size == 0:
        raise ValueError("No data available for fitting.")
    W = np.sqrt(weights)[:, None]
    Gw = G * W
    yw = y * np.sqrt(weights)
    sol, *_ = np.linalg.lstsq(Gw, yw, rcond=None)
    return sol


def fit_ctmt_scaling(
    data_dir: Path,
    diurnal_path: Path,
    semidiurnal_path: Path,
    year: int,
    alt_range: Tuple[float, float],
    error_floor: float = 5.0,
) -> Dict[str, Dict[str, float]]:
    """Fit multiplicative scaling factors and phase shifts for CTMT components."""
    comp_order = [("d", c) for c in COMPONENTS["d"]] + [("s", c) for c in COMPONENTS["s"]]

    all_G_u: List[List[float]] = []
    all_y_u: List[float] = []
    all_w_u: List[float] = []
    all_G_v: List[List[float]] = []
    all_y_v: List[float] = []
    all_w_v: List[float] = []
    mean_records: List[Dict[str, float]] = []

    for nc_path in sorted(data_dir.glob("*_{}.nc".format(year))):
        ds = xr.load_dataset(nc_path, decode_timedelta=True)
        site = CtmtAtSite(
            diurnal_path,
            semidiurnal_path,
            float(ds.attrs["radar_latitude"]),
            float(ds.attrs["radar_longitude"]),
            alt_range=alt_range,
        )
        G_u, y_u, w_u, G_v, y_v, w_v, u_mean, v_mean = build_design_matrices(
            ds, site, comp_order, year, error_floor=error_floor
        )
        ds.close()

        all_G_u.extend(G_u)
        all_y_u.extend(y_u)
        all_w_u.extend(w_u)
        all_G_v.extend(G_v)
        all_y_v.extend(y_v)
        all_w_v.extend(w_v)
        mean_records.append(
            {"file": str(nc_path), "u_mean_removed": u_mean, "v_mean_removed": v_mean}
        )

    G_u_arr = np.asarray(all_G_u)
    y_u_arr = np.asarray(all_y_u)
    w_u_arr = np.asarray(all_w_u)
    G_v_arr = np.asarray(all_G_v)
    y_v_arr = np.asarray(all_y_v)
    w_v_arr = np.asarray(all_w_v)

    # Solve for linear coefficients (A*cos(delta), A*sin(delta)) per component.
    coeffs_u = weighted_lstsq(G_u_arr, y_u_arr, w_u_arr)
    coeffs_v = weighted_lstsq(G_v_arr, y_v_arr, w_v_arr)

    result: Dict[str, Dict[str, float]] = {}
    for idx, (ds_key, comp) in enumerate(comp_order):
        key = f"{ds_key}_{comp}"
        ds_mult = 1 if ds_key == "d" else 2
        a_u = float(coeffs_u[2 * idx])
        b_u = float(coeffs_u[2 * idx + 1])
        a_v = float(coeffs_v[2 * idx])
        b_v = float(coeffs_v[2 * idx + 1])
        scale_u = float(np.hypot(a_u, b_u))
        scale_v = float(np.hypot(a_v, b_v))
        phase_u_rad = float(np.arctan2(b_u, a_u))
        phase_v_rad = float(np.arctan2(b_v, a_v))
        phase_u_hours = phase_u_rad * 12.0 / (ds_mult * np.pi)
        phase_v_hours = phase_v_rad * 12.0 / (ds_mult * np.pi)
        result[key] = {
            "u_scale": scale_u,
            "v_scale": scale_v,
            "u_phase_shift_hours": phase_u_hours,
            "v_phase_shift_hours": phase_v_hours,
        }

    # Quick residual diagnostics (unweighted RMSE).
    base_pred_u = np.sum(G_u_arr[:, ::2], axis=1)  # equivalent to scale=1, phase=0
    fitted_pred_u = G_u_arr @ coeffs_u
    base_pred_v = np.sum(G_v_arr[:, ::2], axis=1)
    fitted_pred_v = G_v_arr @ coeffs_v
    result["_rmse"] = {
        "u_base": float(np.sqrt(np.nanmean((y_u_arr - base_pred_u) ** 2))),
        "u_fitted": float(np.sqrt(np.nanmean((y_u_arr - fitted_pred_u) ** 2))),
        "v_base": float(np.sqrt(np.nanmean((y_v_arr - base_pred_v) ** 2))),
        "v_fitted": float(np.sqrt(np.nanmean((y_v_arr - fitted_pred_v) ** 2))),
        "u_points": int(len(y_u_arr)),
        "v_points": int(len(y_v_arr)),
    }
    result["_sd_mean_removed"] = {
        "u_mean": float(np.nanmean([m["u_mean_removed"] for m in mean_records])),
        "v_mean": float(np.nanmean([m["v_mean_removed"] for m in mean_records])),
        "per_file": mean_records,
    }

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit CTMT coefficient scale factors from SuperDARN winds.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("~/data/superdarn/fit_nc_3_winds/annual/2008").expanduser(),
        help="Directory containing annual SuperDARN netCDF files.",
    )
    parser.add_argument(
        "--ctmt-diurnal",
        type=Path,
        default=Path("~/data/ctmt/ctmt_diurnal_2002_2008.nc").expanduser(),
        help="Path to CTMT diurnal coefficient file.",
    )
    parser.add_argument(
        "--ctmt-semidiurnal",
        type=Path,
        default=Path("~/data/ctmt/ctmt_semidiurnal_2002_2008.nc").expanduser(),
        help="Path to CTMT semidiurnal coefficient file.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2008,
        help="Year of the SuperDARN annual files to use.",
    )
    parser.add_argument(
        "--alt-min",
        type=float,
        default=70.0,
        help="Lower altitude bound (km) for CTMT vertical averaging.",
    )
    parser.add_argument(
        "--alt-max",
        type=float,
        default=110.0,
        help="Upper altitude bound (km) for CTMT vertical averaging.",
    )
    parser.add_argument(
        "--error-floor",
        type=float,
        default=5.0,
        help="Minimum standard deviation (m/s) used for inverse-variance weighting.",
    )
    parser.add_argument(
        "--save-json",
        type=Path,
        help="Optional path to save the fitted scales and diagnostics as JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    alt_range = (args.alt_min, args.alt_max)

    result = fit_ctmt_scaling(
        args.data_dir,
        args.ctmt_diurnal,
        args.ctmt_semidiurnal,
        args.year,
        alt_range=alt_range,
        error_floor=args.error_floor,
    )

    comp_order = [("d", c) for c in COMPONENTS["d"]] + [("s", c) for c in COMPONENTS["s"]]
    print("\nBest-fit CTMT amplitude scales and phase shifts (u/v):")
    for ds_key, comp in comp_order:
        key = f"{ds_key}_{comp}"
        vals = result[key]
        print(
            f"{key:6s}  "
            f"u scale 1.000 -> {vals['u_scale']:+0.3f}, "
            f"u phase 0.0h -> {vals['u_phase_shift_hours']:+0.3f}h;  "
            f"v scale 1.000 -> {vals['v_scale']:+0.3f}, "
            f"v phase 0.0h -> {vals['v_phase_shift_hours']:+0.3f}h"
        )

    mean_removed = result.get("_sd_mean_removed", {})
    if mean_removed:
        print(
            f"\nMean SuperDARN winds removed before fit: "
            f"u={mean_removed.get('u_mean', 0.0):+0.2f} m/s, "
            f"v={mean_removed.get('v_mean', 0.0):+0.2f} m/s"
        )

    rmse = result["_rmse"]
    print(
        f"\nRMSE (u): base={rmse['u_base']:.2f} m/s, fitted={rmse['u_fitted']:.2f} m/s "
        f"using {rmse['u_points']} points"
    )
    print(
        f"RMSE (v): base={rmse['v_base']:.2f} m/s, fitted={rmse['v_fitted']:.2f} m/s "
        f"using {rmse['v_points']} points\n"
    )

    if args.save_json:
        args.save_json.parent.mkdir(parents=True, exist_ok=True)
        with args.save_json.open("w") as fh:
            json.dump(result, fh, indent=2)
        print(f"Saved results to {args.save_json}")


if __name__ == "__main__":
    main()
