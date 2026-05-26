#!/usr/bin/env python3
"""
Detect WWV 1 kHz tick leading edges and estimate tone frequency from DigitalRF.

Pipeline (matches the working audio demod path):
1) Mix raw IQ to 10 MHz.
2) Decimate to the requested channel rate, lowpass to 10 kHz.
3) Apply the same lowpass / envelope / matched-filter steps at that rate.
4) Envelope detect, bandpass 600-1400 Hz.
5) Matched filter 5-cycle 1 kHz tick to find leading edges.
6) Estimate tone frequency per tick via phase slope on the bandpassed segment.
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

import digital_rf as drf
import numpy as np
from scipy import signal

from stack_superdarn_iss_ephem import geodetic_to_ecef, load_tle, predict_delay_doppler


os.environ.setdefault("MPLBACKEND", "Agg")

DEFAULT_INPUT_ROOT = Path("/Users/chartat1/data/hf_data/itsi/rooftop_20260114/M10124")
DEFAULT_CHANNEL = "cha"
DEFAULT_TARGET_HZ = 10_000_000.0
DEFAULT_BLOCK_SECONDS = 1.0
DEFAULT_CHANNEL_RATE = None
DEFAULT_CHANNEL_LP_HZ = 10_000.0
DEFAULT_CHANNEL_TRANSITION_HZ = 3_000.0
DEFAULT_BP_LOW_HZ = 600.0
DEFAULT_BP_HIGH_HZ = 1400.0
DEFAULT_BP_TRANSITION_HZ = 200.0
DEFAULT_TONE_HZ = 1000.0
DEFAULT_TONE_CYCLES = 5
DEFAULT_SIGMA_THRESHOLD = 6.0
DEFAULT_RANGE_PLOT = Path("wwv_range_time.png")
DEFAULT_RANGE_MAX_KM = 5000.0
DEFAULT_RANGE_MIN_KM = 0.0
DEFAULT_CARRIER_LP_HZ = 200.0
DEFAULT_START_SECONDS = 1.0
DEFAULT_END_SECONDS = 1.0
# WWV 25 MHz antenna coordinates from NIST.
DEFAULT_TX_LAT_DEG = 40.68069444444444
DEFAULT_TX_LON_DEG = -105.04072222222223
DEFAULT_TX_ALT_M = 1525.0

C_KM_PER_S = 299_792.458


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect WWV 1 kHz ticks from DigitalRF.")
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help=f"DigitalRF dataset root. Default: {DEFAULT_INPUT_ROOT}.",
    )
    p.add_argument("--channel", default=DEFAULT_CHANNEL, help=f"Channel name. Default: {DEFAULT_CHANNEL}.")
    p.add_argument(
        "--raw-center-hz",
        type=float,
        default=None,
        help="Recorded center frequency (Hz). Default: DigitalRF metadata center_frequency_hz when present (supersedes the default None).",
    )
    p.add_argument(
        "--target-hz",
        type=float,
        default=DEFAULT_TARGET_HZ,
        help=f"Target carrier to demodulate (Hz). Default: {DEFAULT_TARGET_HZ:g}.",
    )
    p.add_argument(
        "--block-seconds",
        type=float,
        default=DEFAULT_BLOCK_SECONDS,
        help=f"Seconds of RF to process per block. Default: {DEFAULT_BLOCK_SECONDS:g}.",
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
        help=f"Skip this many seconds from the start. Default: {DEFAULT_START_SECONDS:g}.",
    )
    p.add_argument(
        "--end-seconds",
        type=float,
        default=DEFAULT_END_SECONDS,
        help=f"Skip this many seconds from the end (after --seconds). Default: {DEFAULT_END_SECONDS:g}.",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Process only this many seconds. Default: to end.",
    )
    p.add_argument(
        "--time-offset-seconds",
        type=float,
        default=0.0,
        help="Optional constant offset applied to reported UTC times. Default: 0.",
    )
    p.add_argument(
        "--output-csv",
        type=Path,
        default=Path("wwv_tick_times.csv"),
        help="Output CSV path. Default: wwv_tick_times.csv in cwd.",
    )
    p.add_argument(
        "--range-plot-file",
        type=Path,
        default=DEFAULT_RANGE_PLOT,
        help=f"Range-time-intensity plot path. Default: {DEFAULT_RANGE_PLOT}.",
    )
    p.add_argument(
        "--tle-file",
        type=Path,
        default=None,
        help="Optional ISS TLE file to overlay predicted range and Doppler.",
    )
    p.add_argument(
        "--tx-lat-deg",
        type=float,
        default=DEFAULT_TX_LAT_DEG,
        help=f"WWV transmitter latitude for prediction overlay. Default: {DEFAULT_TX_LAT_DEG:.6f}.",
    )
    p.add_argument(
        "--tx-lon-deg",
        type=float,
        default=DEFAULT_TX_LON_DEG,
        help=f"WWV transmitter longitude for prediction overlay. Default: {DEFAULT_TX_LON_DEG:.6f}.",
    )
    p.add_argument(
        "--tx-alt-m",
        type=float,
        default=DEFAULT_TX_ALT_M,
        help=f"WWV transmitter altitude for prediction overlay. Default: {DEFAULT_TX_ALT_M:g}.",
    )
    p.add_argument(
        "--prediction-carrier-hz",
        type=float,
        default=None,
        help="Carrier frequency to use for the Doppler prediction. Default: target-hz.",
    )
    p.add_argument(
        "--range-offset-km",
        type=float,
        default=None,
        help="Constant offset added to the predicted range curve. Default: auto-fit from detections.",
    )
    p.add_argument(
        "--doppler-offset-hz",
        type=float,
        default=None,
        help="Constant offset added to the predicted Doppler curve. Default: auto-fit from observed Doppler.",
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
        "--no-range-plot",
        action="store_true",
        help="Skip range-time-intensity plotting. Default: False (plot enabled).",
    )
    return p.parse_args()


def epoch_to_datetime(epoch_str: str) -> datetime:
    if epoch_str.endswith("Z"):
        epoch_str = epoch_str.replace("Z", "+00:00")
    return datetime.fromisoformat(epoch_str).astimezone(timezone.utc)


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


def robust_sigma(x: np.ndarray) -> float:
    return float(np.median(np.abs(x)) / 0.6745 + 1e-12)


def datetime_to_unix_seconds(dt: datetime) -> float:
    return dt.timestamp()


def fit_constant_offset(observed: np.ndarray, predicted: np.ndarray) -> float:
    if observed.size == 0 or predicted.size == 0:
        return 0.0
    if observed.shape != predicted.shape:
        raise ValueError("Observed and predicted arrays must have the same shape.")
    return float(np.median(observed - predicted))


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


def plot_range_time(
    range_rows: List[np.ndarray],
    block_times: List[datetime],
    fs: float,
    path: Path,
    range_min_km: float,
    range_max_km: float,
    hits: Optional[List[TickHit]] = None,
    doppler_times: Optional[List[datetime]] = None,
    doppler_hz: Optional[List[float]] = None,
    doppler_yerr: Optional[List[float]] = None,
    predicted_range_times: Optional[List[datetime]] = None,
    predicted_range_km: Optional[np.ndarray] = None,
    predicted_doppler_times: Optional[List[datetime]] = None,
    predicted_doppler_hz: Optional[np.ndarray] = None,
    range_offset_km: float = 0.0,
    doppler_offset_hz: float = 0.0,
) -> Optional[Path]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
        import matplotlib.dates as mdates  # type: ignore
    except Exception as exc:  # pragma: no cover - optional
        print(f"Range-time plot skipped (matplotlib not available: {exc})")
        return None

    if not range_rows:
        print("Range-time plot skipped (no data captured).")
        return None

    data = np.vstack(range_rows).T  # shape: (range_bins, time_bins)
    y_seconds = np.arange(data.shape[0], dtype=np.float64) / fs
    virtual_range_km = y_seconds * C_KM_PER_S
    x_nums = mdates.date2num(block_times)

    font_size = 18
    title_size = 22
    fig = plt.figure(figsize=(13.5, 9.5))
    gs = fig.add_gridspec(
        2,
        2,
        width_ratios=[20, 1],
        height_ratios=[3, 1],
        wspace=0.05,
    )
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[1, 0], sharex=ax0)
    cax = fig.add_subplot(gs[0, 1])
    cf = ax0.pcolormesh(
        x_nums,
        virtual_range_km,
        data,
        shading="nearest",
        cmap="viridis",
        antialiased=False,
        linewidth=0.0,
    )
    ax0.set_title(
        "Matched filter output vs. virtual range",
        fontsize=title_size,
        fontweight="bold",
    )
    ax0.set_ylabel("Virtual range (km)", fontsize=font_size)
    ax0.xaxis_date()
    ax0.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    ax0.set_ylim(range_min_km, range_max_km)
    if hits:
        times = [h.time_utc for h in hits if h.range_km is not None and range_min_km <= h.range_km <= range_max_km]
        ranges = [h.range_km for h in hits if h.range_km is not None and range_min_km <= h.range_km <= range_max_km]
        if times:
            ax0.scatter(times, ranges, s=14, c="red", alpha=0.8, linewidths=0.0)
    if predicted_range_times and predicted_range_km is not None:
        ax0.plot(
            predicted_range_times,
            predicted_range_km + range_offset_km,
            color="white",
            linewidth=2.2,
            alpha=0.95,
            label=f"Predicted + {range_offset_km:+.1f} km",
            zorder=6,
        )
        ax0.legend(loc="upper right", fontsize=12, framealpha=0.85)
    cbar = fig.colorbar(cf, cax=cax, label="Matched filter score (sigma units)")
    cbar.ax.tick_params(labelsize=font_size)
    cbar.set_label("Matched filter score (sigma units)", fontsize=font_size)

    if doppler_times and doppler_hz:
        doppler_y = np.ma.masked_invalid(np.asarray(doppler_hz, dtype=np.float64))
        if doppler_yerr is not None:
            doppler_err = np.ma.masked_invalid(np.asarray(doppler_yerr, dtype=np.float64))
            ax1.errorbar(
                doppler_times,
                doppler_y,
                yerr=doppler_err,
                fmt="-o",
                color="black",
                linewidth=1.0,
                markersize=2.5,
                alpha=0.8,
                elinewidth=0.8,
                capsize=2.0,
            )
        else:
            ax1.plot(doppler_times, doppler_y, color="black", linewidth=1.0)
            ax1.scatter(doppler_times, doppler_y, s=10, c="black", alpha=0.7, linewidths=0.0)
    if predicted_doppler_times and predicted_doppler_hz is not None:
        ax1.plot(
            predicted_doppler_times,
            predicted_doppler_hz + doppler_offset_hz,
            color="tab:orange",
            linewidth=1.8,
            alpha=0.95,
            label=f"Predicted + {doppler_offset_hz:+.1f} Hz",
            zorder=5,
        )
        ax1.legend(loc="best", fontsize=12, framealpha=0.85)
    ax1.axhline(0.0, color="gray", linewidth=0.8, alpha=0.6)
    ax1.set_ylabel("Doppler (Hz)", fontsize=font_size)
    ax1.set_xlabel("UTC time", fontsize=font_size)
    ax1.xaxis_date()
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    ax1.grid(True, which="both", alpha=0.3)

    ax0.tick_params(labelsize=font_size)
    ax1.tick_params(labelsize=font_size)
    fig.autofmt_xdate()
    fig.subplots_adjust(left=0.08, right=0.92, top=0.92, bottom=0.12, hspace=0.14, wspace=0.18)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print(f"Wrote {path}")
    return path


def iter_blocks(
    reader: drf.DigitalRFReader,
    channel: str,
    start: int,
    end: int,
    block_samples: int,
) -> Iterable[Tuple[int, np.ndarray]]:
    cursor = start
    while cursor <= end:
        count = min(block_samples, end - cursor + 1)
        try:
            data = reader.read_vector_1d(cursor, int(count), channel)
        except OSError:
            data = np.zeros(int(count), dtype=np.complex64)
        if data is None:
            data = np.zeros(int(count), dtype=np.complex64)
        yield cursor, data.astype(np.complex64, copy=False)
        cursor += count


def main() -> None:
    args = parse_args()
    input_root = args.dataset_root.expanduser()
    reader = drf.DigitalRFReader(str(input_root))
    props = reader.get_properties(args.channel)
    fs_in = float(props["samples_per_second"])
    raw_center = float(props["center_frequency_hz"]) if args.raw_center_hz is None else float(args.raw_center_hz)
    start, end = reader.get_bounds(args.channel)
    if args.start_seconds > 0:
        start += int(round(args.start_seconds * fs_in))
    if args.seconds is not None:
        end = min(end, start + int(round(args.seconds * fs_in)) - 1)
    if args.end_seconds > 0:
        end -= int(round(args.end_seconds * fs_in))
    if start > end:
        raise ValueError("Requested time span is empty.")

    epoch = epoch_to_datetime(props["epoch"])
    start_time = epoch + timedelta(seconds=start / fs_in) + timedelta(seconds=args.time_offset_seconds)

    block_samples = int(round(args.block_seconds * fs_in))
    if block_samples < 1:
        raise ValueError("block_seconds too small for the input rate.")

    total_samples = end - start + 1
    total_seconds = total_samples / fs_in
    total_blocks = int(math.ceil(total_samples / block_samples))
    start_wall = time.monotonic()
    print(
        f"Processing {total_seconds:.1f} s in {total_blocks} blocks from {input_root}.",
        flush=True,
    )

    desired_channel_rate = fs_in if args.channel_rate is None else float(args.channel_rate)
    decim = int(round(fs_in / desired_channel_rate))
    if decim < 1:
        decim = 1
    if decim > 1 and abs(fs_in / decim - desired_channel_rate) > 1e-3:
        raise ValueError(f"Cannot reach channel_rate={desired_channel_rate} from fs_in={fs_in}.")
    channel_rate = fs_in / decim

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

    mix_hz = raw_center - args.target_hz
    phase_step = -2.0 * math.pi * mix_hz / fs_in
    phase = 0.0

    chan_cursor = 0
    hits: List[TickHit] = []
    range_rows_raw: List[np.ndarray] = []
    range_row_times: List[datetime] = []
    doppler_times: List[datetime] = []
    doppler_values: List[float] = []

    blocks_done = 0
    for cursor, block in iter_blocks(reader, args.channel, start, end, block_samples):
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
        if carrier_filt.size > 1:
            phasor = np.conj(carrier_filt[:-1]) * carrier_filt[1:]
            phasor_sum = np.sum(phasor)
            if np.abs(phasor_sum) > 0:
                doppler = float(np.angle(phasor_sum) * channel_rate / (2.0 * math.pi))
                mid_time = start_time + timedelta(seconds=(cursor - start + (block_count / 2.0)) / fs_in)
                doppler_times.append(mid_time)
                doppler_values.append(doppler)

        env = np.abs(stage2).astype(np.float32, copy=False)
        env_bp, bp_zi = signal.lfilter(bp_taps, [1.0], env, zi=bp_zi)

        corr_sin = signal.correlate(env_bp, tpl_sin, mode="valid")
        corr_cos = signal.correlate(env_bp, tpl_cos, mode="valid")
        corr_block = np.sqrt(corr_sin**2 + corr_cos**2)
        if bp_delay > 0 and corr_block.size > bp_delay:
            corr_block = corr_block[bp_delay:]
        range_rows_raw.append(corr_block.astype(np.float32, copy=False))
        block_time = start_time + timedelta(seconds=(cursor - start) / fs_in)
        range_row_times.append(block_time)

        search = np.concatenate([prev_tail, env_bp])
        corr_sin = signal.correlate(search, tpl_sin, mode="valid")
        corr_cos = signal.correlate(search, tpl_cos, mode="valid")
        corr_mag = np.sqrt(corr_sin**2 + corr_cos**2)
        corr_centered = corr_mag - np.median(corr_mag)
        sigma = robust_sigma(corr_centered)
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
            range_km = (lag_index / channel_rate) * C_KM_PER_S if lag_index >= 0 else None

            seg_start = int(p)
            seg_stop = seg_start + tpl_len
            if seg_stop <= search.size:
                tone_seg = search[seg_start:seg_stop]
                freq_hz = estimate_freq_hz(tone_seg, channel_rate)
            else:
                freq_hz = None

            tick_time = start_time + timedelta(seconds=leading_sample / channel_rate)
            hits.append(
                TickHit(
                    score=float(corr_centered[p]),
                    sample_chan=leading_sample,
                    time_utc=tick_time,
                    freq_hz=freq_hz,
                    range_km=range_km,
                )
            )

        prev_tail = search[-overlap:] if overlap > 0 else np.zeros(0, dtype=np.float32)
        chan_cursor += env_bp.size

        blocks_done += 1
        processed_samples = (cursor - start) + block_count
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

    predicted_range_times: Optional[List[datetime]] = None
    predicted_range_km: Optional[np.ndarray] = None
    predicted_doppler_times: Optional[List[datetime]] = None
    predicted_doppler_hz: Optional[np.ndarray] = None
    range_offset_km = 0.0
    doppler_offset_hz = 0.0
    if args.tle_file is not None:
        sat = load_tle(args.tle_file.expanduser())
        tx_ecef = geodetic_to_ecef(args.tx_lat_deg, args.tx_lon_deg, args.tx_alt_m)
        carrier_hz = float(args.prediction_carrier_hz) if args.prediction_carrier_hz is not None else float(args.target_hz)

        hit_times = [h.time_utc for h in hits if h.range_km is not None]
        if hit_times:
            hit_unix = np.array([datetime_to_unix_seconds(t) for t in hit_times], dtype=np.float64)
            pred_delay_s, _ = predict_delay_doppler(sat, hit_unix, tx_ecef, carrier_hz)
            pred_range_km = pred_delay_s * C_KM_PER_S
            obs_range_km = np.array([h.range_km for h in hits if h.range_km is not None], dtype=np.float64)
            if args.range_offset_km is None:
                visible_mask = (obs_range_km >= args.range_min_km) & (obs_range_km <= args.range_max_km)
                if np.any(visible_mask):
                    range_offset_km = fit_constant_offset(obs_range_km[visible_mask], pred_range_km[visible_mask])
                else:
                    range_offset_km = fit_constant_offset(obs_range_km, pred_range_km)
            else:
                range_offset_km = float(args.range_offset_km)
            predicted_range_times = range_row_times
            range_row_unix = np.array([datetime_to_unix_seconds(t) for t in range_row_times], dtype=np.float64)
            row_delay_s, _ = predict_delay_doppler(sat, range_row_unix, tx_ecef, carrier_hz)
            predicted_range_km = row_delay_s * C_KM_PER_S

        if doppler_times and doppler_values:
            doppler_unix = np.array([datetime_to_unix_seconds(t) for t in doppler_times], dtype=np.float64)
            _, pred_doppler_hz = predict_delay_doppler(sat, doppler_unix, tx_ecef, carrier_hz)
            obs_doppler_hz = np.asarray(doppler_values, dtype=np.float64)
            if args.doppler_offset_hz is None:
                doppler_offset_hz = fit_constant_offset(obs_doppler_hz, pred_doppler_hz)
            else:
                doppler_offset_hz = float(args.doppler_offset_hz)
            predicted_doppler_times = doppler_times
            predicted_doppler_hz = pred_doppler_hz

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
    if not args.no_range_plot and range_rows_raw:
        global_sigma = robust_sigma(np.concatenate(range_rows_raw))
        range_rows = [row / (global_sigma + 1e-12) for row in range_rows_raw]
        plot_range_time(
            range_rows,
            range_row_times,
            channel_rate,
            args.range_plot_file,
            args.range_min_km,
            args.range_max_km,
            hits,
            doppler_times,
            doppler_values,
            predicted_range_times=predicted_range_times,
            predicted_range_km=predicted_range_km,
            predicted_doppler_times=predicted_doppler_times,
            predicted_doppler_hz=predicted_doppler_hz,
            range_offset_km=range_offset_km,
            doppler_offset_hz=doppler_offset_hz,
        )


if __name__ == "__main__":
    main()
