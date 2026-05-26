#!/usr/bin/env python3
"""
Compute ISS near-conjunction intervals for Digisonde stations.

The script expects:
  * a Digisonde station list HTML page, and
  * an ISS TLE text file

By default both inputs are read from `artifacts/`, and the script writes:
  * a parsed station JSON cache
  * a CSV of near-conjunction intervals
  * a JSON summary of the same intervals

A near-conjunction is defined here as the ISS footpoint being within a
great-circle distance threshold of a station location.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
from sgp4.api import Satrec


WGS84_A_M = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
EARTH_RADIUS_KM = 6371.0088

DEFAULT_ARTIFACTS_DIR = Path("artifacts")
DEFAULT_STATION_HTML = DEFAULT_ARTIFACTS_DIR / "digisonde_stationlist.html"
DEFAULT_STATION_JSON = DEFAULT_ARTIFACTS_DIR / "digisonde_stationlist.json"
DEFAULT_TLE_FILE = DEFAULT_ARTIFACTS_DIR / "iss_stations.tle"
DEFAULT_OUTPUT_CSV = DEFAULT_ARTIFACTS_DIR / "iss_digisonde_near_conjunctions.csv"
DEFAULT_OUTPUT_JSON = DEFAULT_ARTIFACTS_DIR / "iss_digisonde_near_conjunctions.json"


@dataclass(frozen=True)
class Station:
    rank: int
    location: str
    system: str | None
    serial: str | None
    sid: str | None
    ursi: str | None
    lat_deg: float
    lon_deg: float
    operated_by: str | None
    contact: str | None
    comments: str | None


@dataclass(frozen=True)
class ConjunctionInterval:
    station_rank: int
    station_location: str
    station_ursi: str | None
    station_lat_deg: float
    station_lon_deg: float
    station_comments: str | None
    start_utc: str
    end_utc: str
    min_distance_km: float
    min_distance_utc: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute ISS near-conjunctions for Digisonde stations.")
    p.add_argument("--station-html", type=Path, default=DEFAULT_STATION_HTML, help="Digisonde station list HTML.")
    p.add_argument("--station-json", type=Path, default=DEFAULT_STATION_JSON, help="Parsed station JSON cache.")
    p.add_argument("--tle-file", type=Path, default=DEFAULT_TLE_FILE, help="ISS TLE file.")
    p.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV, help="CSV output path.")
    p.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON, help="JSON output path.")
    p.add_argument("--start-utc", type=str, default=None, help="Start timestamp in ISO-8601 UTC. Default: now.")
    p.add_argument("--months", type=int, default=2, help="How many calendar months to analyze. Default: 2.")
    p.add_argument("--step-seconds", type=int, default=60, help="Propagation cadence in seconds. Default: 60.")
    p.add_argument("--radius-km", type=float, default=1000.0, help="Great-circle threshold in km. Default: 1000.")
    p.add_argument(
        "--include-historical",
        action="store_true",
        help="Include moved/deactivated/test/campaign rows from the station list instead of filtering to current locations.",
    )
    return p.parse_args()


def add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, _days_in_month(year, month))
    return dt.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    this_month = datetime(year, month, 1, tzinfo=timezone.utc)
    return (next_month - this_month).days


def normalize_lon_deg(lon_east_deg: float) -> float:
    return ((lon_east_deg + 180.0) % 360.0) - 180.0


def parse_lat_lon(text: str) -> tuple[float, float]:
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if len(nums) < 2:
        raise ValueError(f"Could not parse latitude/longitude from {text!r}")
    return float(nums[0]), float(nums[1])


def load_station_table(html_path: Path, station_json_path: Path, include_historical: bool) -> list[Station]:
    html = html_path.read_text(encoding="utf-8", errors="replace")
    tables = pd.read_html(StringIO(html))
    station_df = None
    for table in tables:
        if table.shape[1] == 10:
            first_row = " ".join(str(x) for x in table.iloc[0].tolist())
            if "Station Location" in first_row and "URSI ID" in first_row:
                station_df = table
                break
    if station_df is None:
        raise RuntimeError(f"Could not locate the Digisonde station table in {html_path}")

    station_df = station_df.copy()
    station_df.columns = [
        "rank",
        "location",
        "system",
        "serial",
        "sid",
        "ursi",
        "latlon",
        "operated_by",
        "contact",
        "comments",
    ]
    station_df = station_df[pd.to_numeric(station_df["rank"], errors="coerce").notna()].copy()
    station_df["comments"] = station_df["comments"].fillna("").astype(str)

    if not include_historical:
        comment_text = station_df["comments"].str.strip().str.lower()
        keep = (comment_text == "") | comment_text.str.contains("current location")
        station_df = station_df[keep].copy()

    station_df = station_df.drop_duplicates(subset=["location", "system", "serial", "sid", "ursi", "latlon", "operated_by", "contact", "comments"]).copy()
    station_df["rank"] = station_df["rank"].astype(int)

    stations: list[Station] = []
    for _, row in station_df.sort_values(["rank", "location", "latlon"]).iterrows():
        lat_deg, lon_east_deg = parse_lat_lon(str(row["latlon"]))
        stations.append(
            Station(
                rank=int(row["rank"]),
                location=str(row["location"]).strip(),
                system=None if pd.isna(row["system"]) else str(row["system"]).strip(),
                serial=None if pd.isna(row["serial"]) else str(row["serial"]).strip(),
                sid=None if pd.isna(row["sid"]) else str(row["sid"]).strip(),
                ursi=None if pd.isna(row["ursi"]) else str(row["ursi"]).strip(),
                lat_deg=float(lat_deg),
                lon_deg=float(normalize_lon_deg(float(lon_east_deg))),
                operated_by=None if pd.isna(row["operated_by"]) else str(row["operated_by"]).strip(),
                contact=None if pd.isna(row["contact"]) else " ".join(str(row["contact"]).split()),
                comments=None if not str(row["comments"]).strip() else str(row["comments"]).strip(),
            )
        )

    station_json_path.write_text(
        json.dumps([asdict(station) for station in stations], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return stations


def load_iss_tle(path: Path) -> Satrec:
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"TLE file {path} does not contain an ISS element set.")
    if lines[0].startswith("1 "):
        line1, line2 = lines[0], lines[1]
    else:
        line1, line2 = lines[1], lines[2]
    return Satrec.twoline2rv(line1, line2)


def gmst_from_jd(jd_ut1: float) -> float:
    t = (jd_ut1 - 2451545.0) / 36525.0
    gmst_deg = (
        280.46061837
        + 360.98564736629 * (jd_ut1 - 2451545.0)
        + 0.000387933 * t * t
        - t * t * t / 38710000.0
    )
    return math.radians(gmst_deg % 360.0)


def teme_to_ecef(r_km: np.ndarray, jd_ut1: float) -> np.ndarray:
    theta = gmst_from_jd(jd_ut1)
    c = math.cos(theta)
    s = math.sin(theta)
    r_m = np.asarray(r_km, dtype=np.float64) * 1000.0
    return np.array([c * r_m[0] + s * r_m[1], -s * r_m[0] + c * r_m[1], r_m[2]], dtype=np.float64)


def ecef_to_geodetic(r_m: np.ndarray) -> tuple[float, float]:
    x, y, z = float(r_m[0]), float(r_m[1]), float(r_m[2])
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(6):
        sin_lat = math.sin(lat)
        n = WGS84_A_M / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
        lat = math.atan2(z + WGS84_E2 * n * sin_lat, p)
    return lat, lon


def datetime_to_jd(dt: datetime) -> float:
    return dt.timestamp() / 86400.0 + 2440587.5


def great_circle_km(lat1_rad: float, lon1_rad: float, lat2_rad: np.ndarray, lon2_rad: np.ndarray) -> np.ndarray:
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def format_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def calculate_conjunctions(
    sat: Satrec,
    stations: list[Station],
    start_utc: datetime,
    end_utc: datetime,
    step_seconds: int,
    radius_km: float,
) -> list[ConjunctionInterval]:
    station_lat_rad = np.radians(np.array([station.lat_deg for station in stations], dtype=np.float64))
    station_lon_rad = np.radians(np.array([station.lon_deg for station in stations], dtype=np.float64))

    active = np.zeros(len(stations), dtype=bool)
    interval_start = np.full(len(stations), np.nan, dtype=np.float64)
    min_dist = np.full(len(stations), np.inf, dtype=np.float64)
    min_time = np.full(len(stations), np.nan, dtype=np.float64)
    results: list[ConjunctionInterval] = []

    start_ts = start_utc.timestamp()
    end_ts = end_utc.timestamp()
    n_steps = int(math.floor((end_ts - start_ts) / step_seconds)) + 1

    for step_index in range(n_steps):
        ts = start_ts + step_index * step_seconds
        jd = datetime_to_jd(datetime.fromtimestamp(ts, tz=timezone.utc))
        jd0 = math.floor(jd)
        fr = jd - jd0
        err, r_km, _v_km_s = sat.sgp4(jd0, fr)
        if err != 0:
            raise RuntimeError(f"SGP4 propagation failed with code {err} at {format_dt(ts)}")

        ecef_m = teme_to_ecef(np.asarray(r_km, dtype=np.float64), jd)
        sat_lat_rad, sat_lon_rad = ecef_to_geodetic(ecef_m)
        distances = great_circle_km(sat_lat_rad, sat_lon_rad, station_lat_rad, station_lon_rad)
        hits = np.flatnonzero(distances <= radius_km)
        misses = np.flatnonzero(distances > radius_km)

        for idx in hits:
            if not active[idx]:
                active[idx] = True
                interval_start[idx] = ts
                min_dist[idx] = float(distances[idx])
                min_time[idx] = ts
            elif distances[idx] < min_dist[idx]:
                min_dist[idx] = float(distances[idx])
                min_time[idx] = ts

        for idx in misses:
            if active[idx]:
                results.append(
                    ConjunctionInterval(
                        station_rank=stations[idx].rank,
                        station_location=stations[idx].location,
                        station_ursi=stations[idx].ursi,
                        station_lat_deg=stations[idx].lat_deg,
                        station_lon_deg=stations[idx].lon_deg,
                        station_comments=stations[idx].comments,
                        start_utc=format_dt(float(interval_start[idx])),
                        end_utc=format_dt(ts - step_seconds),
                        min_distance_km=float(min_dist[idx]),
                        min_distance_utc=format_dt(float(min_time[idx])),
                    )
                )
                active[idx] = False
                interval_start[idx] = np.nan
                min_dist[idx] = np.inf
                min_time[idx] = np.nan

    for idx in np.flatnonzero(active):
        results.append(
            ConjunctionInterval(
                station_rank=stations[idx].rank,
                station_location=stations[idx].location,
                station_ursi=stations[idx].ursi,
                station_lat_deg=stations[idx].lat_deg,
                station_lon_deg=stations[idx].lon_deg,
                station_comments=stations[idx].comments,
                start_utc=format_dt(float(interval_start[idx])),
                end_utc=format_dt(end_ts),
                min_distance_km=float(min_dist[idx]),
                min_distance_utc=format_dt(float(min_time[idx])),
            )
        )

    results.sort(key=lambda item: (item.start_utc, item.station_rank, item.station_location))
    return results


def main() -> int:
    args = parse_args()

    if not args.station_html.exists():
        raise FileNotFoundError(f"Missing station HTML file: {args.station_html}")
    if not args.tle_file.exists():
        raise FileNotFoundError(f"Missing ISS TLE file: {args.tle_file}")

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.station_json.parent.mkdir(parents=True, exist_ok=True)

    stations = load_station_table(args.station_html, args.station_json, args.include_historical)
    sat = load_iss_tle(args.tle_file)

    start_utc = (
        datetime.fromisoformat(args.start_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
        if args.start_utc
        else datetime.now(timezone.utc)
    )
    end_utc = add_months(start_utc, args.months)

    intervals = calculate_conjunctions(
        sat=sat,
        stations=stations,
        start_utc=start_utc,
        end_utc=end_utc,
        step_seconds=args.step_seconds,
        radius_km=args.radius_km,
    )

    csv_rows = [asdict(interval) for interval in intervals]
    pd.DataFrame(csv_rows).to_csv(args.output_csv, index=False)

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "start_utc": start_utc.isoformat().replace("+00:00", "Z"),
        "end_utc": end_utc.isoformat().replace("+00:00", "Z"),
        "step_seconds": args.step_seconds,
        "radius_km": args.radius_km,
        "station_count": len(stations),
        "conjunction_count": len(intervals),
        "stations": [asdict(station) for station in stations],
        "intervals": csv_rows,
    }
    args.output_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Loaded {len(stations)} stations from {args.station_html}")
    print(f"Wrote parsed station list to {args.station_json}")
    print(f"Computed {len(intervals)} near-conjunction intervals from {start_utc.isoformat()} to {end_utc.isoformat()}")
    print(f"Wrote CSV to {args.output_csv}")
    print(f"Wrote JSON to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
