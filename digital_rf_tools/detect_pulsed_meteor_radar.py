#!/usr/bin/env python3
"""
Analyze pulsed meteor-radar returns in a DigitalRF recording.

This script is the pulsed-radar analogue of `detect_wwv_ticks.py`:
1) mix raw IQ to each candidate transmitter frequency,
2) decimate to a working rate,
3) matched-filter the decimated complex stream against the transmitter code, and
4) write the matched-filter range-time output as a plot plus a compact per-row summary CSV.

The transmitter catalog is encoded directly in this script from the supplied
table of monostatic pulsed transmitters.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from scipy import ndimage, signal

from drf_compat import open_drf_like_reader

os.environ.setdefault("MPLBACKEND", "Agg")

DEFAULT_INPUT_ROOT = Path("/Users/chartat1/data/hf_data/itsi/iss/GMT152/M10331A")
DEFAULT_OUTPUT_PREFIX = Path("pulsed_meteor_radar_detection")
DEFAULT_BLOCK_SECONDS = 1.0
DEFAULT_CHANNEL_RATE = 400_000.0
DEFAULT_CHANNEL_LP_HZ = 180_000.0
DEFAULT_CHANNEL_TRANSITION_HZ = 10_000.0
DEFAULT_SIGMA_THRESHOLD = 1.5
DEFAULT_RANGE_PLOT = Path("pulsed_meteor_radar_range_time.png")
DEFAULT_RANGE_MAX_KM = 500.0
DEFAULT_RANGE_MIN_KM = 0.0
DEFAULT_START_SECONDS = 0.0
DEFAULT_END_SECONDS = 0.0
DEFAULT_WARMUP_SECONDS = 2.0
DEFAULT_TIME_OFFSET_SECONDS = 0.0
DEFAULT_RECEIVER_BAND_MARGIN_HZ = 0.0
DEFAULT_RAW_CHUNK_SECONDS = 2.0
DEFAULT_PRI_FOLD = True
DEFAULT_ENHANCE_SURFACE = False
DEFAULT_ENHANCE_MODE = "persistent-band"
DEFAULT_ENHANCE_TIME_SIGMA = 1.0
DEFAULT_ENHANCE_RANGE_SIGMA = 1.0
DEFAULT_ENHANCE_BACKGROUND_FACTOR = 4.0
C_KM_PER_S = 299_792.458
DECIM_FIR_TAPS = 161
BARKER_7 = np.array([1, 1, 1, -1, -1, 1, -1], dtype=np.float32)


@dataclass(frozen=True)
class PulsedTransmitter:
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

    @property
    def freq_hz(self) -> float:
        return float(self.freq_mhz) * 1e6

    @property
    def label(self) -> str:
        return f"{self.network}/{self.site} ({self.system})"

    @property
    def supports_template(self) -> bool:
        return self.prf_hz is not None and self.prf_hz > 0 and bool(self.code.strip())


@dataclass
class DetectionHit:
    score: float
    sample_index: int
    lag_samples: int
    time_utc: datetime
    residual_hz: Optional[float]
    range_km: float
    template_name: str


@dataclass
class DetectionResult:
    transmitter: PulsedTransmitter
    hits: list[DetectionHit]
    corr_rows: list[np.ndarray]
    row_times: list[datetime]
    track_ranges_km: list[float]
    residual_times: list[datetime]
    residual_hz: list[float]
    template_name: str
    template_samples: int
    pri_samples: int


CATALOG: tuple[PulsedTransmitter, ...] = (
    PulsedTransmitter("METnwDEU", "Collm", "Skiymet", 51.309, 13.003, 170.0, 36.2000, "Barker-7", 625.0, 100_000.0),
    PulsedTransmitter("METnwNOR", "Alta", "ATRAD", 69.970, 23.295, 0.0, 31.0000, "", None, None),
    PulsedTransmitter("METnwNOR", "Sodankyla", "Skiymet", 67.366, 26.637, 0.0, 36.9000, "Monopulse", 2144.0, None),
    PulsedTransmitter("METnwNOR", "Tromso", "ATRAD", 69.580, 19.220, 0.0, 30.2500, "", None, None),
    PulsedTransmitter("METnwNOR", "Kiruna", "Skiymet", 67.891, 21.076, 89.4, 32.5500, "Barker-7", 625.0, 100_000.0),
    PulsedTransmitter("METnwCONDOR", "ALO", "ATRAD", -30.252, -70.738, 2520.0, 35.1500, "", None, None),
    PulsedTransmitter("None", "Bahir Dar", "Skiymet", 11.600, 37.400, 0.0, 32.5500, "Barker-7", 625.0, 100_000.0),
    PulsedTransmitter("None", "Santa Cruz", "Skiymet", 10.284, -85.595, 0.0, 36.2000, "Barker-7", 625.0, 100_000.0),
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect pulsed meteor-radar transmitters in a DigitalRF recording.")
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help=f"DigitalRF dataset root. Default: {DEFAULT_INPUT_ROOT}.",
    )
    p.add_argument("--channel", default=None, help="Channel name. Default: auto-select the first channel.")
    p.add_argument(
        "--center-hz",
        type=float,
        default=None,
        help="Override the DigitalRF center frequency in Hz. Default: metadata.",
    )
    p.add_argument(
        "--transmitter",
        default=None,
        help="Optional case-insensitive substring filter for network/site/system/code/label.",
    )
    p.add_argument(
        "--output-prefix",
        type=Path,
        default=DEFAULT_OUTPUT_PREFIX,
        help=f"Prefix for per-transmitter CSV/PNG outputs. Default: {DEFAULT_OUTPUT_PREFIX}.",
    )
    p.add_argument(
        "--block-seconds",
        type=float,
        default=DEFAULT_BLOCK_SECONDS,
        help=(
            f"Seconds of decimated data to integrate per matched-filter profile. "
            f"Default: {DEFAULT_BLOCK_SECONDS:g}."
        ),
    )
    p.add_argument(
        "--channel-rate",
        type=float,
        default=DEFAULT_CHANNEL_RATE,
        help=f"Working sample rate after decimation. Default: {DEFAULT_CHANNEL_RATE:g}.",
    )
    p.add_argument(
        "--channel-lp-hz",
        type=float,
        default=DEFAULT_CHANNEL_LP_HZ,
        help=f"Lowpass cutoff before decimation. Default: {DEFAULT_CHANNEL_LP_HZ:g}.",
    )
    p.add_argument(
        "--channel-transition-hz",
        type=float,
        default=DEFAULT_CHANNEL_TRANSITION_HZ,
        help=f"Transition width for the decimation lowpass. Default: {DEFAULT_CHANNEL_TRANSITION_HZ:g}.",
    )
    p.add_argument(
        "--sigma-threshold",
        type=float,
        default=DEFAULT_SIGMA_THRESHOLD,
        help=f"Peak threshold = sigma_threshold * robust_sigma. Default: {DEFAULT_SIGMA_THRESHOLD:g}.",
    )
    p.add_argument(
        "--start-seconds",
        type=float,
        default=DEFAULT_START_SECONDS,
        help=f"Skip this many seconds from the start. Default: {DEFAULT_START_SECONDS:g}.",
    )
    p.add_argument(
        "--end-seconds",
        type=float,
        default=DEFAULT_END_SECONDS,
        help=f"Skip this many seconds from the end. Default: {DEFAULT_END_SECONDS:g}.",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Process only this many seconds after skipping. Default: to the end.",
    )
    p.add_argument(
        "--warmup-seconds",
        type=float,
        default=DEFAULT_WARMUP_SECONDS,
        help=(
            f"Pre-roll this many seconds before the requested analysis start and discard those rows. "
            f"Default: {DEFAULT_WARMUP_SECONDS:g}."
        ),
    )
    p.add_argument(
        "--time-offset-seconds",
        type=float,
        default=DEFAULT_TIME_OFFSET_SECONDS,
        help=f"Constant offset applied to reported UTC times. Default: {DEFAULT_TIME_OFFSET_SECONDS:g}.",
    )
    p.add_argument(
        "--receiver-band-margin-hz",
        type=float,
        default=DEFAULT_RECEIVER_BAND_MARGIN_HZ,
        help="Extra margin added to the inferred receiver band edges before filtering candidates.",
    )
    p.add_argument(
        "--raw-chunk-seconds",
        type=float,
        default=DEFAULT_RAW_CHUNK_SECONDS,
        help=f"Raw read chunk size used during decimation. Default: {DEFAULT_RAW_CHUNK_SECONDS:g}.",
    )
    p.add_argument(
        "--range-plot-file",
        type=Path,
        default=DEFAULT_RANGE_PLOT,
        help=f"Template for the per-transmitter range-time plot filename. Default: {DEFAULT_RANGE_PLOT}.",
    )
    p.add_argument(
        "--range-min-km",
        type=float,
        default=DEFAULT_RANGE_MIN_KM,
        help=f"Minimum delay-equivalent range to plot (km). Default: {DEFAULT_RANGE_MIN_KM:g}.",
    )
    p.add_argument(
        "--range-max-km",
        type=float,
        default=DEFAULT_RANGE_MAX_KM,
        help=f"Maximum delay-equivalent range to plot (km). Default: {DEFAULT_RANGE_MAX_KM:g}.",
    )
    p.add_argument(
        "--plot-vmin-sigma",
        type=float,
        default=None,
        help="Lower color-axis limit in sigma units after normalization. Default: auto.",
    )
    p.add_argument(
        "--plot-vmax-sigma",
        type=float,
        default=None,
        help="Upper color-axis limit in sigma units after normalization. Default: auto.",
    )
    p.add_argument(
        "--pri-fold",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_PRI_FOLD,
        help="Fold matched-filter rows by PRI before plotting. Default: on.",
    )
    p.add_argument(
        "--enhance-surface",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_ENHANCE_SURFACE,
        help="Apply a contrast/persistence enhancement before plotting. Default: off.",
    )
    p.add_argument(
        "--enhance-mode",
        choices=("persistent-band", "ridge"),
        default=DEFAULT_ENHANCE_MODE,
        help=(
            "Enhancement style when --enhance-surface is enabled. "
            "'persistent-band' boosts coherent time-persistent bands; "
            "'ridge' keeps the older generic ridge response."
        ),
    )
    p.add_argument(
        "--enhance-time-sigma",
        type=float,
        default=DEFAULT_ENHANCE_TIME_SIGMA,
        help=f"Time-axis sigma for the enhancement smoother. Default: {DEFAULT_ENHANCE_TIME_SIGMA:g}.",
    )
    p.add_argument(
        "--enhance-range-sigma",
        type=float,
        default=DEFAULT_ENHANCE_RANGE_SIGMA,
        help=f"Range-axis sigma for the enhancement smoother. Default: {DEFAULT_ENHANCE_RANGE_SIGMA:g}.",
    )
    p.add_argument(
        "--enhance-background-factor",
        type=float,
        default=DEFAULT_ENHANCE_BACKGROUND_FACTOR,
        help=(
            "Background smoothing sigma is this factor times the enhancement sigma on each axis. "
            f"Default: {DEFAULT_ENHANCE_BACKGROUND_FACTOR:g}."
        ),
    )
    p.add_argument(
        "--show-hit-detections",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Overlay per-row peak detections on the range-time plot. Default: off.",
    )
    p.add_argument(
        "--no-range-plot",
        action="store_true",
        help="Skip range-time plotting. Default: False (plot enabled).",
    )
    return p.parse_args()


def datetime_to_unix_seconds(dt: datetime) -> float:
    return dt.timestamp()


def epoch_to_datetime(epoch_str: str) -> datetime:
    if epoch_str.endswith("Z"):
        epoch_str = epoch_str.replace("Z", "+00:00")
    return datetime.fromisoformat(epoch_str).astimezone(timezone.utc)


def safe_stem(text: str) -> str:
    text = text.strip().replace("/", "_")
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "candidate"


def compute_receiver_band(center_hz: float, fs_in: float, margin_hz: float) -> tuple[float, float]:
    half = fs_in / 2.0
    return center_hz - half - margin_hz, center_hz + half + margin_hz


def robust_sigma(x: np.ndarray) -> float:
    return float(np.median(np.abs(x)) / 0.6745 + 1e-12)


def estimate_freq_hz(x: np.ndarray, fs: float) -> Optional[float]:
    if x.size < 4:
        return None
    if np.iscomplexobj(x):
        phase = np.unwrap(np.angle(x))
    else:
        analytic = signal.hilbert(x)
        phase = np.unwrap(np.angle(analytic))
    t = np.arange(x.size, dtype=np.float64) / fs
    slope, _ = np.polyfit(t, phase, 1)
    return float(slope / (2.0 * math.pi))


def transmitter_matches(tx: PulsedTransmitter, query: str) -> bool:
    q = query.lower().strip()
    return any(
        q in field.lower()
        for field in (
            tx.network,
            tx.site,
            tx.system,
            tx.code,
            tx.label,
        )
    )


def make_template_bank(tx: PulsedTransmitter, fs_out: float) -> tuple[list[tuple[str, np.ndarray]], str]:
    if tx.prf_hz is None or tx.prf_hz <= 0:
        raise RuntimeError(f"Transmitter {tx.label} is missing a usable PRF.")

    code = tx.code.strip().lower()
    templates: list[tuple[str, np.ndarray]] = []

    if code.startswith("barker"):
        if tx.chip_rate_hz is None or tx.chip_rate_hz <= 0:
            raise RuntimeError(f"Transmitter {tx.label} is missing a usable chip_rate_hz.")
        chip_samples_f = fs_out / tx.chip_rate_hz
        chip_samples = max(1, int(round(chip_samples_f)))
        if not math.isclose(chip_samples_f, chip_samples, rel_tol=0.0, abs_tol=1e-6):
            raise RuntimeError(
                f"channel-rate {fs_out:g} Hz does not give an integer Barker chip length for {tx.label}; "
                f"expected chip_rate_hz={tx.chip_rate_hz:g}."
            )
        pulse_samples = chip_samples * BARKER_7.size
        templates.append(("phase", np.repeat(BARKER_7, chip_samples).astype(np.complex64)))
        return templates, f"{tx.code} ({chip_samples} samples/chip, {pulse_samples} samples/pulse)"

    if code == "monopulse":
        chip_samples = max(1, int(round(fs_out / tx.prf_hz)))
        templates.append(("energy", np.ones(chip_samples, dtype=np.complex64)))
        return templates, f"{tx.code} ({chip_samples} samples)"

    raise RuntimeError(f"Unsupported code {tx.code!r} for {tx.label}.")


def template_energy(template: np.ndarray) -> float:
    return float(np.sum(np.abs(template) ** 2))


def fold_score_row(row: np.ndarray, fold_samples: int) -> np.ndarray:
    if fold_samples <= 0:
        raise ValueError("fold_samples must be positive")
    if row.size == 0:
        return np.zeros(fold_samples, dtype=np.float32)

    idx = np.arange(row.size, dtype=np.int64) % int(fold_samples)
    sums = np.bincount(idx, weights=np.asarray(row, dtype=np.float64), minlength=fold_samples)
    counts = np.bincount(idx, minlength=fold_samples)
    folded = sums / np.maximum(counts, 1)
    return folded.astype(np.float32, copy=False)


def fold_complex_row(row: np.ndarray, fold_samples: int) -> np.ndarray:
    if fold_samples <= 0:
        raise ValueError("fold_samples must be positive")
    if row.size == 0:
        return np.zeros(fold_samples, dtype=np.complex64)

    idx = np.arange(row.size, dtype=np.int64) % int(fold_samples)
    real = np.bincount(idx, weights=np.asarray(row.real, dtype=np.float64), minlength=fold_samples)
    imag = np.bincount(idx, weights=np.asarray(row.imag, dtype=np.float64), minlength=fold_samples)
    counts = np.bincount(idx, minlength=fold_samples)
    folded = (real + 1j * imag) / np.maximum(counts, 1)
    return folded.astype(np.complex64, copy=False)


def enhance_surface(
    data: np.ndarray,
    time_sigma: float,
    range_sigma: float,
    background_factor: float,
    mode: str = DEFAULT_ENHANCE_MODE,
) -> np.ndarray:
    if data.size == 0:
        return data
    mode = mode.strip().lower()
    time_sigma = max(float(time_sigma), 0.0)
    range_sigma = max(float(range_sigma), 0.0)
    background_factor = max(float(background_factor), 1.0)

    image = np.asarray(data, dtype=np.float32, copy=False)
    finite = np.isfinite(image)
    if not np.any(finite):
        return np.zeros_like(image, dtype=np.float32)

    baseline = float(np.median(image[finite]))
    scale = robust_sigma(image[finite])
    z = (image - baseline) / (scale + 1e-12)
    z = np.clip(z, -10.0, 10.0)

    if mode == "ridge":
        if time_sigma > 0.0 or range_sigma > 0.0:
            detail = ndimage.gaussian_filter(z, sigma=(time_sigma, range_sigma), mode="nearest")
        else:
            detail = z
        background = ndimage.gaussian_filter(
            detail,
            sigma=(max(time_sigma * background_factor, 1.0), max(range_sigma * background_factor, 1.0)),
            mode="nearest",
        )
        ridges = detail - background

        # Frangi-style ridge response on the high-passed surface.
        ridge_response = np.zeros_like(ridges, dtype=np.float32)
        scales = (1.0, 2.0)
        beta = 0.5
        for scale in scales:
            ixx = ndimage.gaussian_filter(ridges, sigma=scale, order=(0, 2), mode="nearest")
            iyy = ndimage.gaussian_filter(ridges, sigma=scale, order=(2, 0), mode="nearest")
            ixy = ndimage.gaussian_filter(ridges, sigma=scale, order=(1, 1), mode="nearest")
            tmp = np.sqrt(np.maximum((ixx - iyy) ** 2 + 4.0 * ixy**2, 0.0))
            lam1 = 0.5 * (ixx + iyy - tmp)
            lam2 = 0.5 * (ixx + iyy + tmp)
            swap = np.abs(lam1) > np.abs(lam2)
            small = np.where(swap, lam2, lam1)
            large = np.where(swap, lam1, lam2)
            rb = np.abs(small) / (np.abs(large) + 1e-12)
            s = np.sqrt(small**2 + large**2)
            c = float(np.percentile(s[np.isfinite(s)], 90)) if np.any(np.isfinite(s)) else 1.0
            vessel = np.exp(-(rb**2) / (2.0 * beta**2)) * (1.0 - np.exp(-(s**2) / (2.0 * (c**2 + 1e-12))))
            vessel = np.where(large < 0.0, vessel, 0.0)
            ridge_response = np.maximum(ridge_response, vessel.astype(np.float32, copy=False))

        sigma = robust_sigma(ridge_response[np.isfinite(ridge_response)]) if np.any(np.isfinite(ridge_response)) else 1.0
        return (ridge_response / (sigma + 1e-12)).astype(np.float32, copy=False)

    # Default: preserve horizontal persistence while suppressing broad range-wise clutter.
    if range_sigma > 0.0:
        detail = ndimage.gaussian_filter(z, sigma=(0.0, range_sigma), mode="nearest")
    else:
        detail = z
    background = ndimage.gaussian_filter(
        detail,
        sigma=(1.0, max(range_sigma * background_factor, 1.0)),
        mode="nearest",
    )
    band = detail - background
    if time_sigma > 0.0:
        band = ndimage.gaussian_filter(band, sigma=(time_sigma, 0.0), mode="nearest")

    sigma = robust_sigma(band[np.isfinite(band)]) if np.any(np.isfinite(band)) else 1.0
    return (band / (sigma + 1e-12)).astype(np.float32, copy=False)


def _hamming_taps_for_transition(fs: float, transition_hz: float) -> int:
    # Hamming rule of thumb: transition width ~= 3.3 * fs / N.
    if transition_hz <= 0:
        raise ValueError("transition_hz must be positive")
    taps = int(math.ceil(3.3 * fs / transition_hz))
    if taps % 2 == 0:
        taps += 1
    return max(taps, 3)


def load_decimated_channel(
    reader,
    channel: str,
    start_sample: int,
    total_samples: int,
    fs_in: float,
    fs_out: float,
    center_hz: float,
    target_hz: float,
    lp_hz: float,
    transition_hz: float,
    raw_chunk_seconds: float,
) -> np.ndarray:
    decim = int(round(fs_in / fs_out))
    if decim < 1:
        decim = 1
    if not math.isclose(fs_in / decim, fs_out, rel_tol=0.0, abs_tol=1e-9):
        raise RuntimeError("channel-rate must divide the input sample rate exactly.")

    mix_hz = target_hz - center_hz
    phase = 0.0
    phase_step = -2.0 * math.pi * mix_hz / fs_in

    chunk_samples = max(int(round(raw_chunk_seconds * fs_in)), decim)
    taps = signal.firwin(_hamming_taps_for_transition(fs_in, transition_hz), lp_hz, fs=fs_in).astype(np.float32)
    zi = np.zeros(taps.size - 1, dtype=np.complex64)
    decim_offset = 0

    cursor = start_sample
    stop_sample = start_sample + total_samples
    pieces: list[np.ndarray] = []

    while cursor < stop_sample:
        take = min(chunk_samples, stop_sample - cursor)
        try:
            chunk = reader.read_vector_1d(cursor, take, channel)
        except OSError:
            chunk = np.zeros(take, dtype=np.complex64)
        if chunk is None:
            chunk = np.zeros(take, dtype=np.complex64)
        chunk = np.nan_to_num(chunk.astype(np.complex64, copy=False), nan=0.0, posinf=0.0, neginf=0.0)

        if mix_hz != 0.0:
            n = np.arange(chunk.size, dtype=np.float64)
            mixer = np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
            chunk = chunk * mixer
            phase = (phase + phase_step * chunk.size) % (2.0 * math.pi)

        filt, zi = signal.lfilter(taps, [1.0], chunk, zi=zi)
        out = filt[decim_offset::decim]
        decim_offset = (decim_offset - filt.size) % decim
        if out.size:
            pieces.append(out.astype(np.complex64, copy=False))
        cursor += take

    if not pieces:
        return np.array([], dtype=np.complex64)
    return np.concatenate(pieces)


def plot_range_time(
    range_rows: list[np.ndarray],
    row_times: list[datetime],
    fs: float,
    path: Path,
    fold_samples: Optional[int],
    range_min_km: float,
    range_max_km: float,
    cmap_vmin: Optional[float] = None,
    cmap_vmax: Optional[float] = None,
    show_hit_detections: bool = False,
    hit_sigma_threshold: float = DEFAULT_SIGMA_THRESHOLD,
    enhance_surface_flag: bool = False,
    enhance_mode: str = DEFAULT_ENHANCE_MODE,
    enhance_time_sigma: float = DEFAULT_ENHANCE_TIME_SIGMA,
    enhance_range_sigma: float = DEFAULT_ENHANCE_RANGE_SIGMA,
    enhance_background_factor: float = DEFAULT_ENHANCE_BACKGROUND_FACTOR,
    title: Optional[str] = None,
) -> Optional[Path]:
    try:
        import matplotlib.dates as mdates  # type: ignore
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # pragma: no cover - optional
        print(f"Range-time plot skipped (matplotlib not available: {exc})")
        return None

    if not range_rows:
        print("Range-time plot skipped (no correlation rows captured).")
        return None

    def _pad_rows(rows: list[np.ndarray]) -> np.ndarray:
        max_len = max(int(row.size) for row in rows)
        if max_len <= 0:
            return np.zeros((0, len(rows)), dtype=np.float32)
        stacked = np.full((len(rows), max_len), np.nan, dtype=np.float32)
        for i, row in enumerate(rows):
            arr = np.asarray(row, dtype=np.float32, copy=False)
            stacked[i, : arr.size] = arr
        return stacked.T

    if fold_samples is not None and fold_samples > 0:
        folded_rows = [fold_score_row(row, fold_samples) for row in range_rows]
        data = _pad_rows(folded_rows)
    else:
        data = _pad_rows(range_rows)
    data = np.asarray(np.ma.masked_invalid(data).filled(0.0), dtype=np.float32)
    if enhance_surface_flag:
        data = enhance_surface(
            data,
            enhance_time_sigma,
            enhance_range_sigma,
            enhance_background_factor,
            mode=enhance_mode,
        )
    y_edges_seconds = np.arange(data.shape[0] + 1, dtype=np.float64) / fs
    delay_equiv_range_km = C_KM_PER_S * y_edges_seconds
    x_nums = mdates.date2num(row_times)

    fig, ax0 = plt.subplots(figsize=(13.5, 8.0))

    if len(x_nums) > 1:
        step = float(np.median(np.diff(x_nums)))
    else:
        step = 1.0 / 86400.0
    x0 = float(x_nums[0])
    x1 = float(x_nums[-1] + step)

    cf = ax0.imshow(
        data,
        aspect="auto",
        origin="lower",
        extent=[x0, x1, float(delay_equiv_range_km[0]), float(delay_equiv_range_km[-1])],
        cmap="viridis",
        interpolation="nearest",
        vmin=cmap_vmin,
        vmax=cmap_vmax,
    )
    ax0.set_title(title or "PRI-integrated matched-filter output vs. delay", fontsize=21, fontweight="bold")
    ax0.set_ylabel("One-way delay-equivalent range (km)", fontsize=15)
    ax0.set_xlabel("UTC time", fontsize=15)
    ax0.xaxis_date()
    ax0.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    range_min_km = max(0.0, float(range_min_km))
    range_max_km = min(float(range_max_km), float(delay_equiv_range_km[-1]))
    ax0.set_ylim(range_min_km, range_max_km)
    ax0.grid(False)

    if show_hit_detections:
        lo_idx = max(0, int(math.floor(range_min_km / C_KM_PER_S * fs)))
        hi_idx = min(data.shape[0], int(math.ceil(range_max_km / C_KM_PER_S * fs)))
        if hi_idx > lo_idx:
            visible = data[lo_idx:hi_idx, :]
            binary = np.asarray(visible > hit_sigma_threshold, dtype=bool)
            labels, num_labels = ndimage.label(binary, structure=np.ones((3, 3), dtype=int))
            best_label = 0
            best_score = -np.inf
            for label_id in range(1, num_labels + 1):
                comp = labels == label_id
                area = int(np.count_nonzero(comp))
                if area < 3:
                    continue
                ys, xs = np.where(comp)
                cols = np.unique(xs).size
                if cols < 2:
                    continue
                score = float(cols * 1000 + area)
                if score > best_score:
                    best_score = score
                    best_label = label_id
            if best_label != 0:
                comp = labels == best_label
                ys, xs = np.where(comp)
                hit_times: list[datetime] = []
                hit_ranges: list[float] = []
                for col in np.unique(xs):
                    col_rows = ys[xs == col]
                    if col_rows.size == 0:
                        continue
                    center_row = float(np.median(col_rows)) + lo_idx
                    hit_times.append(row_times[int(col)])
                    hit_ranges.append(C_KM_PER_S * (center_row / fs))
                if hit_times:
                    ax0.plot(hit_times, hit_ranges, color="white", linewidth=5.0, alpha=0.95, zorder=3)
                    ax0.plot(hit_times, hit_ranges, color="black", linewidth=1.0, alpha=0.4, zorder=4)
                    ax0.scatter(hit_times, hit_ranges, s=18, c="red", linewidths=0.0, zorder=5)
                    best_component = True
                else:
                    best_component = False
            else:
                best_component = False
        else:
            best_component = False

        if not best_component:
            hit_times: list[datetime] = []
            hit_ranges: list[float] = []
            for row_time, row in zip(row_times, data.T):
                if hi_idx <= lo_idx:
                    break
                visible = row[lo_idx:hi_idx]
                if visible.size == 0:
                    continue
                peak_idx = int(np.argmax(visible))
                peak_score = float(visible[peak_idx])
                if peak_score < hit_sigma_threshold:
                    continue
                hit_times.append(row_time)
                hit_ranges.append(C_KM_PER_S * ((lo_idx + peak_idx) / fs))
            if hit_times:
                ax0.scatter(
                    hit_times,
                    hit_ranges,
                    s=90,
                    facecolors="none",
                    edgecolors="white",
                    linewidths=1.4,
                    zorder=3,
                )
                ax0.scatter(hit_times, hit_ranges, s=20, c="red", linewidths=0.0, alpha=1.0, zorder=4)

    cbar = fig.colorbar(cf, ax=ax0, label="Matched-filter score (sigma units)")
    cbar.ax.tick_params(labelsize=12)

    fig.autofmt_xdate()
    fig.subplots_adjust(left=0.08, right=0.92, top=0.92, bottom=0.12)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print(f"Wrote {path}")
    return path


def detect_transmitter(
    reader,
    channel: str,
    fs_in: float,
    center_hz: float,
    tx: PulsedTransmitter,
    raw_scan_start_sample: int,
    raw_scan_total_samples: int,
    scan_start_display_utc: datetime,
    analysis_start_display_utc: datetime,
    channel_rate: float,
    channel_lp_hz: float,
    channel_transition_hz: float,
    raw_chunk_seconds: float,
    block_seconds: float,
    pri_fold: bool,
    sigma_threshold: float,
) -> DetectionResult:
    raw_scan_start_sample = int(raw_scan_start_sample)
    raw_scan_total_samples = max(int(raw_scan_total_samples), 1)

    y = load_decimated_channel(
        reader,
        channel=channel,
        start_sample=raw_scan_start_sample,
        total_samples=raw_scan_total_samples,
        fs_in=fs_in,
        fs_out=channel_rate,
        center_hz=center_hz,
        target_hz=tx.freq_hz,
        lp_hz=channel_lp_hz,
        transition_hz=channel_transition_hz,
        raw_chunk_seconds=raw_chunk_seconds,
    )
    if y.size == 0:
        raise RuntimeError(f"No decimated samples produced for {tx.label}.")

    templates, template_name = make_template_bank(tx, channel_rate)
    template_samples = int(templates[0][1].size) if templates else 0
    pri_samples = max(1, int(round(channel_rate / tx.prf_hz)))
    overlap = max((tpl.size for _name, tpl in templates), default=1) - 1
    block_samples = max(1, int(round(block_seconds * channel_rate)))

    prev_tail = np.zeros(overlap, dtype=np.complex64)
    corr_rows: list[np.ndarray] = []
    row_times: list[datetime] = []
    hits: list[DetectionHit] = []

    total_blocks = int(math.ceil(y.size / block_samples))
    start_wall = time.monotonic()

    for block_index in range(total_blocks):
        lo = block_index * block_samples
        hi = min(y.size, lo + block_samples)
        block = y[lo:hi]
        if block.size == 0:
            continue

        search = np.concatenate([prev_tail, block])
        best_score_centered: Optional[np.ndarray] = None
        best_peak = -np.inf
        for _tpl_name, template in templates:
            tpl_len = int(template.size)
            tpl_energy = template_energy(template)
            corr = signal.correlate(search, template, mode="valid", method="fft")
            power = signal.correlate(np.abs(search) ** 2, np.ones(tpl_len, dtype=np.float32), mode="valid", method="fft")
            denom = np.sqrt(np.maximum(power, 1e-12) * max(tpl_energy, 1e-12))
            score = corr / np.maximum(denom, 1e-12)
            # Fold power, not complex correlation, so pulse-to-pulse phase rotation
            # does not cancel a stable return.
            score_profile = fold_score_row(np.abs(score), pri_samples) if pri_fold else np.abs(score)
            score_centered = score_profile - np.median(score_profile)
            peak = float(np.max(score_centered)) if score_centered.size else -np.inf
            if peak > best_peak:
                best_peak = peak
                best_score_centered = score_centered

        if best_score_centered is None:
            continue

        row_time = scan_start_display_utc + timedelta(seconds=((lo + 0.5 * block.size) / channel_rate))
        if row_time < analysis_start_display_utc:
            prev_tail = search[-overlap:] if overlap > 0 else np.zeros(0, dtype=np.complex64)
            continue

        corr_rows.append(best_score_centered.astype(np.float32, copy=False))
        row_times.append(row_time)

        peak_idx = int(np.argmax(best_score_centered))
        peak_score = float(best_score_centered[peak_idx])
        sigma = robust_sigma(best_score_centered)
        if peak_score >= sigma_threshold * sigma:
            hits.append(
                DetectionHit(
                    score=peak_score,
                    sample_index=raw_scan_start_sample + lo + int(block.size // 2),
                    lag_samples=peak_idx,
                    time_utc=row_time,
                    residual_hz=None,
                    range_km=C_KM_PER_S * (peak_idx / channel_rate),
                    template_name=template_name,
                )
            )
        prev_tail = search[-overlap:] if overlap > 0 else np.zeros(0, dtype=np.complex64)

        processed_samples = min(y.size, hi)
        processed_seconds = processed_samples / channel_rate
        pct = 100.0 * processed_samples / y.size
        elapsed = time.monotonic() - start_wall
        print(
            f"{tx.label}: processed {processed_seconds:.1f}/{y.size / channel_rate:.1f} s "
            f"({pct:.1f}%), elapsed {elapsed:.1f} s.",
            flush=True,
        )

    return DetectionResult(
        transmitter=tx,
        hits=hits,
        corr_rows=corr_rows,
        row_times=row_times,
        track_ranges_km=[],
        residual_times=[],
        residual_hz=[],
        template_name=template_name,
        template_samples=template_samples,
        pri_samples=pri_samples,
    )


def write_analysis_csv(path: Path, result: DetectionResult, fs: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "utc_time",
                "peak_lag_samples",
                "peak_range_km",
                "peak_score",
                "template",
                "network",
                "site",
                "system",
                "freq_mhz",
                "code",
                "prf_hz",
                "chip_rate_hz",
            ]
        )
        tx = result.transmitter
        for row_time, row in zip(result.row_times, result.corr_rows):
            peak_lag_samples = int(np.argmax(row)) if row.size else 0
            peak_range_km = C_KM_PER_S * (peak_lag_samples / fs)
            peak_score = float(row[peak_lag_samples]) if row.size else float("nan")
            writer.writerow(
                [
                    row_time.isoformat(),
                    peak_lag_samples,
                    f"{peak_range_km:.3f}",
                    f"{peak_score:.3f}",
                    result.template_name,
                    tx.network,
                    tx.site,
                    tx.system,
                    f"{tx.freq_mhz:.4f}",
                    tx.code,
                    "" if tx.prf_hz is None else f"{tx.prf_hz:.1f}",
                    "" if tx.chip_rate_hz is None else f"{tx.chip_rate_hz:.1f}",
                ]
            )
    print(f"Wrote {path} ({len(result.corr_rows)} rows)")


def main() -> int:
    args = parse_args()
    input_root = args.dataset_root.expanduser()
    output_prefix = args.output_prefix.expanduser()
    range_plot_template = args.range_plot_file.expanduser()

    reader, channel, reader_mode = open_drf_like_reader(input_root, args.channel)
    if reader_mode != "digital_rf":
        print(f"Using flat Data/rf@*.h5 reader for channel {channel} under {input_root}")

    props = reader.get_properties(channel)
    fs_in = float(props["samples_per_second"])
    center_hz = float(props["center_frequency_hz"]) if args.center_hz is None else float(args.center_hz)
    start_sample, stop_sample = reader.get_bounds(channel)
    if start_sample is None or stop_sample is None:
        raise RuntimeError("Dataset bounds are unavailable.")
    start_sample = int(start_sample)
    stop_sample = int(stop_sample)

    epoch = epoch_to_datetime(props["epoch"])
    recording_start_utc = epoch + timedelta(seconds=start_sample / fs_in)
    recording_end_utc = epoch + timedelta(seconds=stop_sample / fs_in)

    analysis_start_raw_utc = recording_start_utc + timedelta(seconds=max(0.0, args.start_seconds))
    analysis_end_raw_utc = recording_end_utc - timedelta(seconds=max(0.0, args.end_seconds))
    if args.seconds is not None:
        analysis_end_raw_utc = min(analysis_end_raw_utc, analysis_start_raw_utc + timedelta(seconds=float(args.seconds)))
    if analysis_end_raw_utc <= analysis_start_raw_utc:
        raise RuntimeError("Requested time span is empty.")

    analysis_start_display_utc = analysis_start_raw_utc + timedelta(seconds=args.time_offset_seconds)
    analysis_end_display_utc = analysis_end_raw_utc + timedelta(seconds=args.time_offset_seconds)
    warmup_seconds = max(0.0, float(args.warmup_seconds))
    scan_start_raw_utc = max(recording_start_utc, analysis_start_raw_utc - timedelta(seconds=warmup_seconds))
    raw_scan_start_sample = start_sample + int(round((scan_start_raw_utc - recording_start_utc).total_seconds() * fs_in))
    raw_scan_total_samples = int(round((analysis_end_raw_utc - scan_start_raw_utc).total_seconds() * fs_in))
    warmup_seconds_applied = max(0.0, (analysis_start_raw_utc - scan_start_raw_utc).total_seconds())

    channel_rate = min(float(args.channel_rate), fs_in)
    decim = int(round(fs_in / channel_rate))
    if decim < 1:
        decim = 1
    if not math.isclose(fs_in / decim, channel_rate, rel_tol=0.0, abs_tol=1e-6):
        channel_rate = fs_in
        decim = 1
        print(f"Adjusted channel-rate to {channel_rate:g} Hz for fs_in={fs_in:g} Hz.")
    channel_lp_hz = min(float(args.channel_lp_hz), 0.45 * channel_rate, 0.45 * fs_in)
    if channel_lp_hz != float(args.channel_lp_hz):
        print(f"Adjusted channel lowpass to {channel_lp_hz:g} Hz to stay below Nyquist.")

    band_low_hz, band_high_hz = compute_receiver_band(center_hz, fs_in, args.receiver_band_margin_hz)

    candidates = [tx for tx in CATALOG if tx.supports_template and band_low_hz <= tx.freq_hz <= band_high_hz]
    if args.transmitter:
        candidates = [tx for tx in candidates if transmitter_matches(tx, args.transmitter)]
        if not candidates:
            raise RuntimeError(f"No catalog entries matched transmitter filter {args.transmitter!r}.")

    if not candidates:
        print("No supported pulsed transmitters fall inside the receiver band.")
        return 0

    print(f"Dataset root: {input_root}")
    print(f"Channel: {channel} (reader mode: {reader_mode})")
    print(f"Receiver band: {band_low_hz/1e6:.4f} to {band_high_hz/1e6:.4f} MHz")
    print(f"Analysis span: {analysis_start_display_utc.isoformat()} to {analysis_end_display_utc.isoformat()}")
    print(f"Warmup pre-roll: {warmup_seconds_applied:.1f} s")
    print(f"Matched-filter candidates: {len(candidates)}")

    for tx in candidates:
        chip_info = "" if tx.chip_rate_hz is None else f" chip_rate={tx.chip_rate_hz:.1f} Hz"
        print(f"Candidate: {tx.label} {tx.freq_mhz:.4f} MHz code={tx.code} prf={tx.prf_hz:g}{chip_info}")
        result = detect_transmitter(
            reader=reader,
            channel=channel,
            fs_in=fs_in,
            center_hz=center_hz,
            tx=tx,
            raw_scan_start_sample=raw_scan_start_sample,
            raw_scan_total_samples=raw_scan_total_samples,
            scan_start_display_utc=scan_start_raw_utc + timedelta(seconds=args.time_offset_seconds),
            analysis_start_display_utc=analysis_start_display_utc,
            channel_rate=channel_rate,
            channel_lp_hz=channel_lp_hz,
            channel_transition_hz=float(args.channel_transition_hz),
            raw_chunk_seconds=float(args.raw_chunk_seconds),
            block_seconds=float(args.block_seconds),
            pri_fold=bool(args.pri_fold),
            sigma_threshold=float(args.sigma_threshold),
        )

        prefix_stem = output_prefix.stem if output_prefix.suffix else output_prefix.name
        stem = f"{prefix_stem}_{safe_stem(tx.label)}_{tx.freq_mhz:.4f}MHz"
        csv_path = output_prefix.with_name(f"{stem}.csv")
        plot_path = range_plot_template.with_name(f"{stem}.png")
        write_analysis_csv(csv_path, result, channel_rate)

        if not args.no_range_plot:
            if result.corr_rows:
                global_sigma = robust_sigma(np.concatenate(result.corr_rows))
                norm_rows = [row / (global_sigma + 1e-12) for row in result.corr_rows]
                plot_range_time(
                    norm_rows,
                    result.row_times,
                    channel_rate,
                    plot_path,
                    result.pri_samples if args.pri_fold else None,
                    args.range_min_km,
                    args.range_max_km,
                    cmap_vmin=args.plot_vmin_sigma,
                    cmap_vmax=args.plot_vmax_sigma,
                    show_hit_detections=bool(args.show_hit_detections),
                    hit_sigma_threshold=float(args.sigma_threshold),
                    enhance_surface_flag=bool(args.enhance_surface),
                    enhance_mode=str(args.enhance_mode),
                    enhance_time_sigma=float(args.enhance_time_sigma),
                    enhance_range_sigma=float(args.enhance_range_sigma),
                    enhance_background_factor=float(args.enhance_background_factor),
                    title=f"{tx.label}: {result.template_name}",
                )
            else:
                print(f"No correlation rows captured for {tx.label}; skipping plot.")
        print(f"  matched-filter rows={len(result.corr_rows)} hits={len(result.hits)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
