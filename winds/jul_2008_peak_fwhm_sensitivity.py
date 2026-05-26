from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.optimize import curve_fit


DATA_PATH = Path("/Users/chartat1/data/meteor_winds/mat/Jul_2008.mat")
OUT_DIR = Path("/Users/chartat1/superdarn/winds/outputs/jul_2008_sensitivity")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def gauss1(x: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    return a * np.exp(-((x - b) ** 2) / (c**2))


def moving_nanmedian(arr: np.ndarray, window: int = 31) -> np.ndarray:
    radius = window // 2
    out = np.full_like(arr, np.nan, dtype=float)
    for idx in range(arr.shape[-1]):
        start = max(0, idx - radius)
        stop = min(arr.shape[-1], idx + radius + 1)
        out[..., idx] = np.nanmedian(arr[..., start:stop], axis=-1)
    return out


def fit_profile(alt_km: np.ndarray, counts: np.ndarray) -> tuple[float, float, float]:
    good = np.isfinite(counts) & np.isfinite(alt_km)
    x = alt_km[good]
    y = counts[good]
    if x.size < 4 or np.all(y <= 0):
        return np.nan, np.nan, np.nan
    a0 = float(np.nanmax(y))
    if not np.isfinite(a0) or a0 <= 0:
        return np.nan, np.nan, np.nan
    b0 = float(np.nansum(x * y) / np.nansum(y))
    c0 = max(float(np.nanstd(np.repeat(x, np.maximum(np.round(y / np.nanmax(y) * 10), 1).astype(int)))), 2.0)
    c0 = min(max(c0, 1.0), 10.0)
    try:
        popt, _ = curve_fit(
            gauss1,
            x,
            y,
            p0=(a0, b0, c0),
            bounds=((0.0, 75.0, 0.5), (np.inf, 105.0, 20.0)),
            maxfev=20000,
        )
    except Exception:
        # Fallback moment estimate if the nonlinear fit fails.
        mu = b0
        sigma = np.sqrt(np.nansum(y * (x - mu) ** 2) / np.nansum(y))
        popt = np.array([a0, mu, max(float(sigma * np.sqrt(2.0)), 0.5)])
    return float(popt[0]), float(popt[1]), float(popt[2])


def matlab_datenum_to_datetime(arr: np.ndarray) -> pd.DatetimeIndex:
    flat = np.asarray(arr, dtype=float).ravel()
    return pd.to_datetime(flat - 719529, unit="D", origin="unix")


def compute_month_targets(times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    dates = matlab_datenum_to_datetime(times[0, :])
    target_dates = pd.date_range("2008-01-01", "2008-12-01", freq="MS") + pd.offsets.Day(14)
    idx = np.array([int(np.where(dates.normalize() == target)[0][0]) for target in target_dates], dtype=int)
    return target_dates.month.to_numpy(), idx


@dataclass
class WindField:
    zonal: np.ndarray
    meridional: np.ndarray


def weighted_wind(u_prof: np.ndarray, v_prof: np.ndarray, alt: np.ndarray, peak: float, width: float) -> tuple[float, float]:
    if not np.isfinite(peak) or not np.isfinite(width) or width <= 0:
        return np.nan, np.nan
    weights = np.exp(-((alt - peak) ** 2) / (width**2))
    good_u = np.isfinite(u_prof)
    good_v = np.isfinite(v_prof)
    zonal = np.nan
    meridional = np.nan
    if np.any(good_u):
        wu = weights[good_u]
        zonal = np.nansum(u_prof[good_u] * wu) / np.nansum(wu)
    if np.any(good_v):
        wv = weights[good_v]
        meridional = np.nansum(v_prof[good_v] * wv) / np.nansum(wv)
    return zonal, meridional


def calc_stats(delta: np.ndarray) -> dict[str, float]:
    vals = delta[np.isfinite(delta)]
    return {
        "mean_signed": float(np.nanmean(vals)),
        "mean_abs": float(np.nanmean(np.abs(vals))),
        "rmse": float(np.sqrt(np.nanmean(vals**2))),
        "max_abs": float(np.nanmax(np.abs(vals))),
        "n": int(vals.size),
    }


def main() -> None:
    mat = loadmat(DATA_PATH, squeeze_me=True)
    alt = np.asarray(mat["alt"], dtype=float)
    counts = np.asarray(mat["counts"], dtype=float)
    u = np.asarray(mat["u"], dtype=float)
    v = np.asarray(mat["v"], dtype=float)
    times = np.asarray(mat["Time"], dtype=float)

    counts_med = moving_nanmedian(counts, 31)
    u_med = moving_nanmedian(u, 31)
    v_med = moving_nanmedian(v, 31)

    months, month_idx = compute_month_targets(times)
    hours = np.arange(24, dtype=int)

    fit_alt = alt[1:-1]
    peaks = np.full((24, 12), np.nan, dtype=float)
    widths = np.full((24, 12), np.nan, dtype=float)

    for hi in range(24):
        for mi, di in enumerate(month_idx):
            _, peak, width = fit_profile(fit_alt, counts_med[1:-1, hi, di])
            peaks[hi, mi] = peak
            widths[hi, mi] = width

    baseline_zonal = np.full((24, 12), np.nan, dtype=float)
    baseline_meridional = np.full((24, 12), np.nan, dtype=float)
    for hi in range(24):
        for mi, di in enumerate(month_idx):
            baseline_zonal[hi, mi], baseline_meridional[hi, mi] = weighted_wind(
                u_med[:, hi, di],
                v_med[:, hi, di],
                alt,
                peaks[hi, mi],
                widths[hi, mi],
            )

    perturbations = {
        "peak_plus_1km": (1.0, 0.0),
        "peak_minus_1km": (-1.0, 0.0),
        "width_plus_1km": (0.0, 1.0),
        "width_minus_1km": (0.0, -1.0),
    }

    rows: list[dict[str, float | str]] = []
    for label, (dpeak, dwidth) in perturbations.items():
        zonal = np.full_like(baseline_zonal, np.nan)
        meridional = np.full_like(baseline_meridional, np.nan)
        for hi in range(24):
            for mi, di in enumerate(month_idx):
                zonal[hi, mi], meridional[hi, mi] = weighted_wind(
                    u_med[:, hi, di],
                    v_med[:, hi, di],
                    alt,
                    peaks[hi, mi] + dpeak,
                    widths[hi, mi] + dwidth,
                )
        dz = zonal - baseline_zonal
        dm = meridional - baseline_meridional
        zstats = calc_stats(dz)
        mstats = calc_stats(dm)
        for comp, stats in [("zonal", zstats), ("meridional", mstats)]:
            row = {"perturbation": label, "component": comp}
            row.update(stats)
            rows.append(row)

    summary = pd.DataFrame(rows)
    summary_path = OUT_DIR / "jul_2008_peak_fwhm_sensitivity_summary.csv"
    summary.to_csv(summary_path, index=False)

    baseline_df = []
    for mi, month in enumerate(months):
        for hi in hours:
            baseline_df.append(
                {
                    "month": int(month),
                    "hour_ut": int(hi),
                    "peak_km": peaks[hi, mi],
                    "width_param_km": widths[hi, mi],
                    "zonal_baseline_mps": baseline_zonal[hi, mi],
                    "meridional_baseline_mps": baseline_meridional[hi, mi],
                }
            )
    baseline_path = OUT_DIR / "jul_2008_baseline_peak_width_and_winds.csv"
    pd.DataFrame(baseline_df).to_csv(baseline_path, index=False)

    txt_path = OUT_DIR / "jul_2008_peak_fwhm_sensitivity_summary.txt"
    with txt_path.open("w", encoding="ascii") as fh:
        fh.write("JUL 2008 peak/FWHM sensitivity of monthly wind products\n")
        fh.write("Baseline workflow: 31-day median-smoothed altitude profiles, monthly mid-month samples, gauss1 weights.\n")
        fh.write("Width term follows the code variable labeled FWHM, i.e. the gauss1 width parameter used in weighting.\n\n")
        for label in perturbations:
            fh.write(f"{label}\n")
            sub = summary[summary["perturbation"] == label]
            for _, row in sub.iterrows():
                fh.write(
                    f"  {row['component']}: mean_abs={row['mean_abs']:.3f} m/s, "
                    f"rmse={row['rmse']:.3f} m/s, max_abs={row['max_abs']:.3f} m/s, "
                    f"mean_signed={row['mean_signed']:.3f} m/s, n={int(row['n'])}\n"
                )
            fh.write("\n")

    print(summary.round(3).to_string(index=False))
    print(summary_path)
    print(baseline_path)
    print(txt_path)


if __name__ == "__main__":
    main()
