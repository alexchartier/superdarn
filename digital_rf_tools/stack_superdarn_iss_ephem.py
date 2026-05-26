#!/usr/bin/env python3
"""
De-dopplerize and de-lag a SuperDARN downrange recording using an ISS TLE,
then fold and matched-filter the corrected PRI frames.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy import signal
from sgp4.api import Satrec, jday

try:
    from drf_compat import open_drf_like_reader
except ImportError:  # pragma: no cover
    from digital_rf_tools.drf_compat import open_drf_like_reader


SEQUENCES = {
    "7p": {
        "pulse_sequence": [0, 9, 12, 20, 22, 26, 27],
        "tau_us": 2400.0,
        "pulse_len_us": 300.0,
        "pri_s": 0.1,
    },
    "8p": {
        "pulse_sequence": [0, 14, 22, 24, 27, 31, 42, 43],
        "tau_us": 1500.0,
        "pulse_len_us": 300.0,
        "pri_s": 0.1,
    },
}

DECIM_FIR_TAPS = 161
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
C_MPS = 299_792_458.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ephemeris-based ISS downrange SuperDARN restacker.")
    p.add_argument("--dataset-root", type=Path, required=True, help="DigitalRF dataset root or channel directory.")
    p.add_argument("--channel", default=None, help="Channel name. Default: inferred.")
    p.add_argument("--center-hz", type=float, default=None, help="Dataset center frequency in Hz. Default: metadata.")
    p.add_argument("--target-hz", type=float, default=None, help="Carrier to mix to baseband in Hz. Default: center-hz.")
    p.add_argument("--tle-file", type=Path, required=True, help="TLE file for ISS.")
    p.add_argument("--sequence", choices=sorted(SEQUENCES), default="7p", help="Pulse sequence template.")
    p.add_argument("--radar-lat-deg", type=float, default=37.85730, help="Wallops radar latitude in degrees.")
    p.add_argument("--radar-lon-deg", type=float, default=-75.51019, help="Wallops radar longitude in degrees.")
    p.add_argument("--radar-alt-m", type=float, default=50.0, help="Wallops radar altitude in meters.")
    p.add_argument("--skip-seconds", type=float, default=0.0, help="Seconds to skip from dataset start.")
    p.add_argument("--seconds", type=float, default=100.0, help="Seconds to analyze.")
    p.add_argument("--channel-lp-hz", type=float, default=5000.0, help="Lowpass cutoff after mixing in Hz.")
    p.add_argument("--decimated-rate", type=float, default=100000.0, help="Post-filter sample rate in Hz.")
    p.add_argument("--raw-chunk-seconds", type=float, default=2.0, help="Raw read chunk size in seconds.")
    p.add_argument("--residual-span-hz", type=float, default=50.0, help="Residual frequency half-span after ephemeris correction in Hz.")
    p.add_argument("--residual-step-hz", type=float, default=2.0, help="Residual frequency step after ephemeris correction in Hz.")
    p.add_argument("--residual-lag-span-ms", type=float, default=4.0, help="Residual lag half-span after ephemeris correction in ms.")
    p.add_argument("--average-pris", type=int, default=32, help="Average this many consecutive PRI rows.")
    p.add_argument("--output-prefix", type=Path, required=True, help="Prefix for PNG and JSON outputs.")
    return p.parse_args()


def _center_hz_from_properties(props: dict[str, object]) -> float | None:
    for key in ("center_frequency_hz", "center_frequency", "center_freq_hz", "cf_hz"):
        value = props.get(key)
        if value not in (None, ""):
            return float(value)
    return None


def load_tle(path: Path) -> Satrec:
    lines = [line.rstrip() for line in path.read_text().splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"TLE file {path} does not contain two lines.")
    if lines[0].startswith("1 "):
        line1, line2 = lines[0], lines[1]
    else:
        line1, line2 = lines[1], lines[2]
    return Satrec.twoline2rv(line1, line2)


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_m: float) -> np.ndarray:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * math.sin(lat) ** 2)
    return np.array(
        [
            (n + alt_m) * math.cos(lat) * math.cos(lon),
            (n + alt_m) * math.cos(lat) * math.sin(lon),
            ((1.0 - WGS84_E2) * n + alt_m) * math.sin(lat),
        ],
        dtype=np.float64,
    )


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
    return np.array(
        [
            c * r_m[0] + s * r_m[1],
            -s * r_m[0] + c * r_m[1],
            r_m[2],
        ],
        dtype=np.float64,
    )


def sat_ecef_at_unix(sat: Satrec, unix_time_s: float) -> np.ndarray:
    jd = unix_time_s / 86400.0 + 2440587.5
    jd0 = math.floor(jd)
    fr = jd - jd0
    e, r_km, _v_km_s = sat.sgp4(jd0, fr)
    if e != 0:
        raise RuntimeError(f"SGP4 propagation failed with code {e} at unix time {unix_time_s}.")
    return teme_to_ecef(np.asarray(r_km), jd)


def predict_delay_doppler(
    sat: Satrec,
    frame_times_s: np.ndarray,
    radar_ecef_m: np.ndarray,
    freq_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    delays_s = np.zeros(frame_times_s.size, dtype=np.float64)
    dopplers_hz = np.zeros(frame_times_s.size, dtype=np.float64)
    dt = 0.5
    for i, ts in enumerate(frame_times_s):
        p0 = sat_ecef_at_unix(sat, ts)
        pm = sat_ecef_at_unix(sat, ts - dt)
        pp = sat_ecef_at_unix(sat, ts + dt)
        r0 = float(np.linalg.norm(p0 - radar_ecef_m))
        rm = float(np.linalg.norm(pm - radar_ecef_m))
        rp = float(np.linalg.norm(pp - radar_ecef_m))
        range_rate = (rp - rm) / (2.0 * dt)
        delays_s[i] = r0 / C_MPS
        dopplers_hz[i] = -freq_hz * range_rate / C_MPS
    return delays_s, dopplers_hz


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
    raw_chunk_seconds: float,
) -> np.ndarray:
    decim = int(round(fs_in / fs_out))
    if not math.isclose(fs_in / fs_out, decim, rel_tol=0.0, abs_tol=1e-9):
        raise RuntimeError("decimated-rate must divide input sample rate exactly.")

    chunk_samples = max(int(round(raw_chunk_seconds * fs_in)), decim)
    taps = signal.firwin(DECIM_FIR_TAPS, lp_hz, fs=fs_in).astype(np.float32)
    zi = np.zeros(taps.size - 1, dtype=np.complex64)
    mix_hz = target_hz - center_hz
    phase = 0.0
    phase_step = -2.0 * math.pi * mix_hz / fs_in
    decim_offset = 0
    cursor = start_sample
    stop_sample = start_sample + total_samples
    pieces: list[np.ndarray] = []

    while cursor < stop_sample:
        take = min(chunk_samples, stop_sample - cursor)
        chunk = reader.read_vector_1d(cursor, take, channel).astype(np.complex64, copy=False)
        chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.0, neginf=0.0)

        n = np.arange(chunk.size, dtype=np.float64)
        mixer = np.exp(1j * (phase + phase_step * n)).astype(np.complex64)
        mixed = chunk * mixer
        phase = (phase + phase_step * chunk.size) % (2.0 * math.pi)

        filt, zi = signal.lfilter(taps, [1.0], mixed, zi=zi)
        out = filt[decim_offset::decim]
        decim_offset = (decim_offset - filt.size) % decim
        if out.size:
            pieces.append(out.astype(np.complex64, copy=False))
        cursor += take

    if not pieces:
        return np.array([], dtype=np.complex64)
    return np.concatenate(pieces)


def frame_pris(
    y: np.ndarray,
    fs_hz: float,
    start_sample_raw: int,
    fs_in: float,
    pri_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    pri_samples = int(round(pri_s * fs_hz))
    decim = int(round(fs_in / fs_hz))
    group_delay_dec = ((DECIM_FIR_TAPS - 1) // 2) // decim
    start_sample_dec = start_sample_raw // decim + group_delay_dec
    frame_offset = (-start_sample_dec) % pri_samples
    first_frame_start_dec = start_sample_dec + frame_offset
    usable = y[frame_offset:]
    pri_count = usable.size // pri_samples
    frames = usable[: pri_count * pri_samples].reshape(pri_count, pri_samples)
    frame_start_times_s = (first_frame_start_dec + np.arange(pri_count) * pri_samples) / fs_hz
    return frames, frame_start_times_s


def fractional_advance(frame: np.ndarray, shift_samples: float) -> np.ndarray:
    n = np.arange(frame.size, dtype=np.float64)
    x = n + shift_samples
    real = np.interp(x, n, frame.real, left=0.0, right=0.0)
    imag = np.interp(x, n, frame.imag, left=0.0, right=0.0)
    return (real + 1j * imag).astype(np.complex64, copy=False)


def correct_frames(
    frames: np.ndarray,
    fs_hz: float,
    delays_s: np.ndarray,
    dopplers_hz: np.ndarray,
) -> np.ndarray:
    corrected = np.zeros_like(frames, dtype=np.complex64)
    t = np.arange(frames.shape[1], dtype=np.float64) / fs_hz
    for i in range(frames.shape[0]):
        phase = np.exp(-2j * np.pi * dopplers_hz[i] * t).astype(np.complex64)
        dedopp = frames[i] * phase
        corrected[i] = fractional_advance(dedopp, delays_s[i] * fs_hz)
    return corrected


def template_metadata(cfg: dict[str, object], fs_hz: float) -> tuple[np.ndarray, int]:
    pulse_samples = int(round(float(cfg["pulse_len_us"]) * 1e-6 * fs_hz))
    offsets = np.round(np.asarray(cfg["pulse_sequence"], dtype=np.float64) * float(cfg["tau_us"]) * 1e-6 * fs_hz).astype(int)
    return offsets, pulse_samples


def matched_corr(frames: np.ndarray, offsets: np.ndarray, pulse_samples: int) -> np.ndarray:
    pri_samples = frames.shape[1]
    template_span = int(offsets[-1] + pulse_samples)
    valid_lags = pri_samples - template_span + 1
    if valid_lags <= 0:
        raise RuntimeError("PRI is shorter than pulse template.")
    cs = np.concatenate(
        [np.zeros((frames.shape[0], 1), dtype=np.complex64), np.cumsum(frames, axis=1, dtype=np.complex64)],
        axis=1,
    )
    corr = np.zeros((frames.shape[0], valid_lags), dtype=np.complex64)
    for i, lag in enumerate(range(valid_lags)):
        series = np.zeros(frames.shape[0], dtype=np.complex64)
        for off in offsets:
            lo = lag + off
            hi = lo + pulse_samples
            series += cs[:, hi] - cs[:, lo]
        corr[:, i] = series
    return corr


def search_residuals(
    frames: np.ndarray,
    fs_hz: float,
    offsets: np.ndarray,
    pulse_samples: int,
    residual_span_hz: float,
    residual_step_hz: float,
    residual_lag_span_ms: float,
) -> tuple[float, int]:
    pri_samples = frames.shape[1]
    lag_half = int(round(residual_lag_span_ms * 1e-3 * fs_hz))
    t = np.arange(pri_samples, dtype=np.float64) / fs_hz
    residuals = np.arange(-residual_span_hz, residual_span_hz + 0.5 * residual_step_hz, residual_step_hz, dtype=np.float64)
    best_score = -np.inf
    best_residual_hz = 0.0
    best_lag = 0
    for residual_hz in residuals:
        phase = np.exp(-2j * np.pi * residual_hz * t).astype(np.complex64)
        mixed = frames * phase[None, :]
        corr = matched_corr(mixed, offsets, pulse_samples)
        center = 0
        lo = max(0, center - lag_half)
        hi = min(corr.shape[1], center + lag_half + 1)
        local = np.abs(corr[:, lo:hi]) ** 2
        profile = local.mean(axis=0)
        idx = int(np.argmax(profile))
        score = float(profile[idx])
        if score > best_score:
            best_score = score
            best_residual_hz = float(residual_hz)
            best_lag = int(lo + idx)
    return best_residual_hz, best_lag


def average_rows(matrix: np.ndarray, average_pris: int) -> np.ndarray:
    if average_pris <= 1:
        return matrix
    usable = (matrix.shape[0] // average_pris) * average_pris
    if usable <= 0:
        raise RuntimeError("Not enough PRI rows for requested averaging.")
    return matrix[:usable].reshape(usable // average_pris, average_pris, matrix.shape[1]).mean(axis=1)


def plot_results(
    path: Path,
    power: np.ndarray,
    lag_ms: np.ndarray,
    best_lag_ms: float,
    residual_hz: float,
    delay_ms: np.ndarray,
    doppler_hz: np.ndarray,
    avg_pris: int,
    dataset_name: str | None = None,
    sequence_label: str | None = None,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    row_median = np.median(power, axis=1, keepdims=True)
    rel_db = 10.0 * np.log10(np.maximum(power, 1e-12) / np.maximum(row_median, 1e-12))
    profile_db = 10.0 * np.log10(np.maximum(power.mean(axis=0), 1e-12) / np.maximum(np.median(power.mean(axis=0)), 1e-12))

    vmin = float(np.percentile(rel_db, 10))
    vmax = float(np.percentile(rel_db, 99.5))

    fig, axes = plt.subplots(
        4,
        1,
        figsize=(12, 10),
        gridspec_kw={"height_ratios": [1, 1, 1, 5], "hspace": 0.08},
        sharex=False,
    )

    ax = axes[0]
    ax.plot(lag_ms, profile_db, lw=1.2, color="0.15")
    ax.axvline(best_lag_ms, color="tab:red", ls="--", lw=1.0)
    ax.set_ylabel("Mean MF\n(dB rel)")
    ax.grid(True, alpha=0.2)
    title = f"ISS ephemeris-corrected MF stack, residual {residual_hz:+.1f} Hz, avg {avg_pris} PRI"
    if dataset_name is not None or sequence_label is not None:
        extra = " ".join(part for part in [dataset_name, sequence_label] if part)
        title = f"{extra}: {title}" if extra else title
    ax.set_title(title)

    ax = axes[1]
    ax.plot(delay_ms, lw=1.0)
    ax.set_ylabel("Delay\n(ms)")
    ax.grid(True, alpha=0.2)

    ax = axes[2]
    ax.plot(doppler_hz, lw=1.0)
    ax.set_ylabel("Doppler\n(Hz)")
    ax.grid(True, alpha=0.2)

    ax = axes[3]
    extent = [float(lag_ms[0]), float(lag_ms[-1]), 0, power.shape[0]]
    im = ax.imshow(
        rel_db,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap="magma",
        vmin=vmin,
        vmax=vmax,
    )
    ax.axvline(best_lag_ms, color="cyan", ls="--", lw=1.0)
    ax.set_xlabel("Residual lag after ephemeris correction (ms)")
    ax.set_ylabel("PRI group index")
    fig.colorbar(im, ax=ax, pad=0.01, label="Matched-filter power / row median (dB)")

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    cfg = SEQUENCES[args.sequence]

    reader, channel, reader_mode = open_drf_like_reader(args.dataset_root, args.channel)
    if reader_mode != "digital_rf":
        print(f"Using flat Data/rf@*.h5 reader for channel {channel} under {args.dataset_root}")

    props = reader.get_properties(channel)
    fs_in = float(props["samples_per_second"])
    center_hz = float(args.center_hz) if args.center_hz is not None else _center_hz_from_properties(props)
    if center_hz is None:
        raise RuntimeError("Could not infer center frequency from channel properties. Supply --center-hz.")
    target_hz = center_hz if args.target_hz is None else float(args.target_hz)
    start_sample, stop_sample = reader.get_bounds(channel)
    start_sample += int(round(args.skip_seconds * fs_in))
    if start_sample > stop_sample:
        raise RuntimeError("Skip exceeds dataset length.")

    total_samples = int(round(args.seconds * fs_in))
    total_samples = min(total_samples, stop_sample - start_sample + 1)
    if total_samples <= 0:
        raise RuntimeError("No samples left to analyze.")

    sat = load_tle(args.tle_file)
    radar_ecef = geodetic_to_ecef(args.radar_lat_deg, args.radar_lon_deg, args.radar_alt_m)

    y = load_decimated_channel(
        reader,
        channel=channel,
        start_sample=start_sample,
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

    frames, frame_times_s = frame_pris(y, args.decimated_rate, start_sample, fs_in, float(cfg["pri_s"]))
    delay_s, doppler_hz = predict_delay_doppler(sat, frame_times_s, radar_ecef, target_hz)
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

    png_path = args.output_prefix.with_suffix(".png")
    json_path = args.output_prefix.with_suffix(".json")
    plot_results(
        png_path,
        power=power,
        lag_ms=lag_ms,
        best_lag_ms=best_lag_ms,
        residual_hz=residual_hz,
        delay_ms=delay_s * 1e3,
        doppler_hz=doppler_hz,
        avg_pris=args.average_pris,
    )

    result = {
        "dataset_root": str(args.dataset_root),
        "channel": channel,
        "center_hz": float(center_hz),
        "target_hz": float(target_hz),
        "sequence": args.sequence,
        "radar_lat_deg": float(args.radar_lat_deg),
        "radar_lon_deg": float(args.radar_lon_deg),
        "radar_alt_m": float(args.radar_alt_m),
        "seconds": float(total_samples / fs_in),
        "channel_lpf_hz": float(args.channel_lp_hz),
        "decimated_rate_hz": float(args.decimated_rate),
        "delay_ms_start": float(delay_s[0] * 1e3),
        "delay_ms_end": float(delay_s[-1] * 1e3),
        "doppler_hz_start": float(doppler_hz[0]),
        "doppler_hz_end": float(doppler_hz[-1]),
        "residual_hz": float(residual_hz),
        "best_residual_lag_ms": float(best_lag_ms),
        "average_pris": int(args.average_pris),
        "pri_groups": int(power.shape[0]),
        "reader_mode": reader_mode,
        "tle_file": str(args.tle_file),
    }
    json_path.write_text(json.dumps(result, indent=2))

    print(f"Saved plot: {png_path}")
    print(f"Saved summary: {json_path}")
    print(f"Predicted delay: {delay_s[0]*1e3:.3f} -> {delay_s[-1]*1e3:.3f} ms")
    print(f"Predicted doppler: {doppler_hz[0]:+.1f} -> {doppler_hz[-1]:+.1f} Hz")
    print(f"Residual correction: {residual_hz:+.1f} Hz, lag {best_lag_ms:.3f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
