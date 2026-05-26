#!/usr/bin/env python3
"""
Detect likely meteor-radar transmitters in a DigitalRF recording.

The detector:
1) reads the receiver metadata to infer the operating band;
2) filters a transmitter catalog to the receivers' band;
3) uses an ISS TLE to predict closest approach for each candidate radar;
4) keeps only radars whose closest point of approach is within a threshold;
5) extracts a short window around closest approach;
6) mixes, decimates, and matched-filters the window with an appropriate code.

The transmitter catalog is a CSV file with a `kind` column:
- `monostatic`: Barker/monopulse-style pulsed radars.
- `simone`: SIMONe coded transmitters using the provided seed list.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from scipy import signal

from drf_compat import open_drf_like_reader
from stack_superdarn_iss_ephem import geodetic_to_ecef, load_decimated_channel, load_tle, predict_delay_doppler

os.environ.setdefault("MPLBACKEND", "Agg")

DEFAULT_INPUT_ROOT = Path("/Users/chartat1/data/hf_data/itsi/iss/GMT132/M30023A")
DEFAULT_TRANSMITTERS_FILE = Path(__file__).with_name("meteor_radar_transmitters.csv")
DEFAULT_OUTPUT_PREFIX = Path("meteor_radar_detection")
DEFAULT_CPA_THRESHOLD_KM = 20_000.0
DEFAULT_EPH_STEP_SECONDS = 1.0
DEFAULT_ANALYSIS_SECONDS = 20.0
DEFAULT_RECENTER_SECONDS = 0.0
DEFAULT_DECIMATED_RATE = 100_000.0
DEFAULT_CHANNEL_LP_HZ = 45_000.0
DEFAULT_LAG_SEARCH_MS = 25.0
DEFAULT_RECEIVER_BAND_MARGIN_HZ = 0.0

C_KM_PER_S = 299_792.458
BARKER_7 = np.array([1, 1, 1, -1, -1, 1, -1], dtype=np.float32)


@dataclass
class Transmitter:
    kind: str
    network: str
    site: str
    system: str
    lat_deg: float
    lon_deg: float
    height_m: float
    freq_mhz: float
    code: str
    prf_hz: Optional[float]
    chip_rate_hz: Optional[float]
    code_repetition_chips: Optional[int]
    cw_seeds: list[int]

    @property
    def freq_hz(self) -> float:
        return float(self.freq_mhz) * 1e6

    @property
    def label(self) -> str:
        return f"{self.network}/{self.site} ({self.system})"


@dataclass
class CandidateResult:
    transmitter: Transmitter
    min_range_km: float
    cpa_time_utc: datetime
    gate_start_utc: datetime
    gate_end_utc: datetime
    gate_center_utc: datetime
    delay_ms: float
    doppler_hz: float
    best_score: float
    best_lag_samples: int
    best_template: str
    template_samples: int
    receiver_band_ok: bool


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect likely meteor-radar transmitters in a DigitalRF recording.")
    p.add_argument("--dataset-root", type=Path, default=DEFAULT_INPUT_ROOT, help=f"DigitalRF dataset root. Default: {DEFAULT_INPUT_ROOT}.")
    p.add_argument("--channel", default=None, help="Channel name. Default: auto-select the first channel.")
    p.add_argument("--tle-file", type=Path, required=True, help="ISS TLE file used for the range/Doppler prediction.")
    p.add_argument(
        "--transmitters-file",
        type=Path,
        default=DEFAULT_TRANSMITTERS_FILE,
        help=f"Transmitter catalog CSV. Default: {DEFAULT_TRANSMITTERS_FILE}.",
    )
    p.add_argument(
        "--output-prefix",
        type=Path,
        default=DEFAULT_OUTPUT_PREFIX,
        help=f"Output prefix for CSV/JSON. Default: {DEFAULT_OUTPUT_PREFIX}.",
    )
    p.add_argument(
        "--cpa-threshold-km",
        type=float,
        default=DEFAULT_CPA_THRESHOLD_KM,
        help=f"Keep only transmitters whose closest approach is within this many km. Default: {DEFAULT_CPA_THRESHOLD_KM:g}.",
    )
    p.add_argument(
        "--ephemeris-step-seconds",
        type=float,
        default=DEFAULT_EPH_STEP_SECONDS,
        help=f"Cadence used to sample the TLE prediction. Default: {DEFAULT_EPH_STEP_SECONDS:g}.",
    )
    p.add_argument(
        "--analysis-seconds",
        type=float,
        default=DEFAULT_ANALYSIS_SECONDS,
        help=f"Analyze this many seconds around closest approach. Default: {DEFAULT_ANALYSIS_SECONDS:g}.",
    )
    p.add_argument(
        "--recentre-seconds",
        type=float,
        default=DEFAULT_RECENTER_SECONDS,
        help=f"Shift the analysis window by this many seconds relative to closest approach. Default: 0.",
    )
    p.add_argument(
        "--decimated-rate",
        type=float,
        default=DEFAULT_DECIMATED_RATE,
        help=f"Working sample rate after decimation. Default: {DEFAULT_DECIMATED_RATE:g}.",
    )
    p.add_argument(
        "--channel-lp-hz",
        type=float,
        default=DEFAULT_CHANNEL_LP_HZ,
        help=f"Lowpass cutoff before decimation. Default: {DEFAULT_CHANNEL_LP_HZ:g}.",
    )
    p.add_argument(
        "--receiver-band-margin-hz",
        type=float,
        default=DEFAULT_RECEIVER_BAND_MARGIN_HZ,
        help="Extra margin added to the inferred receiver band edges before filtering transmitters.",
    )
    p.add_argument(
        "--lag-search-ms",
        type=float,
        default=DEFAULT_LAG_SEARCH_MS,
        help=f"Search this many ms around the predicted delay. Default: {DEFAULT_LAG_SEARCH_MS:g}.",
    )
    p.add_argument(
        "--center-hz",
        type=float,
        default=None,
        help="Override the DigitalRF center frequency in Hz. Default: metadata.",
    )
    p.add_argument(
        "--target-hz",
        type=float,
        default=None,
        help="Override the nominal receiver tuning frequency in Hz. Default: the transmitter frequency for each candidate.",
    )
    p.add_argument(
        "--skip-seconds",
        type=float,
        default=0.0,
        help="Skip this many seconds from the start of the recording. Default: 0.",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Analyze only this many seconds from the recording after skipping. Default: to the end.",
    )
    return p.parse_args()


def datetime_to_unix_seconds(dt: datetime) -> float:
    return dt.timestamp()


def epoch_to_datetime(epoch_str: str) -> datetime:
    if epoch_str.endswith("Z"):
        epoch_str = epoch_str.replace("Z", "+00:00")
    return datetime.fromisoformat(epoch_str).astimezone(timezone.utc)


def parse_int_list(text: str) -> list[int]:
    text = text.strip()
    if not text:
        return []
    text = text.strip("[]")
    parts = re.split(r"[|,;\s]+", text)
    return [int(p) for p in parts if p]


def load_transmitters(path: Path) -> list[Transmitter]:
    rows: list[Transmitter] = []
    with path.open(newline="") as f:
        filtered_lines = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(filtered_lines)
    for row in reader:
        try:
            rows.append(
                Transmitter(
                    kind=row["kind"].strip().lower(),
                    network=row["network"].strip(),
                    site=row["site"].strip(),
                    system=row["system"].strip(),
                    lat_deg=float(row["lat_deg"]),
                    lon_deg=float(row["lon_deg"]),
                    height_m=float(row["height_m"]),
                    freq_mhz=float(row["freq_mhz"]),
                    code=row.get("code", "").strip(),
                    prf_hz=float(row["prf_hz"]) if row.get("prf_hz", "").strip() else None,
                    chip_rate_hz=float(row["chip_rate_hz"]) if row.get("chip_rate_hz", "").strip() else None,
                    code_repetition_chips=int(row["code_repetition_chips"]) if row.get("code_repetition_chips", "").strip() else None,
                    cw_seeds=parse_int_list(row.get("cw_seeds", "")),
                )
            )
        except Exception as exc:
            raise RuntimeError(f"Malformed transmitter row in {path}: {row}") from exc
    if not rows:
        raise RuntimeError(f"No transmitters found in {path}")
    return rows


def make_barker_template(prf_hz: float, fs_out: float) -> tuple[np.ndarray, int]:
    chip_samples = max(1, int(round(fs_out / prf_hz)))
    tpl = np.repeat(BARKER_7, chip_samples).astype(np.float32)
    return tpl, chip_samples


def make_monopulse_template(prf_hz: Optional[float], fs_out: float) -> tuple[np.ndarray, int]:
    if prf_hz is None or prf_hz <= 0:
        return np.ones(1, dtype=np.float32), 1
    chip_samples = max(1, int(round(fs_out / prf_hz)))
    tpl = np.ones(chip_samples, dtype=np.float32)
    return tpl, chip_samples


def create_codes(codelen: int, seeds: list[int]) -> np.ndarray:
    codes = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        phases = np.sign(rng.random(codelen) * 2.0 - 1.0).astype(np.float32)
        phases[phases == 0.0] = 1.0
        codes.append(phases)
    return np.asarray(codes, dtype=np.float32)


def make_simone_templates(code_len: int, chip_rate_hz: float, fs_out: float, seeds: list[int]) -> tuple[list[np.ndarray], int]:
    chip_samples = max(1, int(round(fs_out / chip_rate_hz)))
    codes = create_codes(code_len, seeds)
    templates = [np.repeat(code, chip_samples).astype(np.float32) for code in codes]
    return templates, chip_samples


def template_energy(template: np.ndarray) -> float:
    return float(np.sum(np.abs(template) ** 2))


def compute_receiver_band(center_hz: float, fs_in: float, margin_hz: float) -> tuple[float, float]:
    half = fs_in / 2.0
    return center_hz - half - margin_hz, center_hz + half + margin_hz


def select_gate_window(
    ephem_times_s: np.ndarray,
    ranges_km: np.ndarray,
    margin_km: float,
    pad_seconds: float,
    analysis_seconds: Optional[float],
    recenter_seconds: float,
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
    gate_center_s = float(ephem_times_s[min_idx] + recenter_seconds)

    if analysis_seconds is not None and analysis_seconds > 0:
        half = analysis_seconds / 2.0
        gate_start_s = max(gate_start_s, gate_center_s - half)
        gate_end_s = min(gate_end_s, gate_center_s + half)

    return gate_start_s, gate_end_s, gate_center_s, min_range_km


def analyze_template_bank(
    signal_in: np.ndarray,
    fs_out: float,
    templates: list[tuple[str, np.ndarray]],
    pred_delay_s: float,
    lag_search_ms: float,
) -> tuple[float, int, str]:
    if signal_in.size == 0:
        return 0.0, 0, ""

    lag_half = max(1, int(round(lag_search_ms * 1e-3 * fs_out)))
    pred_lag = int(round(pred_delay_s * fs_out))
    best_score = -np.inf
    best_lag = 0
    best_name = ""

    power = np.abs(signal_in) ** 2
    for name, template in templates:
        tpl = np.asarray(template, dtype=np.complex64)
        if tpl.size == 0 or signal_in.size < tpl.size:
            continue
        corr = signal.correlate(signal_in, tpl, mode="valid", method="fft")
        tpl_energy = template_energy(tpl)
        local_energy = signal.correlate(power, np.ones(tpl.size, dtype=np.float32), mode="valid", method="fft")
        denom = np.sqrt(np.maximum(local_energy, 1e-12) * max(tpl_energy, 1e-12))
        score = np.abs(corr) / denom
        lo = max(0, pred_lag - lag_half)
        hi = min(score.size, pred_lag + lag_half + 1)
        if lo >= hi:
            lo = 0
            hi = score.size
        local = score[lo:hi]
        if local.size == 0:
            continue
        idx = int(np.argmax(local))
        candidate_score = float(local[idx])
        if candidate_score > best_score:
            best_score = candidate_score
            best_lag = int(lo + idx)
            best_name = name

    if not np.isfinite(best_score):
        return 0.0, 0, ""
    return best_score, best_lag, best_name


def transmitter_templates(tx: Transmitter, fs_out: float) -> list[tuple[str, np.ndarray]]:
    kind = tx.kind.lower()
    if kind == "simone":
        if tx.chip_rate_hz is None or tx.code_repetition_chips is None:
            raise RuntimeError(f"SIMONe transmitter {tx.label} is missing chip_rate_hz/code_repetition_chips.")
        templates, _ = make_simone_templates(tx.code_repetition_chips, tx.chip_rate_hz, fs_out, tx.cw_seeds)
        return [(f"seed={seed}", tpl) for seed, tpl in zip(tx.cw_seeds, templates)]

    code = tx.code.lower()
    if code.startswith("barker"):
        if tx.prf_hz is None:
            raise RuntimeError(f"Monostatic Barker transmitter {tx.label} is missing prf_hz.")
        tpl, _ = make_barker_template(tx.prf_hz, fs_out)
        return [(tx.code, tpl)]
    tpl, _ = make_monopulse_template(tx.prf_hz, fs_out)
    return [("monopulse", tpl)]


def label_candidate(tx: Transmitter) -> str:
    return f"{tx.network}/{tx.site} {tx.freq_mhz:.4f} MHz"


def evaluate_transmitter(
    reader,
    channel: str,
    fs_in: float,
    center_hz: float,
    target_hz: float,
    tx: Transmitter,
    sat,
    recording_start_unix: float,
    recording_end_unix: float,
    analysis_seconds: float,
    recenter_seconds: float,
    ephem_step_seconds: float,
    decimated_rate: float,
    channel_lp_hz: float,
    lag_search_ms: float,
) -> CandidateResult:
    tx_freq_hz = tx.freq_hz
    tx_ecef = geodetic_to_ecef(tx.lat_deg, tx.lon_deg, tx.height_m)
    times_s = np.arange(recording_start_unix, recording_end_unix + 0.5 * ephem_step_seconds, ephem_step_seconds, dtype=np.float64)
    delay_s, doppler_hz = predict_delay_doppler(sat, times_s, tx_ecef, tx_freq_hz)
    ranges_km = delay_s * C_KM_PER_S
    min_idx = int(np.argmin(ranges_km))
    min_range_km = float(ranges_km[min_idx])
    cpa_time_s = float(times_s[min_idx])

    gate_start_s, gate_end_s, gate_center_s, _ = select_gate_window(
        times_s,
        ranges_km,
        margin_km=1_000.0,
        pad_seconds=5.0,
        analysis_seconds=analysis_seconds,
        recenter_seconds=recenter_seconds,
    )
    gate_start_s = max(gate_start_s, recording_start_unix)
    gate_end_s = min(gate_end_s, recording_end_unix)
    if gate_end_s <= gate_start_s:
        raise RuntimeError(f"Analysis window collapsed for {tx.label}.")

    start_sample, _ = reader.get_bounds(channel)
    if start_sample is None:
        raise RuntimeError("Dataset start bound is unavailable.")
    start_sample = int(start_sample)
    gate_start_sample = int(start_sample + round((gate_start_s - recording_start_unix) * fs_in))
    gate_total_samples = int(round((gate_end_s - gate_start_s) * fs_in))
    gate_total_samples = max(gate_total_samples, 1)

    if target_hz == 0.0:
        raise ValueError("target_hz cannot be zero.")

    y = load_decimated_channel(
        reader,
        channel=channel,
        start_sample=gate_start_sample,
        total_samples=gate_total_samples,
        fs_in=fs_in,
        fs_out=decimated_rate,
        center_hz=center_hz,
        target_hz=target_hz,
        lp_hz=channel_lp_hz,
        raw_chunk_seconds=2.0,
    )
    if y.size == 0:
        raise RuntimeError(f"No decimated samples produced for {tx.label}.")

    pred_delay_s = float(delay_s[min_idx])
    pred_doppler_hz = float(doppler_hz[min_idx])
    t = np.arange(y.size, dtype=np.float64) / decimated_rate
    corrected = y * np.exp(-2j * np.pi * pred_doppler_hz * t).astype(np.complex64)

    templates = transmitter_templates(tx, decimated_rate)
    best_score, best_lag, best_template = analyze_template_bank(
        corrected,
        decimated_rate,
        templates,
        pred_delay_s=pred_delay_s,
        lag_search_ms=lag_search_ms,
    )

    if best_template == "":
        best_template = "none"

    return CandidateResult(
        transmitter=tx,
        min_range_km=min_range_km,
        cpa_time_utc=datetime.fromtimestamp(cpa_time_s, tz=timezone.utc),
        gate_start_utc=datetime.fromtimestamp(gate_start_s, tz=timezone.utc),
        gate_end_utc=datetime.fromtimestamp(gate_end_s, tz=timezone.utc),
        gate_center_utc=datetime.fromtimestamp(gate_center_s, tz=timezone.utc),
        delay_ms=pred_delay_s * 1e3,
        doppler_hz=pred_doppler_hz,
        best_score=best_score,
        best_lag_samples=best_lag,
        best_template=best_template,
        template_samples=max((tpl.size for _, tpl in templates), default=0),
        receiver_band_ok=True,
    )


def main() -> int:
    args = parse_args()
    input_root = args.dataset_root.expanduser()
    tle_file = args.tle_file.expanduser()
    transmitters_file = args.transmitters_file.expanduser()

    reader, channel, reader_mode = open_drf_like_reader(input_root, args.channel)
    if reader_mode != "digital_rf":
        print(f"Using flat Data/rf@*.h5 reader for channel {channel} under {input_root}")

    props = reader.get_properties(channel)
    fs_in = float(props["samples_per_second"])
    center_hz = float(props["center_frequency_hz"]) if args.center_hz is None else float(args.center_hz)
    target_hz_default = center_hz if args.target_hz is None else float(args.target_hz)
    start_sample, stop_sample = reader.get_bounds(channel)
    if start_sample is None or stop_sample is None:
        raise RuntimeError("Dataset bounds are unavailable.")
    start_sample = int(start_sample)
    stop_sample = int(stop_sample)

    decimated_rate = min(float(args.decimated_rate), fs_in)
    decim = int(round(fs_in / decimated_rate))
    if decim < 1:
        decim = 1
    if not math.isclose(fs_in / decim, decimated_rate, rel_tol=0.0, abs_tol=1e-6):
        decimated_rate = fs_in
        decim = 1
        print(f"Adjusted decimated-rate to {decimated_rate:g} Hz for fs_in={fs_in:g} Hz.")
    channel_lp_hz = min(float(args.channel_lp_hz), 0.45 * decimated_rate, 0.45 * fs_in)
    if channel_lp_hz != float(args.channel_lp_hz):
        print(f"Adjusted channel lowpass to {channel_lp_hz:g} Hz to stay below Nyquist.")

    epoch = epoch_to_datetime(props["epoch"])
    recording_start_utc = epoch + timedelta(seconds=start_sample / fs_in)
    recording_end_utc = epoch + timedelta(seconds=stop_sample / fs_in)
    recording_start_unix = datetime_to_unix_seconds(recording_start_utc)
    recording_end_unix = datetime_to_unix_seconds(recording_end_utc)

    sat = load_tle(tle_file)
    transmitters = load_transmitters(transmitters_file)
    band_low_hz, band_high_hz = compute_receiver_band(center_hz, fs_in, args.receiver_band_margin_hz)

    if args.seconds is not None:
        recording_end_unix = min(recording_end_unix, recording_start_unix + float(args.skip_seconds) + float(args.seconds))
    if args.skip_seconds > 0:
        recording_start_unix = min(recording_end_unix, recording_start_unix + float(args.skip_seconds))

    times_s = np.arange(recording_start_unix, recording_end_unix + 0.5 * args.ephemeris_step_seconds, args.ephemeris_step_seconds, dtype=np.float64)
    if times_s.size == 0:
        raise RuntimeError("Recording window is empty after skip/seconds filtering.")

    results: list[CandidateResult] = []
    rejected_band: list[Transmitter] = []
    rejected_cpa: list[Transmitter] = []

    print(f"Dataset root: {input_root}")
    print(f"Channel: {channel} (reader mode: {reader_mode})")
    print(f"Receiver band: {band_low_hz/1e6:.4f} to {band_high_hz/1e6:.4f} MHz")
    print(f"Transmitter catalog: {transmitters_file}")
    print(f"Recording span used: {datetime.fromtimestamp(recording_start_unix, tz=timezone.utc).isoformat()} to {datetime.fromtimestamp(recording_end_unix, tz=timezone.utc).isoformat()}")
    print(f"Analyzing candidates with CPA <= {args.cpa_threshold_km:.1f} km")

    for tx in transmitters:
        freq_hz = tx.freq_hz
        if not (band_low_hz <= freq_hz <= band_high_hz):
            rejected_band.append(tx)
            continue

        tx_ecef = geodetic_to_ecef(tx.lat_deg, tx.lon_deg, tx.height_m)
        delay_s, _doppler_hz = predict_delay_doppler(sat, times_s, tx_ecef, freq_hz)
        ranges_km = delay_s * C_KM_PER_S
        min_range_km = float(np.min(ranges_km))
        if min_range_km > args.cpa_threshold_km:
            rejected_cpa.append(tx)
            continue

        print(f"Candidate: {label_candidate(tx)} CPA {min_range_km:.1f} km")
        result = evaluate_transmitter(
            reader,
            channel=channel,
            fs_in=fs_in,
            center_hz=center_hz,
            target_hz=tx.freq_hz if args.target_hz is None else target_hz_default,
            tx=tx,
            sat=sat,
            recording_start_unix=recording_start_unix,
            recording_end_unix=recording_end_unix,
            analysis_seconds=args.analysis_seconds,
            recenter_seconds=args.recentre_seconds,
            ephem_step_seconds=args.ephemeris_step_seconds,
            decimated_rate=decimated_rate,
            channel_lp_hz=channel_lp_hz,
            lag_search_ms=args.lag_search_ms,
        )
        results.append(result)
        print(
            f"  best template={result.best_template} score={result.best_score:.4f} "
            f"lag={result.best_lag_samples} samples delay={result.delay_ms:.3f} ms doppler={result.doppler_hz:+.1f} Hz"
        )

    results_csv = args.output_prefix.with_suffix(".csv")
    results_json = args.output_prefix.with_suffix(".json")
    results_csv.parent.mkdir(parents=True, exist_ok=True)

    with results_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "kind",
                "network",
                "site",
                "system",
                "freq_mhz",
                "min_range_km",
                "cpa_time_utc",
                "gate_start_utc",
                "gate_end_utc",
                "gate_center_utc",
                "delay_ms",
                "doppler_hz",
                "best_score",
                "best_lag_samples",
                "best_template",
                "template_samples",
            ]
        )
        for r in results:
            tx = r.transmitter
            writer.writerow(
                [
                    tx.kind,
                    tx.network,
                    tx.site,
                    tx.system,
                    f"{tx.freq_mhz:.4f}",
                    f"{r.min_range_km:.3f}",
                    r.cpa_time_utc.isoformat(),
                    r.gate_start_utc.isoformat(),
                    r.gate_end_utc.isoformat(),
                    r.gate_center_utc.isoformat(),
                    f"{r.delay_ms:.3f}",
                    f"{r.doppler_hz:.3f}",
                    f"{r.best_score:.6f}",
                    r.best_lag_samples,
                    r.best_template,
                    r.template_samples,
                ]
            )

    summary = {
        "dataset_root": str(input_root),
        "channel": channel,
        "reader_mode": reader_mode,
        "tle_file": str(tle_file),
        "transmitters_file": str(transmitters_file),
        "receiver_center_hz": center_hz,
        "receiver_band_low_hz": band_low_hz,
        "receiver_band_high_hz": band_high_hz,
        "analysis_seconds": float(args.analysis_seconds),
        "ephemeris_step_seconds": float(args.ephemeris_step_seconds),
        "cpa_threshold_km": float(args.cpa_threshold_km),
        "decimated_rate_hz": float(decimated_rate),
        "channel_lp_hz": float(channel_lp_hz),
        "n_transmitters": len(transmitters),
        "n_band_candidates": len(transmitters) - len(rejected_band),
        "n_cpa_candidates": len(results),
        "results": [
            {
                "kind": r.transmitter.kind,
                "network": r.transmitter.network,
                "site": r.transmitter.site,
                "system": r.transmitter.system,
                "freq_mhz": r.transmitter.freq_mhz,
                "min_range_km": r.min_range_km,
                "cpa_time_utc": r.cpa_time_utc.isoformat(),
                "gate_start_utc": r.gate_start_utc.isoformat(),
                "gate_end_utc": r.gate_end_utc.isoformat(),
                "delay_ms": r.delay_ms,
                "doppler_hz": r.doppler_hz,
                "best_score": r.best_score,
                "best_lag_samples": r.best_lag_samples,
                "best_template": r.best_template,
                "template_samples": r.template_samples,
            }
            for r in results
        ],
    }
    results_json.write_text(json.dumps(summary, indent=2))

    print(f"Wrote {results_csv} ({len(results)} candidates)")
    print(f"Wrote {results_json}")
    print(f"Rejected by receiver band: {len(rejected_band)}")
    print(f"Rejected by CPA threshold: {len(rejected_cpa)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
