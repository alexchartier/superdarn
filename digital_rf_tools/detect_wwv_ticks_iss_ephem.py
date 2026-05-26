#!/usr/bin/env python3
"""
Detect WWV 1 kHz tick leading edges from a DigitalRF recording after
automatically gating the analysis window using the ISS ephemeris in
`Ancillary.csv`.

The gate is chosen from the ISS slant-range curve to the WWV Fort Collins
transmitter:
1) load the ISS state vectors from Ancillary.csv,
2) convert the recorded J2000 positions to an Earth-fixed frame,
3) find the closest-approach interval around the minimum range,
4) analyze only that slice with the existing WWV tick detector.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import numpy as np
from scipy import signal

import detect_wwv_ticks as base
from drf_compat import open_drf_like_reader
from stack_superdarn_iss_ephem import geodetic_to_ecef, gmst_from_jd, load_tle, predict_delay_doppler


os.environ.setdefault("MPLBACKEND", "Agg")

DEFAULT_INPUT_ROOT = Path("/Users/chartat1/data/hf_data/itsi/iss/GMT132/M30023A")
DEFAULT_CHANNEL = None
DEFAULT_CHANNEL_RATE = None
DEFAULT_CHANNEL_LP_HZ = base.DEFAULT_CHANNEL_LP_HZ
DEFAULT_CHANNEL_TRANSITION_HZ = base.DEFAULT_CHANNEL_TRANSITION_HZ
DEFAULT_BP_LOW_HZ = base.DEFAULT_BP_LOW_HZ
DEFAULT_BP_HIGH_HZ = base.DEFAULT_BP_HIGH_HZ
DEFAULT_BP_TRANSITION_HZ = base.DEFAULT_BP_TRANSITION_HZ
DEFAULT_TONE_HZ = base.DEFAULT_TONE_HZ
DEFAULT_TONE_CYCLES = base.DEFAULT_TONE_CYCLES
DEFAULT_SIGMA_THRESHOLD = base.DEFAULT_SIGMA_THRESHOLD
DEFAULT_RANGE_PLOT = Path("wwv_range_time_iss_ephem.png")
DEFAULT_RANGE_MAX_KM = base.DEFAULT_RANGE_MAX_KM
DEFAULT_RANGE_MIN_KM = base.DEFAULT_RANGE_MIN_KM
DEFAULT_CARRIER_LP_HZ = base.DEFAULT_CARRIER_LP_HZ
DEFAULT_START_SECONDS = base.DEFAULT_START_SECONDS
DEFAULT_END_SECONDS = base.DEFAULT_END_SECONDS
DEFAULT_GATE_MARGIN_KM = 1000.0
DEFAULT_GATE_PAD_SECONDS = 120.0
DEFAULT_EPH_PLOT = Path("wwv_iss_ephemeris_gate.png")
DEFAULT_EPHEMERIS_STEP_SECONDS = 1.0

WWV_TX_LAT_DEG = 40.68069444444444
WWV_TX_LON_DEG = -105.04072222222223
WWV_TX_ALT_M = 1525.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Detect WWV 1 kHz ticks from DigitalRF, using ISS ephemeris to gate the analysis window."
    )
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help=f"DigitalRF dataset root. Default: {DEFAULT_INPUT_ROOT}.",
    )
    p.add_argument("--channel", default=DEFAULT_CHANNEL, help="Channel name. Default: auto-select the first channel.")
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
        default=DEFAULT_EPHEMERIS_STEP_SECONDS,
        help=f"Cadence for generated ancillary samples when --tle-file is used. Default: {DEFAULT_EPHEMERIS_STEP_SECONDS:g}.",
    )
    p.add_argument(
        "--regenerate-ephemeris",
        action="store_true",
        help="Regenerate the ephemeris CSV from --tle-file even if it already exists.",
    )
    p.add_argument(
        "--raw-center-hz",
        type=float,
        default=None,
        help="Recorded center frequency (Hz). Default: DigitalRF metadata center_frequency_hz when present.",
    )
    p.add_argument(
        "--target-hz",
        type=float,
        default=None,
        help="Target carrier to demodulate (Hz). Default: the channel center frequency.",
    )
    p.add_argument(
        "--block-seconds",
        type=float,
        default=base.DEFAULT_BLOCK_SECONDS,
        help=f"Seconds of RF to process per block. Default: {base.DEFAULT_BLOCK_SECONDS:g}.",
    )
    p.add_argument(
        "--channel-rate",
        type=float,
        default=DEFAULT_CHANNEL_RATE,
        help="Intermediate rate after decimation (Hz). Default: the DigitalRF sample rate.",
    )
    p.add_argument(
        "--channel-lp-hz",
        type=float,
        default=DEFAULT_CHANNEL_LP_HZ,
        help=f"Channel lowpass cutoff before envelope detection (Hz). Default: {DEFAULT_CHANNEL_LP_HZ:g}.",
    )
    p.add_argument(
        "--channel-transition-hz",
        type=float,
        default=DEFAULT_CHANNEL_TRANSITION_HZ,
        help=f"Transition width for the channel lowpass (Hz). Default: {DEFAULT_CHANNEL_TRANSITION_HZ:g}.",
    )
    p.add_argument(
        "--bp-low-hz",
        type=float,
        default=DEFAULT_BP_LOW_HZ,
        help=f"Bandpass low cutoff for the 1 kHz tone (Hz). Default: {DEFAULT_BP_LOW_HZ:g}.",
    )
    p.add_argument(
        "--bp-high-hz",
        type=float,
        default=DEFAULT_BP_HIGH_HZ,
        help=f"Bandpass high cutoff for the 1 kHz tone (Hz). Default: {DEFAULT_BP_HIGH_HZ:g}.",
    )
    p.add_argument(
        "--bp-transition-hz",
        type=float,
        default=DEFAULT_BP_TRANSITION_HZ,
        help=f"Transition width for the tone bandpass (Hz). Default: {DEFAULT_BP_TRANSITION_HZ:g}.",
    )
    p.add_argument(
        "--tone-hz",
        type=float,
        default=DEFAULT_TONE_HZ,
        help=f"Tick tone frequency (Hz). Default: {DEFAULT_TONE_HZ:g}.",
    )
    p.add_argument(
        "--tone-cycles",
        type=int,
        default=DEFAULT_TONE_CYCLES,
        help=f"Cycles per tick. Default: {DEFAULT_TONE_CYCLES}.",
    )
    p.add_argument(
        "--sigma-threshold",
        type=float,
        default=DEFAULT_SIGMA_THRESHOLD,
        help=f"Peak threshold = sigma_threshold * robust_sigma. Default: {DEFAULT_SIGMA_THRESHOLD:g}.",
    )
    p.add_argument(
        "--carrier-lp-hz",
        type=float,
        default=DEFAULT_CARRIER_LP_HZ,
        help=f"Lowpass cutoff for carrier Doppler estimate (Hz). Default: {DEFAULT_CARRIER_LP_HZ:g}.",
    )
    p.add_argument(
        "--start-seconds",
        type=float,
        default=DEFAULT_START_SECONDS,
        help=f"Trim this many seconds from the start of the ephemeris-selected window. Default: {DEFAULT_START_SECONDS:g}.",
    )
    p.add_argument(
        "--end-seconds",
        type=float,
        default=DEFAULT_END_SECONDS,
        help=f"Trim this many seconds from the end of the ephemeris-selected window. Default: {DEFAULT_END_SECONDS:g}.",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Process only this many seconds from the ephemeris-selected window. Default: to the gated end.",
    )
    p.add_argument(
        "--time-offset-seconds",
        type=float,
        default=0.0,
        help="Optional constant offset applied to reported UTC times. Default: 0.",
    )
    p.add_argument(
        "--gate-margin-km",
        type=float,
        default=DEFAULT_GATE_MARGIN_KM,
        help=f"Keep the contiguous interval where the ISS range is within this many km of the minimum. Default: {DEFAULT_GATE_MARGIN_KM:g}.",
    )
    p.add_argument(
        "--gate-pad-seconds",
        type=float,
        default=DEFAULT_GATE_PAD_SECONDS,
        help=f"Pad the ephemeris-selected window on both sides by this many seconds. Default: {DEFAULT_GATE_PAD_SECONDS:g}.",
    )
    p.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Output CSV path. Default: wwv_tick_times_<channel>_iss_ephem.csv in the current directory.",
    )
    p.add_argument(
        "--range-plot-file",
        type=Path,
        default=None,
        help="Range-time plot path. Default: wwv_range_time_<channel>_iss_ephem.png in the current directory.",
    )
    p.add_argument(
        "--gate-plot-file",
        type=Path,
        default=DEFAULT_EPH_PLOT,
        help=f"Plot of the ISS ephemeris gate. Default: {DEFAULT_EPH_PLOT}.",
    )
    p.add_argument(
        "--range-min-km",
        type=float,
        default=DEFAULT_RANGE_MIN_KM,
        help=f"Min virtual range to plot (km). Default: {DEFAULT_RANGE_MIN_KM:g}.",
    )
    p.add_argument(
        "--range-max-km",
        type=float,
        default=DEFAULT_RANGE_MAX_KM,
        help=f"Max virtual range to plot (km). Default: {DEFAULT_RANGE_MAX_KM:g}.",
    )
    p.add_argument(
        "--range-offset-km",
        type=float,
        default=None,
        help="Constant offset added to the predicted range curve. Default: auto-fit from the 10 detections nearest closest approach.",
    )
    p.add_argument(
        "--no-range-plot",
        action="store_true",
        help="Skip range-time-intensity plotting. Default: False (plot enabled).",
    )
    return p.parse_args()


def epoch_to_datetime(epoch_str: str) -> datetime:
    if epoch_str.endswith("Z"):
        epoch_str = epoch_str.replace("Z", "+00:00")
    return datetime.fromisoformat(epoch_str).astimezone(timezone.utc)


def datetime_to_unix_seconds(dt: datetime) -> float:
    return dt.timestamp()


def _odd_len(value: float) -> int:
    taps = int(math.ceil(value))
    if taps % 2 == 0:
        taps += 1
    return max(taps, 3)


def _hamming_taps_for_transition(fs: float, transition_hz: float) -> int:
    # Hamming rule-of-thumb: transition width ~= 3.3 * fs / N.
    if transition_hz <= 0:
        raise ValueError("transition_hz must be positive")
    return _odd_len(3.3 * fs / transition_hz)


def robust_sigma(x: np.ndarray) -> float:
    return float(np.median(np.abs(x)) / 0.6745 + 1e-12)


def estimate_freq_hz(x: np.ndarray, fs: float) -> Optional[float]:
    if x.size < 4:
        return None
    analytic = signal.hilbert(x)
    phase = np.unwrap(np.angle(analytic))
    t = np.arange(x.size, dtype=np.float64) / fs
    slope, _ = np.polyfit(t, phase, 1)
    return float(slope / (2.0 * math.pi))


@dataclass
class TickHit:
    score: float
    sample_chan: int
    time_utc: datetime
    freq_hz: Optional[float]
    range_km: Optional[float]


def make_templates(fs: float, tone_hz: float, cycles: int) -> Tuple[np.ndarray, np.ndarray]:
    samples = int(round(cycles * fs / tone_hz))
    t = np.arange(samples, dtype=np.float64) / fs
    window = signal.windows.hann(samples)
    tone_sin = np.sin(2.0 * math.pi * tone_hz * t) * window
    tone_cos = np.cos(2.0 * math.pi * tone_hz * t) * window

    def _norm(x: np.ndarray) -> np.ndarray:
        x = x - np.mean(x)
        denom = float(np.sqrt(np.sum(x**2)))
        if denom > 0:
            x = x / denom
        return x.astype(np.float32)

    return _norm(tone_sin), _norm(tone_cos)


def iter_blocks(
    reader,
    channel: str,
    start: int,
    end: int,
    block_samples: int,
) -> Iterable[Tuple[int, np.ndarray]]:
    cursor = int(start)
    end = int(end)
    block_samples = int(block_samples)
    while cursor <= end:
        count = int(min(block_samples, end - cursor + 1))
        if count < 2:
            break
        try:
            data = reader.read_vector_1d(int(cursor), int(count), channel)
        except OSError:
            data = np.zeros(count, dtype=np.complex64)
        if data is None:
            data = np.zeros(count, dtype=np.complex64)
        yield cursor, data.astype(np.complex64, copy=False)
        cursor += count


def load_iss_ephemeris_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    times: list[float] = []
    positions: list[list[float]] = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc)
                pos = [
                    float(row["j2000_p_x"]),
                    float(row["j2000_p_y"]),
                    float(row["j2000_p_z"]),
                ]
            except (KeyError, ValueError) as exc:
                raise RuntimeError(f"Malformed ephemeris row in {path}: {exc}") from exc
            times.append(datetime_to_unix_seconds(ts))
            positions.append(pos)

    if not times:
        raise RuntimeError(f"No ephemeris rows found in {path}")
    return np.asarray(times, dtype=np.float64), np.asarray(positions, dtype=np.float64)


def j2000_to_ecef_m(r_j2000_m: np.ndarray, unix_time_s: float) -> np.ndarray:
    jd = unix_time_s / 86400.0 + 2440587.5
    theta = gmst_from_jd(jd)
    c = math.cos(theta)
    s = math.sin(theta)
    r_m = np.asarray(r_j2000_m, dtype=np.float64)
    return np.array(
        [
            c * r_m[0] + s * r_m[1],
            -s * r_m[0] + c * r_m[1],
            r_m[2],
        ],
        dtype=np.float64,
    )


def teme_position_km_at_unix(sat, unix_time_s: float) -> np.ndarray:
    jd = unix_time_s / 86400.0 + 2440587.5
    jd0 = math.floor(jd)
    fr = jd - jd0
    err, r_km, _v_km_s = sat.sgp4(jd0, fr)
    if err != 0:
        raise RuntimeError(f"SGP4 propagation failed with code {err} at unix time {unix_time_s}.")
    return np.asarray(r_km, dtype=np.float64)


def generate_ancillary_csv_from_tle(
    output_path: Path,
    tle_file: Path,
    start_utc: datetime,
    end_utc: datetime,
    step_seconds: float,
) -> Path:
    if step_seconds <= 0:
        raise ValueError("ephemeris-step-seconds must be positive")

    sat = load_tle(tle_file)
    start_unix = datetime_to_unix_seconds(start_utc)
    end_unix = datetime_to_unix_seconds(end_utc)
    if end_unix < start_unix:
        raise ValueError("Ephemeris end precedes start.")

    times = np.arange(start_unix, end_unix + 0.5 * step_seconds, step_seconds, dtype=np.float64)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "j2000_p_x", "j2000_p_y", "j2000_p_z"])
        for ts in times:
            pos_m = teme_position_km_at_unix(sat, float(ts)) * 1000.0
            stamp = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
            writer.writerow([stamp, f"{pos_m[0]:.6f}", f"{pos_m[1]:.6f}", f"{pos_m[2]:.6f}"])

    return output_path


def compute_iss_range_profile(
    ephem_times_s: np.ndarray,
    ephem_positions_m: np.ndarray,
    tx_ecef_m: np.ndarray,
) -> np.ndarray:
    ranges_km = np.empty(ephem_times_s.size, dtype=np.float64)
    for i, (ts, pos_m) in enumerate(zip(ephem_times_s, ephem_positions_m)):
        iss_ecef_m = j2000_to_ecef_m(pos_m, float(ts))
        ranges_km[i] = float(np.linalg.norm(iss_ecef_m - tx_ecef_m) / 1000.0)
    return ranges_km


def select_gate_window(
    ephem_times_s: np.ndarray,
    ranges_km: np.ndarray,
    margin_km: float,
    pad_seconds: float,
) -> tuple[float, float, float, float]:
    if ephem_times_s.size == 0 or ranges_km.size == 0:
        raise RuntimeError("Empty ephemeris range profile.")
    if ephem_times_s.shape != ranges_km.shape:
        raise RuntimeError("Ephemeris time and range arrays must have the same shape.")

    min_idx = int(np.argmin(ranges_km))
    min_range_km = float(ranges_km[min_idx])
    threshold_km = min_range_km + float(margin_km)
    keep = ranges_km <= threshold_km

    left = min_idx
    while left > 0 and keep[left - 1]:
        left -= 1

    right = min_idx
    while right + 1 < keep.size and keep[right + 1]:
        right += 1

    gate_start_s = float(ephem_times_s[left] - pad_seconds)
    gate_end_s = float(ephem_times_s[right] + pad_seconds)
    gate_center_s = float(ephem_times_s[min_idx])
    return gate_start_s, gate_end_s, gate_center_s, min_range_km


def fit_range_offset_from_nearby_hits(
    hits: List[TickHit],
    gate_center_s: float,
    sat,
    tx_ecef_m: np.ndarray,
    carrier_hz: float,
    max_hits: int = 10,
) -> tuple[float, int]:
    valid_hits = [hit for hit in hits if hit.range_km is not None]
    if not valid_hits:
        return 0.0, 0

    selected_hits = sorted(
        valid_hits,
        key=lambda hit: abs(datetime_to_unix_seconds(hit.time_utc) - gate_center_s),
    )[:max_hits]
    hit_unix = np.array([datetime_to_unix_seconds(hit.time_utc) for hit in selected_hits], dtype=np.float64)
    pred_delay_s, _ = predict_delay_doppler(sat, hit_unix, tx_ecef_m, carrier_hz)
    pred_range_km = pred_delay_s * base.C_KM_PER_S
    obs_range_km = np.array([hit.range_km for hit in selected_hits], dtype=np.float64)
    return base.fit_constant_offset(obs_range_km, pred_range_km), len(selected_hits)


def plot_ephemeris_gate(
    path: Path,
    ephem_times_s: np.ndarray,
    ranges_km: np.ndarray,
    gate_start_s: float,
    gate_end_s: float,
    gate_center_s: float,
    gate_margin_km: float,
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
    ax.set_title("ISS ephemeris gate toward WWV Fort Collins")
    ax.set_xlabel("UTC time")
    ax.set_ylabel("Slant range to WWV transmitter (km)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print(f"Wrote {path}")
    return path


def main() -> None:
    args = parse_args()
    input_root = args.dataset_root.expanduser()
    ephemeris_file = args.ephemeris_file.expanduser() if args.ephemeris_file is not None else input_root / "Ancillary.csv"
    tle_file = args.tle_file.expanduser() if args.tle_file is not None else None

    reader, channel, reader_mode = open_drf_like_reader(input_root, args.channel)
    if reader_mode != "digital_rf":
        print(f"Using flat Data/rf@*.h5 reader for channel {channel} under {input_root}")

    props = reader.get_properties(channel)
    fs_in = float(props["samples_per_second"])
    raw_center = float(props["center_frequency_hz"]) if args.raw_center_hz is None else float(args.raw_center_hz)
    target_hz = raw_center if args.target_hz is None else float(args.target_hz)
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
    elif tle_file is not None:
        print(f"Using existing ephemeris CSV {ephemeris_file}; --tle-file will be used for predicted overlays.")

    ephem_times_s, ephem_positions_m = load_iss_ephemeris_csv(ephemeris_file)
    wwv_ecef_m = geodetic_to_ecef(WWV_TX_LAT_DEG, WWV_TX_LON_DEG, WWV_TX_ALT_M)
    range_km = compute_iss_range_profile(ephem_times_s, ephem_positions_m, wwv_ecef_m)
    sat = load_tle(tle_file) if tle_file is not None else None

    in_recording = (ephem_times_s >= recording_start_unix) & (ephem_times_s <= recording_end_unix)
    if not np.any(in_recording):
        raise RuntimeError(
            "No ephemeris samples overlap the recording span. Check the dataset epoch, ephemeris file, and channel bounds."
        )

    ephem_times_s = ephem_times_s[in_recording]
    range_km = range_km[in_recording]

    gate_start_s, gate_end_s, gate_center_s, min_range_km = select_gate_window(
        ephem_times_s,
        range_km,
        margin_km=float(args.gate_margin_km),
        pad_seconds=float(args.gate_pad_seconds),
    )

    gate_start_s = max(gate_start_s, recording_start_unix)
    gate_end_s = min(gate_end_s, recording_end_unix)
    if gate_start_s >= gate_end_s:
        raise RuntimeError("Ephemeris gate collapsed after clipping to the recording span.")

    if args.start_seconds > 0:
        gate_start_s += float(args.start_seconds)
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

    if args.output_csv is None:
        args.output_csv = Path(f"wwv_tick_times_{channel}_iss_ephem.csv")
    if args.range_plot_file is None:
        args.range_plot_file = Path(f"wwv_range_time_{channel}_iss_ephem.png")

    print(f"Dataset root: {input_root}")
    print(f"Channel: {channel} (reader mode: {reader_mode})")
    print(f"Ephemeris file: {ephemeris_file}")
    print(f"Raw center frequency: {raw_center:.3f} Hz")
    print(f"Target frequency: {target_hz:.3f} Hz")
    print(
        f"Recording span: {recording_start_utc.isoformat()} to {recording_end_utc.isoformat()} "
        f"({(stop_sample - start_sample + 1) / fs_in:.1f} s)"
    )
    print(
        f"Ephemeris gate center: {datetime.fromtimestamp(gate_center_s, tz=timezone.utc).isoformat()}, "
        f"min range {min_range_km:.1f} km"
    )
    print(f"Selected analysis window: {gate_start_utc.isoformat()} to {gate_end_utc.isoformat()}")
    print(f"Selected sample span: {gate_start_sample} to {gate_end_sample}")

    plot_ephemeris_gate(
        args.gate_plot_file,
        ephem_times_s,
        range_km,
        gate_start_s,
        gate_end_s,
        gate_center_s,
        float(args.gate_margin_km),
    )

    block_samples = int(round(args.block_seconds * fs_in))
    if block_samples < 1:
        raise ValueError("block_seconds too small for the input rate.")

    total_samples = gate_end_sample - gate_start_sample + 1
    total_seconds = total_samples / fs_in
    total_blocks = int(math.ceil(total_samples / block_samples))
    start_wall = time.monotonic()
    print(f"Processing {total_seconds:.1f} s in {total_blocks} blocks from {input_root}.", flush=True)

    desired_channel_rate = fs_in if args.channel_rate is None else min(float(args.channel_rate), fs_in)
    decim = int(round(fs_in / desired_channel_rate))
    if decim < 1:
        decim = 1
    channel_rate = fs_in / decim
    if decim > 1 and abs(channel_rate - desired_channel_rate) > 1e-3:
        raise ValueError(f"Cannot reach channel_rate={args.channel_rate} from fs_in={fs_in}.")

    decim1 = 50 if decim % 50 == 0 else 1
    decim2 = decim // decim1
    if decim2 < 1:
        raise ValueError("Invalid decimation stages.")

    stage1_rate = fs_in / decim1
    channel_taps = signal.firwin(
        _hamming_taps_for_transition(stage1_rate, args.channel_transition_hz),
        args.channel_lp_hz,
        fs=stage1_rate,
        window="hamming",
    )
    channel_zi = np.zeros(len(channel_taps) - 1, dtype=np.complex64)

    carrier_sos = signal.butter(4, args.carrier_lp_hz, btype="low", fs=channel_rate, output="sos")
    carrier_zi: Optional[np.ndarray] = None

    bp_taps = signal.firwin(
        _hamming_taps_for_transition(channel_rate, args.bp_transition_hz),
        [args.bp_low_hz, args.bp_high_hz],
        pass_zero=False,
        fs=channel_rate,
        window="hamming",
    )
    bp_zi = np.zeros(len(bp_taps) - 1, dtype=np.float32)
    bp_delay = (len(bp_taps) - 1) // 2

    tpl_sin, tpl_cos = make_templates(channel_rate, args.tone_hz, args.tone_cycles)
    tpl_len = tpl_sin.shape[0]
    overlap = tpl_len - 1
    prev_tail = np.zeros(overlap, dtype=np.float32)

    mix_hz = raw_center - target_hz
    phase_step = -2.0 * math.pi * mix_hz / fs_in
    phase = 0.0

    chan_cursor = 0
    hits: List[TickHit] = []
    range_rows_raw: List[np.ndarray] = []
    range_row_times: List[datetime] = []
    doppler_times: List[datetime] = []
    doppler_values: List[float] = []
    doppler_yerr: List[float] = []

    blocks_done = 0
    for cursor, block in iter_blocks(reader, channel, gate_start_sample, gate_end_sample, block_samples):
        block_count = block.size
        if block.size == 0:
            continue
        if block.size < block_samples:
            pad = np.zeros(block_samples - block.size, dtype=np.complex64)
            block = np.concatenate([block, pad])

        block *= np.float32(1.0 / 32768.0)

        if mix_hz != 0.0:
            n = np.arange(block.shape[0], dtype=np.float64)
            block *= np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
            phase = (phase + phase_step * block.shape[0]) % (2.0 * math.pi)

        stage1 = signal.resample_poly(block, 1, decim1).astype(np.complex64, copy=False)
        stage1, channel_zi = signal.lfilter(channel_taps, [1.0], stage1, zi=channel_zi)
        stage2 = signal.resample_poly(stage1, 1, decim2).astype(np.complex64, copy=False)

        if carrier_zi is None:
            carrier_zi = signal.sosfilt_zi(carrier_sos) * stage2[0]
        carrier_filt, carrier_zi = signal.sosfilt(carrier_sos, stage2, zi=carrier_zi)
        env = np.abs(stage2).astype(np.float32, copy=False)
        env_bp, bp_zi = signal.lfilter(bp_taps, [1.0], env, zi=bp_zi)

        corr_sin = signal.correlate(env_bp, tpl_sin, mode="valid")
        corr_cos = signal.correlate(env_bp, tpl_cos, mode="valid")
        corr_block = np.sqrt(corr_sin**2 + corr_cos**2)
        if bp_delay > 0 and corr_block.size > bp_delay:
            corr_block = corr_block[bp_delay:]
        range_rows_raw.append(corr_block.astype(np.float32, copy=False))
        block_time = gate_start_utc + timedelta(seconds=(cursor - gate_start_sample) / fs_in)
        range_row_times.append(block_time)

        search = np.concatenate([prev_tail, env_bp])
        corr_sin = signal.correlate(search, tpl_sin, mode="valid")
        corr_cos = signal.correlate(search, tpl_cos, mode="valid")
        corr_mag = np.sqrt(corr_sin**2 + corr_cos**2)
        corr_centered = corr_mag - np.median(corr_mag)
        sigma = robust_sigma(corr_centered)
        block_peak_sigma = float(np.max(corr_centered) / sigma) if corr_centered.size else 0.0
        thresh = args.sigma_threshold * sigma
        above = corr_centered >= thresh
        if above.size:
            prev = np.concatenate(([False], above[:-1]))
            starts = np.flatnonzero(above & ~prev)
            nextv = np.concatenate((above[1:], [False]))
            stops = np.flatnonzero(above & ~nextv)
        else:
            starts = np.array([], dtype=int)
            stops = np.array([], dtype=int)

        for s, e in zip(starts, stops):
            if s < prev_tail.size:
                continue
            seg = corr_centered[s : e + 1]
            if seg.size == 0:
                continue
            p = s + int(np.argmax(seg))
            sample_chan = chan_cursor - prev_tail.size + p
            leading_sample = sample_chan - bp_delay
            if leading_sample < 0:
                continue
            lag_in_block = p - prev_tail.size
            lag_index = lag_in_block - bp_delay
            range_km = (lag_index / channel_rate) * base.C_KM_PER_S if lag_index >= 0 else None

            seg_start = int(p)
            seg_stop = seg_start + tpl_len
            if seg_stop <= search.size:
                tone_seg = search[seg_start:seg_stop]
                freq_hz = estimate_freq_hz(tone_seg, channel_rate)
            else:
                freq_hz = None

            tick_time = gate_start_utc + timedelta(seconds=leading_sample / channel_rate)
            hits.append(
                TickHit(
                    score=float(corr_centered[p]),
                    sample_chan=leading_sample,
                    time_utc=tick_time,
                    freq_hz=freq_hz,
                    range_km=range_km,
                )
            )

        if carrier_filt.size > 1:
            phasor = np.conj(carrier_filt[:-1]) * carrier_filt[1:]
            phasor_sum = np.sum(phasor)
            if np.abs(phasor_sum) > 0:
                doppler = float(np.angle(phasor_sum) * channel_rate / (2.0 * math.pi))
                phasor_mag = np.abs(phasor)
                unit_phasor = phasor / (phasor_mag + 1e-12)
                coherence = float(np.abs(np.mean(unit_phasor)))
                coherence = max(0.0, min(1.0, coherence))
                if coherence > 0.0:
                    circ_std_rad = math.sqrt(max(-2.0 * math.log(max(coherence, 1e-12)), 0.0))
                    doppler_sigma_hz = circ_std_rad * channel_rate / (2.0 * math.pi * math.sqrt(max(unit_phasor.size, 1)))
                else:
                    doppler_sigma_hz = float("nan")
                mid_time = gate_start_utc + timedelta(seconds=(cursor - gate_start_sample + (block_count / 2.0)) / fs_in)
                doppler_times.append(mid_time)
                doppler_values.append(doppler)
                doppler_yerr.append(doppler_sigma_hz)

        prev_tail = search[-overlap:] if overlap > 0 else np.zeros(0, dtype=np.float32)
        chan_cursor += env_bp.size

        blocks_done += 1
        processed_samples = (cursor - gate_start_sample) + block_count
        processed_samples = min(processed_samples, total_samples)
        processed_seconds = processed_samples / fs_in
        pct = 100.0 * processed_samples / total_samples
        elapsed = time.monotonic() - start_wall
        print(
            (
                f"Processed {processed_seconds:.1f}/{total_seconds:.1f} s "
                f"({pct:.1f}%), {blocks_done}/{total_blocks} blocks, "
                f"elapsed {elapsed:.1f} s."
            ),
            flush=True,
        )

    if not hits:
        print("No ticks detected.")
        return

    doppler_csv = args.output_csv.with_name(f"wwv_doppler_{channel}_iss_ephem.csv") if args.output_csv is not None else Path(f"wwv_doppler_{channel}_iss_ephem.csv")
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["utc_time", "sample_index", "freq_hz", "range_km", "score"])
        for hit in hits:
            writer.writerow(
                [
                    hit.time_utc.isoformat(),
                    hit.sample_chan,
                    "" if hit.freq_hz is None else f"{hit.freq_hz:.3f}",
                    "" if hit.range_km is None else f"{hit.range_km:.3f}",
                    f"{hit.score:.3f}",
                ]
            )

    print(f"Wrote {args.output_csv} ({len(hits)} ticks)")
    if doppler_times and doppler_values:
        with doppler_csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["utc_time", "doppler_hz", "doppler_sigma_hz"])
            for t, d, s in zip(doppler_times, doppler_values, doppler_yerr):
                writer.writerow(
                    [
                        t.isoformat(),
                        "" if not np.isfinite(d) else f"{d:.3f}",
                        "" if not np.isfinite(s) else f"{s:.3f}",
                    ]
                )
        print(f"Wrote {doppler_csv} ({len(doppler_values)} doppler estimates)")

    predicted_range_times: Optional[List[datetime]] = None
    predicted_range_km: Optional[np.ndarray] = None
    predicted_doppler_times: Optional[List[datetime]] = None
    predicted_doppler_hz: Optional[np.ndarray] = None
    range_offset_km = 0.0
    if sat is not None and doppler_times:
        doppler_unix = np.array([datetime_to_unix_seconds(t) for t in doppler_times], dtype=np.float64)
        _, predicted_doppler_hz = predict_delay_doppler(sat, doppler_unix, wwv_ecef_m, target_hz)
        predicted_doppler_times = doppler_times
    if sat is not None and range_row_times:
        if args.range_offset_km is None:
            range_offset_km, used_hits = fit_range_offset_from_nearby_hits(
                hits,
                gate_center_s,
                sat,
                wwv_ecef_m,
                target_hz,
            )
            if used_hits > 0:
                print(f"Auto-fit range offset from {used_hits} detections nearest closest approach: {range_offset_km:+.3f} km")
            else:
                print("Auto-fit range offset skipped (no range detections available); using 0.000 km.")
        else:
            range_offset_km = float(args.range_offset_km)
            print(f"Using manual range offset: {range_offset_km:+.3f} km")
        range_row_unix = np.array([datetime_to_unix_seconds(t) for t in range_row_times], dtype=np.float64)
        pred_delay_s, _ = predict_delay_doppler(sat, range_row_unix, wwv_ecef_m, target_hz)
        predicted_range_times = range_row_times
        predicted_range_km = pred_delay_s * base.C_KM_PER_S

    if not args.no_range_plot and range_rows_raw:
        global_sigma = robust_sigma(np.concatenate(range_rows_raw))
        range_rows = [row / (global_sigma + 1e-12) for row in range_rows_raw]
        base.plot_range_time(
            range_rows,
            range_row_times,
            channel_rate,
            args.range_plot_file,
            args.range_min_km,
            args.range_max_km,
            hits,
            doppler_times,
            doppler_values,
            None,
            predicted_range_times=predicted_range_times,
            predicted_range_km=predicted_range_km,
            predicted_doppler_times=predicted_doppler_times,
            predicted_doppler_hz=predicted_doppler_hz,
            range_offset_km=range_offset_km,
        )


if __name__ == "__main__":
    main()
