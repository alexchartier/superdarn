#!/usr/bin/env python3
"""
Detect SuperDARN 8-pulse katscan transmissions in a DigitalRF recording,
using ISS ephemeris to gate the analysis window and the SuperDARN hardware
tables to pick the closest operational radar to the ISS.

The output mirrors the ephemeris-gated WWV tooling style:
- an ISS-gated analysis window,
- a map-style overpass ground track with land and country outlines,
- predicted range and Doppler time series,
- a matched-filter stack plot,
- CSV and JSON summaries.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from detect_wwv_ticks_iss_ephem import (
    compute_iss_range_profile,
    datetime_to_unix_seconds,
    epoch_to_datetime,
    generate_ancillary_csv_from_tle,
    load_iss_ephemeris_csv,
    j2000_to_ecef_m,
    select_gate_window,
)
from drf_compat import open_drf_like_reader
from stack_superdarn_iss_ephem import (
    average_rows,
    correct_frames,
    frame_pris,
    geodetic_to_ecef,
    load_decimated_channel,
    matched_corr,
    plot_results,
    search_residuals,
    template_metadata,
    SEQUENCES as BASE_SEQUENCES,
)


SEQUENCES = dict(BASE_SEQUENCES)
SEQUENCES["katscan"] = dict(BASE_SEQUENCES["8p"])

C_MPS = 299_792_458.0
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


@dataclass(frozen=True)
class RadarSite:
    name: str
    station_id: int
    status: int
    valid_from: datetime
    lat_deg: float
    lon_deg: float
    alt_m: float
    boresight_deg: float
    beam_sep_deg: float


def _center_hz_from_properties(props: dict[str, object]) -> float | None:
    for key in ("center_frequency_hz", "center_frequency", "center_freq_hz", "cf_hz"):
        value = props.get(key)
        if value not in (None, ""):
            return float(value)
    return None


def _parse_hdw_file(path: Path) -> list[RadarSite]:
    sites: list[RadarSite] = []
    name = path.name.split("hdw.dat.", 1)[-1]
    with path.open() as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 11:
                continue
            try:
                station_id = int(parts[0])
                status = int(parts[1])
                valid_from = datetime.strptime(f"{parts[2]} {parts[3]}", "%Y%m%d %H:%M:%S").replace(tzinfo=timezone.utc)
                lat_deg = float(parts[4])
                lon_deg = float(parts[5])
                alt_m = float(parts[6])
                boresight_deg = float(parts[7])
                beam_sep_deg = float(parts[9])
            except ValueError:
                continue
            sites.append(
                RadarSite(
                    name=name,
                    station_id=station_id,
                    status=status,
                    valid_from=valid_from,
                    lat_deg=lat_deg,
                    lon_deg=lon_deg,
                    alt_m=alt_m,
                    boresight_deg=boresight_deg,
                    beam_sep_deg=beam_sep_deg,
                )
            )
    return sites


def _load_hdw_sites(hdw_root: Path, when_utc: datetime) -> list[RadarSite]:
    sites: list[RadarSite] = []
    for path in sorted(hdw_root.glob("hdw.dat.*")):
        entries = _parse_hdw_file(path)
        if not entries:
            continue
        candidates = [site for site in entries if site.valid_from <= when_utc]
        if not candidates:
            continue
        latest = max(candidates, key=lambda s: s.valid_from)
        if latest.status != 1:
            continue
        sites.append(latest)
    if not sites:
        raise RuntimeError(f"No active SuperDARN hardware files found in {hdw_root}")
    return sites


def _select_radar(
    sites: list[RadarSite],
    ephem_times_s: np.ndarray,
    ephem_positions_m: np.ndarray,
    *,
    radar_name: str | None = None,
) -> tuple[RadarSite, np.ndarray, float, int]:
    if radar_name is not None:
        for site in sites:
            if site.name == radar_name:
                radar_ecef = geodetic_to_ecef(site.lat_deg, site.lon_deg, site.alt_m)
                range_km = compute_iss_range_profile(ephem_times_s, ephem_positions_m, radar_ecef)
                min_idx = int(np.argmin(range_km))
                return site, range_km, float(range_km[min_idx]), min_idx
        available = ", ".join(sorted(site.name for site in sites))
        raise RuntimeError(f"Requested radar {radar_name!r} not found. Available: {available}")

    best_site: RadarSite | None = None
    best_range_km: np.ndarray | None = None
    best_min_range_km = float("inf")
    best_min_idx = 0
    for site in sites:
        radar_ecef = geodetic_to_ecef(site.lat_deg, site.lon_deg, site.alt_m)
        range_km = compute_iss_range_profile(ephem_times_s, ephem_positions_m, radar_ecef)
        min_idx = int(np.argmin(range_km))
        min_range_km = float(range_km[min_idx])
        if min_range_km < best_min_range_km:
            best_site = site
            best_range_km = range_km
            best_min_range_km = min_range_km
            best_min_idx = min_idx

    if best_site is None or best_range_km is None:
        raise RuntimeError("Unable to select a closest radar.")
    return best_site, best_range_km, best_min_range_km, best_min_idx


def ecef_to_geodetic(r_m: np.ndarray) -> tuple[float, float]:
    x, y, z = float(r_m[0]), float(r_m[1]), float(r_m[2])
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(6):
        sin_lat = math.sin(lat)
        n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
        lat = math.atan2(z + WGS84_E2 * n * sin_lat, p)
    return lat, lon


def _predict_delay_doppler_from_ephemeris(
    ephem_times_s: np.ndarray,
    ephem_positions_m: np.ndarray,
    frame_times_s: np.ndarray,
    radar_ecef_m: np.ndarray,
    carrier_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    if frame_times_s.size == 0:
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)
    if ephem_times_s.size < 2:
        raise RuntimeError("Need at least two ephemeris samples to predict delay and Doppler.")

    frame_pos = np.empty((frame_times_s.size, 3), dtype=np.float64)
    for i in range(3):
        frame_pos[:, i] = np.interp(frame_times_s, ephem_times_s, ephem_positions_m[:, i])
    ranges_m = np.linalg.norm(frame_pos - radar_ecef_m[None, :], axis=1)
    delay_s = ranges_m / C_MPS
    if frame_times_s.size >= 2:
        range_rate_mps = np.gradient(ranges_m, frame_times_s, edge_order=1)
        doppler_hz = -carrier_hz * range_rate_mps / C_MPS
    else:
        doppler_hz = np.zeros_like(delay_s)
    return delay_s, doppler_hz


def _plot_ephemeris_gate(
    path: Path,
    ephem_times_s: np.ndarray,
    ranges_km: np.ndarray,
    gate_start_s: float,
    gate_end_s: float,
    gate_center_s: float,
    gate_margin_km: float,
    radar_name: str,
) -> Optional[Path]:
    try:
        import matplotlib.dates as mdates  # type: ignore
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # pragma: no cover - optional
        print(f"Ephemeris gate plot skipped (matplotlib not available: {exc})")
        return None

    times = [datetime.fromtimestamp(ts, tz=timezone.utc) for ts in ephem_times_s]
    fig, ax = plt.subplots(figsize=(12.5, 5.5))
    ax.plot(times, ranges_km, color="black", linewidth=1.2)
    ax.axvspan(
        datetime.fromtimestamp(gate_start_s, tz=timezone.utc),
        datetime.fromtimestamp(gate_end_s, tz=timezone.utc),
        color="tab:orange",
        alpha=0.2,
        label="Selected analysis window",
    )
    ax.axvline(datetime.fromtimestamp(gate_center_s, tz=timezone.utc), color="tab:red", linestyle="--", linewidth=1.0)
    ax.axhline(ranges_km.min() + gate_margin_km, color="tab:blue", linestyle=":", linewidth=1.0, label="Gate threshold")
    ax.set_title(f"ISS ephemeris gate toward SuperDARN radar {radar_name}")
    ax.set_xlabel("UTC time")
    ax.set_ylabel("Slant range to radar (km)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print(f"Wrote {path}")
    return path


def _plot_overpass_map(
    path: Path,
    ephem_times_s: np.ndarray,
    ephem_positions_m: np.ndarray,
    radar_site: RadarSite,
    gate_start_s: float,
    gate_end_s: float,
    min_idx: int,
    gate_center_s: float,
) -> Optional[Path]:
    try:
        import cartopy.crs as ccrs  # type: ignore
        import cartopy.feature as cfeature  # type: ignore
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # pragma: no cover - optional
        print(f"Overpass map plot skipped (cartopy/matplotlib not available: {exc})")
        return None

    if ephem_times_s.size == 0:
        print("Overpass map plot skipped (no ephemeris samples).")
        return None

    sat_lat = np.empty(ephem_times_s.size, dtype=np.float64)
    sat_lon = np.empty(ephem_times_s.size, dtype=np.float64)
    for i, (ts, pos) in enumerate(zip(ephem_times_s, ephem_positions_m)):
        sat_ecef = j2000_to_ecef_m(pos, float(ts))
        lat_rad, lon_rad = ecef_to_geodetic(sat_ecef)
        sat_lat[i] = math.degrees(lat_rad)
        sat_lon[i] = math.degrees(lon_rad)

    gate_mask = (ephem_times_s >= gate_start_s) & (ephem_times_s <= gate_end_s)
    if not np.any(gate_mask):
        gate_mask = np.ones_like(ephem_times_s, dtype=bool)

    fig = plt.figure(figsize=(11.5, 7.0))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_facecolor("#dbe8f5")
    ocean = cfeature.NaturalEarthFeature("physical", "ocean", "50m", facecolor="#dbe8f5", edgecolor="none")
    land = cfeature.NaturalEarthFeature("physical", "land", "50m", facecolor="#efefe8", edgecolor="none")
    coast = cfeature.NaturalEarthFeature("physical", "coastline", "50m", facecolor="none", edgecolor="0.25")
    borders = cfeature.NaturalEarthFeature(
        "cultural",
        "admin_0_boundary_lines_land",
        "50m",
        facecolor="none",
        edgecolor="0.35",
    )
    lakes = cfeature.NaturalEarthFeature("physical", "lakes", "50m", facecolor="#dbe8f5", edgecolor="0.4")
    ax.add_feature(ocean, zorder=0)
    ax.add_feature(land, zorder=0)
    ax.add_feature(lakes, linewidth=0.4, zorder=0)
    ax.add_feature(coast, linewidth=0.7, zorder=1)
    ax.add_feature(borders, linewidth=0.5, zorder=1)
    ax.plot(sat_lon, sat_lat, color="0.65", lw=1.0, zorder=2, label="ISS track", transform=ccrs.PlateCarree())
    sc = ax.scatter(
        sat_lon,
        sat_lat,
        c=(ephem_times_s - ephem_times_s[0]),
        cmap="viridis",
        s=14,
        linewidths=0.0,
        zorder=3,
        transform=ccrs.PlateCarree(),
    )
    ax.plot(
        sat_lon[gate_mask],
        sat_lat[gate_mask],
        color="tab:orange",
        lw=2.0,
        zorder=4,
        label="Selected gate",
        transform=ccrs.PlateCarree(),
    )
    ax.scatter(
        [sat_lon[min_idx]],
        [sat_lat[min_idx]],
        marker="*",
        s=140,
        color="tab:red",
        edgecolors="black",
        linewidths=0.6,
        zorder=5,
        label="Closest approach",
        transform=ccrs.PlateCarree(),
    )
    ax.scatter(
        [radar_site.lon_deg],
        [radar_site.lat_deg],
        marker="^",
        s=120,
        color="tab:blue",
        edgecolors="black",
        linewidths=0.6,
        zorder=6,
        label=f"Radar {radar_site.name}",
        transform=ccrs.PlateCarree(),
    )
    ax.annotate(
        radar_site.name,
        (radar_site.lon_deg, radar_site.lat_deg),
        xytext=(6, 6),
        textcoords="offset points",
        fontsize=9,
        color="tab:blue",
    )
    ax.annotate(
        "closest approach",
        (sat_lon[min_idx], sat_lat[min_idx]),
        xytext=(6, -12),
        textcoords="offset points",
        fontsize=9,
        color="tab:red",
    )

    lon_min = float(np.min(np.concatenate([sat_lon, np.array([radar_site.lon_deg], dtype=np.float64)])))
    lon_max = float(np.max(np.concatenate([sat_lon, np.array([radar_site.lon_deg], dtype=np.float64)])))
    lat_min = float(np.min(np.concatenate([sat_lat, np.array([radar_site.lat_deg], dtype=np.float64)])))
    lat_max = float(np.max(np.concatenate([sat_lat, np.array([radar_site.lat_deg], dtype=np.float64)])))

    lon_pad = max(2.5, 0.15 * (lon_max - lon_min + 1e-9))
    lat_pad = max(2.5, 0.15 * (lat_max - lat_min + 1e-9))
    ax.set_extent(
        [
            lon_min - lon_pad,
            lon_max + lon_pad,
            lat_min - lat_pad,
            lat_max + lat_pad,
        ],
        crs=ccrs.PlateCarree(),
    )
    ax.set_xlabel("Longitude (deg E)")
    ax.set_ylabel("Latitude (deg N)")
    ax.set_title(
        f"ISS overpass ground track toward {radar_site.name}\n"
        f"Gate centered at {datetime.fromtimestamp(gate_center_s, tz=timezone.utc).isoformat()}"
    )
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        linewidth=0.5,
        color="0.45",
        alpha=0.4,
        linestyle=":",
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {"size": 9}
    gl.ylabel_style = {"size": 9}
    cbar = fig.colorbar(sc, ax=ax, pad=0.02)
    cbar.set_label("Seconds from ephemeris start")
    ax.legend(loc="best")

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print(f"Wrote {path}")
    return path


def _radar_site_payload(site: RadarSite) -> dict[str, object]:
    return {
        "name": site.name,
        "station_id": site.station_id,
        "status": site.status,
        "valid_from": site.valid_from.isoformat(),
        "lat_deg": site.lat_deg,
        "lon_deg": site.lon_deg,
        "alt_m": site.alt_m,
        "boresight_deg": site.boresight_deg,
        "beam_sep_deg": site.beam_sep_deg,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Detect SuperDARN 8-pulse katscan transmissions with ISS ephemeris and auto-selected radar geometry."
    )
    p.add_argument("--dataset-root", type=Path, required=True, help="DigitalRF dataset root.")
    p.add_argument("--channel", default=None, help="Channel name. Default: first channel in the dataset.")
    p.add_argument(
        "--sequence",
        choices=sorted(SEQUENCES),
        default="katscan",
        help="Pulse sequence to match. Default: katscan (alias for the repo's 8-pulse sequence).",
    )
    p.add_argument(
        "--ephemeris-file",
        type=Path,
        default=None,
        help="ISS ephemeris CSV file with timestamp and j2000_p_* columns. Default: Ancillary.csv in the dataset root.",
    )
    p.add_argument(
        "--tle-file",
        type=Path,
        default=None,
        help="ISS TLE file used to generate Ancillary.csv when it is missing, and for predicted overlays.",
    )
    p.add_argument(
        "--ephemeris-step-seconds",
        type=float,
        default=1.0,
        help="Cadence for generated ancillary samples when --tle-file is used. Default: 1.0.",
    )
    p.add_argument(
        "--regenerate-ephemeris",
        action="store_true",
        help="Regenerate the ephemeris CSV from --tle-file even if it already exists.",
    )
    p.add_argument(
        "--hdw-root",
        type=Path,
        default=Path("~/rst/tables/superdarn/hdw"),
        help="Directory containing hdw.dat.* files. Default: ~/rst/tables/superdarn/hdw.",
    )
    p.add_argument(
        "--radar-name",
        default=None,
        help="Force a specific radar from hdw.dat.* instead of auto-selecting the closest one.",
    )
    p.add_argument(
        "--target-hz",
        type=float,
        default=None,
        help="Carrier to mix to baseband. Default: the channel center frequency.",
    )
    p.add_argument("--skip-seconds", type=float, default=0.0, help="Seconds to trim from the start of the gate.")
    p.add_argument("--end-seconds", type=float, default=0.0, help="Seconds to trim from the end of the gate.")
    p.add_argument("--seconds", type=float, default=None, help="Limit the gated analysis to this many seconds.")
    p.add_argument("--gate-margin-km", type=float, default=1000.0, help="Gate around the minimum range within this margin.")
    p.add_argument("--gate-pad-seconds", type=float, default=120.0, help="Pad the selected gate on both sides.")
    p.add_argument("--channel-rate", type=float, default=None, help="Intermediate rate after decimation (Hz).")
    p.add_argument("--channel-lp-hz", type=float, default=5000.0, help="Lowpass cutoff after mixing in Hz.")
    p.add_argument("--decimated-rate", type=float, default=100000.0, help="Post-filter sample rate in Hz.")
    p.add_argument("--raw-chunk-seconds", type=float, default=2.0, help="Raw read chunk size in seconds.")
    p.add_argument("--residual-span-hz", type=float, default=50.0, help="Residual frequency half-span after ephemeris correction.")
    p.add_argument("--residual-step-hz", type=float, default=2.0, help="Residual frequency step after ephemeris correction.")
    p.add_argument(
        "--residual-lag-span-ms",
        type=float,
        default=4.0,
        help="Residual lag half-span after ephemeris correction in ms.",
    )
    p.add_argument("--average-pris", type=int, default=32, help="Average this many consecutive PRI rows.")
    p.add_argument(
        "--output-prefix",
        type=Path,
        default=None,
        help="Prefix for PNG, CSV, and JSON outputs. Default: derived from dataset/channel/radar/sequence.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = SEQUENCES[args.sequence]
    hdw_root = args.hdw_root.expanduser()

    reader, resolved_channel, reader_mode = open_drf_like_reader(args.dataset_root, args.channel)
    if reader_mode != "digital_rf":
        print(f"Using flat Data/rf@*.h5 reader for channel {resolved_channel} under {args.dataset_root}")

    channel = resolved_channel
    props = reader.get_properties(channel)
    fs_in = float(props["samples_per_second"])
    center_hz = _center_hz_from_properties(props)
    if center_hz is None:
        raise RuntimeError("Could not infer center frequency from channel properties.")
    target_hz = center_hz if args.target_hz is None else float(args.target_hz)

    start_sample, stop_sample = reader.get_bounds(channel)
    if start_sample is None or stop_sample is None:
        raise RuntimeError("Dataset bounds are unavailable.")
    start_sample = int(start_sample)
    stop_sample = int(stop_sample)

    epoch = epoch_to_datetime(props["epoch"])
    recording_start_utc = epoch + timedelta(seconds=start_sample / fs_in)
    recording_end_utc = epoch + timedelta(seconds=stop_sample / fs_in)
    recording_start_unix = datetime_to_unix_seconds(recording_start_utc)
    recording_end_unix = datetime_to_unix_seconds(recording_end_utc)

    ephemeris_file = args.ephemeris_file.expanduser() if args.ephemeris_file is not None else args.dataset_root.expanduser() / "Ancillary.csv"
    tle_file = args.tle_file.expanduser() if args.tle_file is not None else None
    if args.regenerate_ephemeris or not ephemeris_file.exists():
        if tle_file is None:
            raise FileNotFoundError(
                f"Missing ISS ephemeris file {ephemeris_file}. Pass --tle-file to generate it, or place Ancillary.csv in the dataset root."
            )
        print(f"Generating ephemeris CSV from {tle_file} -> {ephemeris_file}")
        generate_ancillary_csv_from_tle(
            ephemeris_file,
            tle_file,
            recording_start_utc,
            recording_end_utc,
            float(args.ephemeris_step_seconds),
        )

    ephem_times_s, ephem_positions_m = load_iss_ephemeris_csv(ephemeris_file)
    in_recording = (ephem_times_s >= recording_start_unix) & (ephem_times_s <= recording_end_unix)
    if not np.any(in_recording):
        raise RuntimeError(
            "No ephemeris samples overlap the recording span. Check the dataset epoch, ephemeris file, and channel bounds."
        )
    ephem_times_s = ephem_times_s[in_recording]
    ephem_positions_m = ephem_positions_m[in_recording]

    radar_sites = _load_hdw_sites(hdw_root, recording_start_utc)
    selected_site, selected_range_km, min_range_km, min_idx = _select_radar(
        radar_sites,
        ephem_times_s,
        ephem_positions_m,
        radar_name=args.radar_name,
    )
    selected_radar_ecef = geodetic_to_ecef(selected_site.lat_deg, selected_site.lon_deg, selected_site.alt_m)

    gate_start_s, gate_end_s, gate_center_s, gate_min_range_km = select_gate_window(
        ephem_times_s,
        selected_range_km,
        margin_km=float(args.gate_margin_km),
        pad_seconds=float(args.gate_pad_seconds),
    )
    gate_start_s = max(gate_start_s, recording_start_unix)
    gate_end_s = min(gate_end_s, recording_end_unix)
    if gate_start_s >= gate_end_s:
        raise RuntimeError("Ephemeris gate collapsed after clipping to the recording span.")
    if args.skip_seconds > 0:
        gate_start_s += float(args.skip_seconds)
    if args.end_seconds > 0:
        gate_end_s -= float(args.end_seconds)
    if args.seconds is not None:
        gate_end_s = min(gate_end_s, gate_start_s + float(args.seconds))
    if gate_start_s >= gate_end_s:
        raise RuntimeError("Requested trims leave an empty analysis window.")

    gate_start_sample = int(start_sample + int(math.floor((gate_start_s - recording_start_unix) * fs_in)))
    gate_end_sample = int(start_sample + int(math.ceil((gate_end_s - recording_start_unix) * fs_in)) - 1)
    gate_start_sample = max(gate_start_sample, start_sample)
    gate_end_sample = min(gate_end_sample, stop_sample)
    if gate_start_sample >= gate_end_sample:
        raise RuntimeError("Ephemeris-selected sample window is empty.")

    gate_start_utc = epoch + timedelta(seconds=gate_start_sample / fs_in)
    gate_end_utc = epoch + timedelta(seconds=gate_end_sample / fs_in)

    if args.output_prefix is None:
        args.output_prefix = Path(f"superdarn_{channel}_{selected_site.name}_{args.sequence}_iss_ephem")
    png_path = args.output_prefix.with_suffix(".png")
    csv_path = args.output_prefix.with_suffix(".csv")
    json_path = args.output_prefix.with_suffix(".json")
    gate_plot_path = args.output_prefix.with_name(args.output_prefix.name + "_gate").with_suffix(".png")
    map_plot_path = args.output_prefix.with_name(args.output_prefix.name + "_map").with_suffix(".png")

    print(f"Dataset root: {args.dataset_root}")
    print(f"Channel: {channel} (reader mode: {reader_mode})")
    print(f"Ephemeris file: {ephemeris_file}")
    print(f"HDW root: {hdw_root}")
    print(
        f"Selected radar: {selected_site.name} (station_id={selected_site.station_id}, "
        f"lat={selected_site.lat_deg:.5f}, lon={selected_site.lon_deg:.5f}, alt={selected_site.alt_m:.1f} m)"
    )
    print(f"Closest radar range in clipped ephemeris: {min_range_km:.1f} km at sample {min_idx}")
    print(f"Gate minimum range after selection: {gate_min_range_km:.1f} km")
    print(f"Center frequency: {center_hz/1e6:.6f} MHz")
    print(f"Target frequency: {target_hz/1e6:.6f} MHz")
    print(
        f"Recording span: {recording_start_utc.isoformat()} to {recording_end_utc.isoformat()} "
        f"({(stop_sample - start_sample + 1) / fs_in:.1f} s)"
    )
    print(f"Selected analysis window: {gate_start_utc.isoformat()} to {gate_end_utc.isoformat()}")
    print(f"Selected sample span: {gate_start_sample} to {gate_end_sample}")

    _plot_ephemeris_gate(
        gate_plot_path,
        ephem_times_s,
        selected_range_km,
        gate_start_s,
        gate_end_s,
        gate_center_s,
        float(args.gate_margin_km),
        selected_site.name,
    )
    _plot_overpass_map(
        map_plot_path,
        ephem_times_s,
        ephem_positions_m,
        selected_site,
        gate_start_s,
        gate_end_s,
        min_idx,
        gate_center_s,
    )

    block_samples = int(round(1.0 * fs_in))
    if block_samples < 1:
        raise ValueError("block_seconds too small for the input rate.")

    total_samples = gate_end_sample - gate_start_sample + 1
    total_seconds = total_samples / fs_in
    total_blocks = int(math.ceil(total_samples / block_samples))
    print(f"Processing {total_seconds:.1f} s in {total_blocks} blocks from {args.dataset_root}.", flush=True)

    desired_channel_rate = fs_in if args.channel_rate is None else min(float(args.channel_rate), fs_in)
    decim = int(round(fs_in / desired_channel_rate))
    if decim < 1:
        decim = 1
    channel_rate = fs_in / decim
    if decim > 1 and abs(channel_rate - desired_channel_rate) > 1e-3:
        raise ValueError(f"Cannot reach channel_rate={args.channel_rate} from fs_in={fs_in}.")

    y = load_decimated_channel(
        reader,
        channel=channel,
        start_sample=gate_start_sample,
        total_samples=total_samples,
        fs_in=fs_in,
        fs_out=args.decimated_rate,
        center_hz=center_hz,
        target_hz=target_hz,
        lp_hz=args.channel_lp_hz,
        raw_chunk_seconds=args.raw_chunk_seconds,
    )
    if y.size == 0:
        raise RuntimeError("No decimated samples produced.")

    frames, frame_times_s = frame_pris(y, args.decimated_rate, gate_start_sample, fs_in, float(cfg["pri_s"]))
    delay_s, doppler_hz = _predict_delay_doppler_from_ephemeris(
        ephem_times_s,
        ephem_positions_m,
        frame_times_s,
        selected_radar_ecef,
        target_hz,
    )
    corrected = correct_frames(frames, args.decimated_rate, delay_s, doppler_hz)

    offsets, pulse_samples = template_metadata(cfg, args.decimated_rate)
    residual_hz, residual_lag = search_residuals(
        corrected,
        fs_hz=args.decimated_rate,
        offsets=offsets,
        pulse_samples=pulse_samples,
        residual_span_hz=args.residual_span_hz,
        residual_step_hz=args.residual_step_hz,
        residual_lag_span_ms=args.residual_lag_span_ms,
    )

    t = np.arange(corrected.shape[1], dtype=np.float64) / args.decimated_rate
    corrected *= np.exp(-2j * np.pi * residual_hz * t).astype(np.complex64)[None, :]
    corr = matched_corr(corrected, offsets, pulse_samples)

    lag_half = int(round(args.residual_lag_span_ms * 1e-3 * args.decimated_rate))
    lo = max(0, residual_lag - lag_half)
    hi = min(corr.shape[1], residual_lag + lag_half + 1)
    power = (np.abs(corr[:, lo:hi]).astype(np.float32) ** 2)
    power = average_rows(power, args.average_pris)

    lag_ms = np.arange(lo, hi, dtype=np.float64) * 1e3 / args.decimated_rate
    best_lag_ms = residual_lag * 1e3 / args.decimated_rate

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["utc_time", "predicted_delay_ms", "predicted_doppler_hz"])
        for ts, dly, dop in zip(frame_times_s, delay_s, doppler_hz):
            writer.writerow(
                [
                    datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat(),
                    f"{dly * 1e3:.3f}",
                    f"{dop:.3f}",
                ]
            )

    plot_results(
        png_path,
        power=power,
        lag_ms=lag_ms,
        best_lag_ms=best_lag_ms,
        residual_hz=residual_hz,
        delay_ms=delay_s * 1e3,
        doppler_hz=doppler_hz,
        avg_pris=args.average_pris,
        dataset_name=f"{args.dataset_root.name} [{selected_site.name}]",
        sequence_label=args.sequence,
    )

    result = {
        "dataset_root": str(args.dataset_root),
        "channel": channel,
        "reader_mode": reader_mode,
        "center_hz": float(center_hz),
        "target_hz": float(target_hz),
        "sequence": args.sequence,
        "pulse_sequence": cfg["pulse_sequence"],
        "tau_us": cfg["tau_us"],
        "pulse_len_us": cfg["pulse_len_us"],
        "pri_s": cfg["pri_s"],
        "hdw_root": str(hdw_root),
        "selected_radar": _radar_site_payload(selected_site),
        "closest_range_km": float(min_range_km),
        "gate_min_range_km": float(gate_min_range_km),
        "seconds": float(total_seconds),
        "channel_lpf_hz": float(args.channel_lp_hz),
        "decimated_rate_hz": float(args.decimated_rate),
        "delay_ms_min": float(np.min(delay_s) * 1e3),
        "delay_ms_max": float(np.max(delay_s) * 1e3),
        "doppler_hz_min": float(np.min(doppler_hz)),
        "doppler_hz_max": float(np.max(doppler_hz)),
        "delay_ms_start": float(delay_s[0] * 1e3),
        "delay_ms_end": float(delay_s[-1] * 1e3),
        "doppler_hz_start": float(doppler_hz[0]),
        "doppler_hz_end": float(doppler_hz[-1]),
        "residual_hz": float(residual_hz),
        "best_residual_lag_ms": float(best_lag_ms),
        "average_pris": int(args.average_pris),
        "pri_groups": int(power.shape[0]),
        "output_png": str(png_path),
        "output_csv": str(csv_path),
        "gate_plot": str(gate_plot_path),
        "map_plot": str(map_plot_path),
        "ephemeris_file": str(ephemeris_file),
        "tle_file": None if tle_file is None else str(tle_file),
    }
    json_path.write_text(json.dumps(result, indent=2))

    print(f"Saved plot: {png_path}")
    print(f"Saved gate plot: {gate_plot_path}")
    print(f"Saved map plot: {map_plot_path}")
    print(f"Saved time-series CSV: {csv_path}")
    print(f"Saved summary: {json_path}")
    print(f"Predicted delay: {delay_s[0]*1e3:.3f} -> {delay_s[-1]*1e3:.3f} ms")
    print(f"Predicted doppler: {doppler_hz[0]:+.1f} -> {doppler_hz[-1]:+.1f} Hz")
    print(f"Residual correction: {residual_hz:+.1f} Hz, lag {best_lag_ms:.3f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
