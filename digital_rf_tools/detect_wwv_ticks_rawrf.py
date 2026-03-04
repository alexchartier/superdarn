#!/usr/bin/env python3
"""
Detect WWV 1 kHz tick leading edges from rawrf HDF5 recordings.

Adapts detect_wwv_ticks.py (DigitalRF) to the SuperDARN rawrf HDF5 layout:
  /<group>/rawrf_data with shape (nseq, nchan, nsamp) and complex64 samples.

Pipeline:
1) Mix raw IQ to target frequency.
2) Decimate to channel_rate with lowpass (channel_lf_hz).
3) Envelope detect, bandpass 600-1400 Hz.
4) Matched filter 5-cycle 1 kHz tick to find leading edges.
5) Estimate tone frequency per tick via phase slope on the bandpassed segment.
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
from typing import Iterable, List, Optional, Tuple

import h5py
import numpy as np
from scipy import signal

os.environ.setdefault("MPLBACKEND", "Agg")

DEFAULT_INPUT = Path("/project/superdarn/data/rawrf/20260212.2005.21.wal.rawrf.h5")
DEFAULT_CHANNEL = 7
DEFAULT_TARGET_HZ = 15_000_000.0
DEFAULT_BLOCK_SECONDS = 1.0
DEFAULT_CHANNEL_RATE = 50_000.0
DEFAULT_CHANNEL_LP_HZ = 10_000.0
DEFAULT_CHANNEL_TRANSITION_HZ = 3_000.0
DEFAULT_BP_LOW_HZ = 600.0
DEFAULT_BP_HIGH_HZ = 1400.0
DEFAULT_BP_TRANSITION_HZ = 200.0
DEFAULT_TONE_HZ = 1000.0
DEFAULT_TONE_CYCLES = 5
DEFAULT_SIGMA_THRESHOLD = 6.0
DEFAULT_CARRIER_LP_HZ = 200.0
DEFAULT_START_SECONDS = 0.0
DEFAULT_SECONDS = 120.0
DEFAULT_OUTPUT_CSV = Path("wwv_tick_times_rawrf.csv")
DEFAULT_RANGE_PLOT = Path("wwv_range_time_rawrf.png")
DEFAULT_RANGE_MAX_KM = 5000.0

C_KM_PER_S = 299_792.458


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect WWV 1 kHz ticks from rawrf HDF5 recordings.")
    p.add_argument("--input-h5", type=Path, default=DEFAULT_INPUT, help=f"Input HDF5 path. Default: {DEFAULT_INPUT}.")
    p.add_argument("--channel", type=int, default=DEFAULT_CHANNEL, help=f"Channel index. Default: {DEFAULT_CHANNEL}.")
    p.add_argument(
        "--sample-rate-hz",
        type=float,
        default=None,
        help="Sample rate in Hz. Default: infer from rx_sample_rate.",
    )
    p.add_argument(
        "--center-freq-khz",
        type=float,
        default=None,
        help="Center frequency in kHz. Default: infer from rx_center_freq.",
    )
    p.add_argument(
        "--target-hz",
        type=float,
        default=DEFAULT_TARGET_HZ,
        help=f"Target carrier (Hz). Default: {DEFAULT_TARGET_HZ:g}.",
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
        help=f"Intermediate rate after decimation (Hz). Default: {DEFAULT_CHANNEL_RATE:g}.",
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
        "--seconds",
        type=float,
        default=DEFAULT_SECONDS,
        help=f"Process only this many seconds. Default: {DEFAULT_SECONDS:g}.",
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
        default=DEFAULT_OUTPUT_CSV,
        help=f"Output CSV path. Default: {DEFAULT_OUTPUT_CSV}.",
    )
    p.add_argument(
        "--range-plot-file",
        type=Path,
        default=DEFAULT_RANGE_PLOT,
        help=f"Range-time-intensity plot path. Default: {DEFAULT_RANGE_PLOT}.",
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


def estimate_freq_hz(x: np.ndarray, fs: float) -> Optional[float]:
    if x.size < 4:
        return None
    analytic = signal.hilbert(x)
    phase = np.unwrap(np.angle(analytic))
    t = np.arange(x.size, dtype=np.float64) / fs
    slope, _ = np.polyfit(t, phase, 1)
    return float(slope / (2.0 * math.pi))


def plot_range_time(
    range_rows: List[np.ndarray],
    block_times: List[datetime],
    fs: float,
    path: Path,
    range_max_km: float,
    hits: Optional[List["TickHit"]] = None,
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
    fig = plt.figure(figsize=(10, 8))
    ax0 = fig.add_subplot(1, 1, 1)
    cf = ax0.pcolormesh(
        x_nums,
        virtual_range_km,
        data,
        shading="nearest",
        cmap="viridis",
        antialiased=False,
        linewidth=0.0,
    )
    ax0.set_title("Matched filter output vs. virtual range", fontsize=title_size, fontweight="bold")
    ax0.set_ylabel("Virtual range (km)", fontsize=font_size)
    ax0.xaxis_date()
    ax0.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    ax0.set_ylim(0.0, range_max_km)
    if hits:
        times = [h.time_utc for h in hits if h.time_utc is not None and h.range_km is not None]
        ranges = [h.range_km for h in hits if h.time_utc is not None and h.range_km is not None]
        if times:
            ax0.scatter(times, ranges, s=10, c="red", alpha=0.8, linewidths=0.0)
    cbar = fig.colorbar(cf, ax=ax0, label="Matched filter score (sigma units)")
    cbar.ax.tick_params(labelsize=font_size)
    cbar.set_label("Matched filter score (sigma units)", fontsize=font_size)

    ax0.tick_params(labelsize=font_size)
    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    print(f"Wrote {path}")
    return path


def _parse_group_time(name: str) -> Optional[datetime]:
    # Expected format: YYYYMMDD-HHMM-SS.micro (e.g., 20260212-2033-35.300000)
    m = re.match(r"^(\d{8})-(\d{2})(\d{2})-(\d{2})\.(\d{6})$", name)
    if not m:
        return None
    ymd, hh, mm, ss, usec = m.groups()
    try:
        dt = datetime(
            int(ymd[0:4]),
            int(ymd[4:6]),
            int(ymd[6:8]),
            int(hh),
            int(mm),
            int(ss),
            int(usec),
            tzinfo=timezone.utc,
        )
        return dt
    except Exception:
        return None


def _find_attr(ds: h5py.Dataset, group: h5py.Group, keys: List[str]) -> Optional[float]:
    for k in keys:
        if k in ds.attrs:
            try:
                return float(ds.attrs[k])
            except Exception:
                continue
        if k in group.attrs:
            try:
                return float(group.attrs[k])
            except Exception:
                continue
    return None


def iter_blocks_h5(
    h5: h5py.File,
    groups: List[str],
    channel: int,
    block_samples: int,
    skip_samples: int,
    max_samples: Optional[int],
) -> Iterable[Tuple[int, np.ndarray]]:
    buf_list: List[np.ndarray] = []
    buf_len = 0
    produced = 0
    raw_cursor = 0

    for gname in groups:
        g = h5[gname]
        ds = g["rawrf_data"]
        for s in range(ds.shape[0]):
            x = ds[s, channel, :].astype(np.complex64, copy=False)
            if skip_samples > 0:
                if x.size <= skip_samples:
                    skip_samples -= x.size
                    raw_cursor += x.size
                    continue
                x = x[skip_samples:]
                raw_cursor += skip_samples
                skip_samples = 0

            buf_list.append(x)
            buf_len += x.size

            while buf_len >= block_samples:
                if len(buf_list) == 1:
                    buf = buf_list[0]
                else:
                    buf = np.concatenate(buf_list)
                block = buf[:block_samples]
                remainder = buf[block_samples:]
                buf_list = [remainder] if remainder.size else []
                buf_len = remainder.size

                yield raw_cursor, block
                raw_cursor += block_samples
                produced += block_samples
                if max_samples is not None and produced >= max_samples:
                    return

    if buf_len > 0 and (max_samples is None or produced < max_samples):
        if len(buf_list) == 1:
            buf = buf_list[0]
        else:
            buf = np.concatenate(buf_list)
        yield raw_cursor, buf


@dataclass
class TickHit:
    score: float
    sample_chan: int
    time_utc: Optional[datetime]
    freq_hz: Optional[float]
    range_km: Optional[float]


def main() -> None:
    args = parse_args()
    input_path = args.input_h5.expanduser()
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    with h5py.File(input_path, "r") as h5:
        groups = [k for k in sorted(h5.keys()) if isinstance(h5[k], h5py.Group) and "rawrf_data" in h5[k]]
        if not groups:
            raise RuntimeError("No groups with rawrf_data found.")

        # infer sample rate and center freq
        g0 = h5[groups[0]]
        ds0 = g0["rawrf_data"]
        fs_in = args.sample_rate_hz or _find_attr(ds0, g0, ["rx_sample_rate", "sample_rate_hz", "sample_rate"])
        if fs_in is None:
            raise RuntimeError("Sample rate not found. Use --sample-rate-hz.")
        fs_in = float(fs_in)

        center_khz = args.center_freq_khz or _find_attr(ds0, g0, ["rx_center_freq", "center_freq_khz", "center_freq"])
        if center_khz is None:
            raise RuntimeError("Center frequency not found. Use --center-freq-khz.")
        center_hz = float(center_khz) * 1000.0

        # estimate total samples quickly from shapes
        total_samples = 0
        for gname in groups:
            ds = h5[gname]["rawrf_data"]
            total_samples += ds.shape[0] * ds.shape[2]

        skip_samples = int(round(args.start_seconds * fs_in))
        max_samples = int(round(args.seconds * fs_in)) if args.seconds is not None else None

        # base time from group name if possible
        base_time = _parse_group_time(groups[0])
        if base_time is not None and skip_samples > 0:
            base_time = base_time + timedelta(seconds=skip_samples / fs_in)
        if base_time is not None and args.time_offset_seconds != 0.0:
            base_time = base_time + timedelta(seconds=args.time_offset_seconds)

        block_samples = int(round(args.block_seconds * fs_in))
        if block_samples < 1:
            raise ValueError("block_seconds too small for the input rate.")

        total_samples_proc = total_samples - skip_samples
        if max_samples is not None:
            total_samples_proc = min(total_samples_proc, max_samples)
        total_seconds = total_samples_proc / fs_in
        total_blocks = int(math.ceil(total_samples_proc / block_samples)) if total_samples_proc > 0 else 0
        start_wall = time.monotonic()

        print(
            f"Processing {total_seconds:.1f} s in {total_blocks} blocks from {input_path}.",
            flush=True,
        )

        decim = int(round(fs_in / args.channel_rate))
        if decim < 1 or abs(fs_in / decim - args.channel_rate) > 1e-3:
            raise ValueError(f"Cannot reach channel_rate={args.channel_rate} from fs_in={fs_in}.")
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

        mix_hz = center_hz - args.target_hz
        phase_step = -2.0 * math.pi * mix_hz / fs_in
        phase = 0.0

        chan_cursor = 0
        hits: List[TickHit] = []
        range_rows_raw: List[np.ndarray] = []
        range_row_times: List[datetime] = []

        blocks_done = 0
        for raw_cursor, block in iter_blocks_h5(
            h5,
            groups,
            args.channel,
            block_samples,
            skip_samples,
            max_samples,
        ):
            block_count = block.size
            if block.size == 0:
                continue
            if block.size < block_samples:
                pad = np.zeros(block_samples - block.size, dtype=np.complex64)
                block = np.concatenate([block, pad])

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
                    _ = float(np.angle(phasor_sum) * channel_rate / (2.0 * math.pi))

            env = np.abs(stage2).astype(np.float32, copy=False)
            env_bp, bp_zi = signal.lfilter(bp_taps, [1.0], env, zi=bp_zi)

            corr_sin = signal.correlate(env_bp, tpl_sin, mode="valid")
            corr_cos = signal.correlate(env_bp, tpl_cos, mode="valid")
            corr_block = np.sqrt(corr_sin**2 + corr_cos**2)
            if bp_delay > 0 and corr_block.size > bp_delay:
                corr_block = corr_block[bp_delay:]
            range_rows_raw.append(corr_block.astype(np.float32, copy=False))
            if base_time is not None:
                block_time = base_time + timedelta(seconds=raw_cursor / fs_in)
            else:
                block_time = datetime.fromtimestamp(0, tz=timezone.utc) + timedelta(seconds=raw_cursor / fs_in)
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

                tick_time = None
                if base_time is not None:
                    tick_time = base_time + timedelta(seconds=leading_sample / channel_rate)

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
            processed_samples = min(raw_cursor + block_count, total_samples_proc)
            processed_seconds = processed_samples / fs_in
            pct = 100.0 * processed_samples / total_samples_proc if total_samples_proc > 0 else 100.0
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

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["utc_time", "sample_index", "freq_hz", "range_km", "score"])
        for hit in hits:
            writer.writerow(
                [
                    "" if hit.time_utc is None else hit.time_utc.isoformat(),
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
            args.range_max_km,
            hits,
        )


if __name__ == "__main__":
    main()
