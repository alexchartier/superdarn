#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import requests
from urllib3.exceptions import InsecureRequestWarning

from compare_sd_mwr_scatter import compute_mwr_modwt, load_mwr_mat, load_sd_annual, ut_to_lt
from download_extract_jawara_point_subsets import CASES as JAWARA_SUBSET_CASES
from download_extract_jawara_point_subsets import case_output_path as jawara_case_output_path
from download_extract_jawara_point_subsets import login as jawara_login
from download_extract_jawara_point_subsets import process_case as extract_jawara_subset
from plot_paper_jawara import CaseConfig as PlotCaseConfig
from plot_paper_jawara import load_jawara_weighted, moving_nanmedian, plot_contours


JAWARA_OUT_DIR = Path("/Users/chartat1/data/jawara")
FIG_OUT_DIR = Path("/Users/chartat1/superdarn/winds/outputs/paper_jawara")

JAWARA_CASE_LOOKUP = {case.name: case for case in JAWARA_SUBSET_CASES}


CASES = [
    {
        "name": "fir_rio",
        "year": 2019,
        "mwr_mat": Path("/Users/chartat1/data/meteor_winds/notused_mat/riogrande_2019.mat"),
        "mwr_label": "RIO",
        "out_name": "fir_rio_jawara_contours.png",
    },
    {
        "name": "fir_sim",
        "year": 2020,
        "mwr_mat": Path("/Users/chartat1/data/meteor_winds/notused_mat/simone_2020.mat"),
        "mwr_label": "SIM",
        "out_name": "fir_sim_jawara_contours.png",
    },
]


def ensure_jawara_subset(session: requests.Session, year: int) -> Path:
    case = JAWARA_CASE_LOOKUP[f"fir_{year}"]
    out_path = jawara_case_output_path(JAWARA_OUT_DIR, case)
    if out_path.exists():
        return out_path

    extract_jawara_subset(session, case, list(range(1, 13)), JAWARA_OUT_DIR, max_ranges_per_request=256, workers=8)
    return out_path


def build_case_figure(session: requests.Session, case: dict[str, object]) -> Path:
    year = int(case["year"])
    sd_path = Path(f"/Users/chartat1/data/superdarn/fit_nc_3_winds/annual/{year}/fir_{year}.nc")
    sd = load_sd_annual(sd_path, "fir")
    mwr = load_mwr_mat(Path(case["mwr_mat"]))

    mwr_for_weight = {
        "u": mwr["u"],
        "v": mwr["v"],
        "alt": mwr["alt"],
        "hour": mwr["hour"],
        "day_doy": mwr["day_doy"],
        "lat": mwr["lat"],
        "lon": mwr["lon"],
    }
    mwr_u, mwr_v, _, _ = compute_mwr_modwt(mwr_for_weight, sd)

    good_days = np.sum(np.isfinite(sd["u"]), axis=0) >= 1
    mwr_u_med = moving_nanmedian(mwr_u, 31)
    mwr_v_med = moving_nanmedian(mwr_v, 31)
    sd_u_med = moving_nanmedian(sd["u"], 31)
    sd_v_med = moving_nanmedian(sd["v"], 31)

    jawara_nc = ensure_jawara_subset(session, year)
    jawara = load_jawara_weighted(jawara_nc, year, sd)
    jaw_u_med = moving_nanmedian(jawara["u_modwt"], 31)
    jaw_v_med = moving_nanmedian(jawara["v_modwt"], 31)

    lthri = np.arange(24, dtype=float)
    lt_mwr_u = ut_to_lt(mwr_u_med, mwr["hour"], lthri, mwr["lon"])
    lt_mwr_v = ut_to_lt(mwr_v_med, mwr["hour"], lthri, mwr["lon"])
    lt_sd_u = ut_to_lt(sd_u_med, sd["hour"], lthri, sd["lon"])
    lt_sd_v = ut_to_lt(sd_v_med, sd["hour"], lthri, sd["lon"])
    lt_jaw_u = ut_to_lt(jaw_u_med, lthri, lthri, jawara["lon"])
    lt_jaw_v = ut_to_lt(jaw_v_med, lthri, lthri, jawara["lon"])

    cfg = PlotCaseConfig(
        name=str(case["name"]),
        year=year,
        sd_code="fir",
        mwr_label=str(case["mwr_label"]),
        mwr_mat=Path(case["mwr_mat"]),
        jawara_sd_nc=jawara_nc,
        jawara_mwr_nc=jawara_nc,
        climit=(-50.0, 50.0),
    )

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / str(case["out_name"])
    plot_contours(
        out_path,
        cfg,
        lt_mwr_u,
        lt_mwr_v,
        lt_sd_u,
        lt_sd_v,
        lt_jaw_u,
        lt_jaw_v,
        float(mwr["lat"]),
        float(mwr["lon"]),
        float(sd["lat"]),
        float(sd["lon"]),
        good_days,
    )
    return out_path


def main() -> None:
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    session = requests.Session()
    session.verify = False
    needs_download = any(
        not jawara_case_output_path(JAWARA_OUT_DIR, JAWARA_CASE_LOOKUP[f"fir_{case['year']}"]).exists()
        for case in CASES
    )
    try:
        if needs_download:
            user = "alexchartier"
            password = "hj5kW}kQgPAx69F"
            jawara_login(session, user, password)
            print("Logged into JAWARA with approved access.", flush=True)
        for case in CASES:
            out_path = build_case_figure(session, case)
            print(f"Wrote {out_path}", flush=True)
    finally:
        session.close()


if __name__ == "__main__":
    main()
