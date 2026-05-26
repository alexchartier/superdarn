#!/usr/bin/env python3
"""Estimate SuperDARN-style tdiff from active calibration captures.

Supports:
- Multi-frequency discrete captures via a CSV manifest.
- Swept-frequency captures via a sweep-plan CSV and a single capture file.

The script fits unwrapped phase difference versus RF frequency:
    phase(f) = phase0 + 2*pi*f*tdiff
and reports tdiff from the fitted slope.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import numpy as np

try:
    import h5py
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"h5py is required for this script: {exc}")


MAIN_DATASET_HINTS = (
    "main_antennas_iq",
    "main_iq",
    "main_data",
    "main",
    "main_antenna_iq",
)
INTF_DATASET_HINTS = (
    "intf_antennas_iq",
    "intf_iq",
    "intf_data",
    "intf",
    "interferometer_antennas_iq",
)
SAMPLE_RATE_HINTS = (
    "sample_rate",
    "rx_sample_rate",
    "sampling_rate",
    "rate",
    "fs",
)


@dataclass
class CaptureSpec:
    freq_hz: float
    file_path: Path
    start_s: float | None
    duration_s: float | None
    tone_hz: float | None
    main_dataset: str | None
    intf_dataset: str | None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Estimate tdiff from multi-frequency/swept active calibration captures."
    )
    p.add_argument(
        "--manifest",
        type=Path,
        help=(
            "CSV for discrete captures with columns: "
            "freq_hz,file_path[,start_s,duration_s,tone_hz,main_dataset,intf_dataset]"
        ),
    )
    p.add_argument("--sweep-file", type=Path, help="Single HDF5 capture file for swept calibration.")
    p.add_argument(
        "--sweep-plan",
        type=Path,
        help="CSV for swept calibration with columns: freq_hz,start_s,duration_s[,tone_hz]",
    )

    p.add_argument("--main-dataset", type=str, default=None, help="Main-array dataset path in HDF5.")
    p.add_argument("--intf-dataset", type=str, default=None, help="Interferometer dataset path in HDF5.")
    p.add_argument("--sample-rate-hz", type=float, default=None, help="Override sample rate (Hz).")
    p.add_argument("--tone-hz", type=float, default=None, help="Known calibration tone offset (Hz, baseband).")
    p.add_argument("--channel-axis", type=int, default=None, help="Channel axis in dataset (auto by default).")
    p.add_argument("--max-samples", type=int, default=1_000_000, help="Max samples used per frequency point.")

    p.add_argument("--phase-method", choices=("refs", "array-mean"), default="refs")
    p.add_argument("--main-ref", type=int, default=0, help="Main reference channel index.")
    p.add_argument("--intf-ref", type=int, default=0, help="Intf reference channel index.")
    p.add_argument(
        "--main-use",
        type=str,
        default=None,
        help="Comma-separated main channel indices for array-mean mode.",
    )
    p.add_argument(
        "--intf-use",
        type=str,
        default=None,
        help="Comma-separated intf channel indices for array-mean mode.",
    )
    p.add_argument(
        "--amplitude-floor-db",
        type=float,
        default=-30.0,
        help="Reject channels below this relative amplitude floor (dB).",
    )
    p.add_argument(
        "--known-geom-delay-ns",
        type=float,
        default=0.0,
        help="Known geometric delay to subtract from fitted delay (ns).",
    )

    p.add_argument("--json-out", type=Path, default=Path("tdiff_estimate.json"))
    p.add_argument("--plot-out", type=Path, default=None, help="Optional phase-vs-frequency plot path.")
    p.add_argument("--verbose", action="store_true")

    args = p.parse_args()
    if not args.manifest and not (args.sweep_file and args.sweep_plan):
        p.error("Provide either --manifest or both --sweep-file and --sweep-plan.")
    return args


def parse_indices(text: str | None) -> list[int] | None:
    if text is None:
        return None
    vals = []
    for token in text.split(","):
        t = token.strip()
        if not t:
            continue
        vals.append(int(t))
    return vals


def iter_datasets(hf: h5py.File) -> Iterable[tuple[str, h5py.Dataset]]:
    def visitor(name: str, obj: object) -> None:
        if isinstance(obj, h5py.Dataset):
            out.append((name, obj))

    out: list[tuple[str, h5py.Dataset]] = []
    hf.visititems(visitor)
    return out


def find_dataset(hf: h5py.File, explicit: str | None, hints: Sequence[str]) -> str:
    if explicit:
        if explicit in hf:
            return explicit
        if explicit.startswith("/"):
            candidate = explicit[1:]
            if candidate in hf:
                return candidate
        raise ValueError(f"Dataset '{explicit}' not found in file.")

    all_ds = list(iter_datasets(hf))
    names = [name for name, _ in all_ds]
    for hint in hints:
        for name in names:
            lname = name.lower()
            if hint in lname and ("iq" in lname or "data" in lname):
                return name
        for name in names:
            if hint in name.lower():
                return name
    raise ValueError("Could not auto-detect dataset. Pass --main-dataset/--intf-dataset explicitly.")


def get_sample_rate(hf: h5py.File, ds: h5py.Dataset, override_hz: float | None) -> float:
    if override_hz:
        return float(override_hz)

    for key in SAMPLE_RATE_HINTS:
        if key in ds.attrs:
            return float(ds.attrs[key])
    for key in SAMPLE_RATE_HINTS:
        if key in hf.attrs:
            return float(hf.attrs[key])
    raise ValueError("Sample rate not found in attributes. Pass --sample-rate-hz.")


def ensure_complex(arr: np.ndarray) -> np.ndarray:
    if np.iscomplexobj(arr):
        return arr.astype(np.complex64, copy=False)
    if arr.ndim >= 1 and arr.shape[-1] == 2:
        return arr[..., 0].astype(np.float32) + 1j * arr[..., 1].astype(np.float32)
    raise ValueError("Dataset is not complex and not I/Q interleaved.")


def choose_channel_axis(shape: tuple[int, ...], explicit_axis: int | None) -> int:
    if explicit_axis is not None:
        axis = explicit_axis
        if axis < 0:
            axis += len(shape)
        if axis < 0 or axis >= len(shape):
            raise ValueError(f"Invalid channel axis {explicit_axis} for shape {shape}")
        return axis
    for axis, size in enumerate(shape):
        if 1 < size <= 64:
            return axis
    return 0


def normalize_channel_samples(arr: np.ndarray, channel_axis: int | None) -> np.ndarray:
    arr_c = ensure_complex(np.asarray(arr))
    if arr_c.ndim == 1:
        return arr_c.reshape(1, -1)
    axis = choose_channel_axis(arr_c.shape, channel_axis)
    moved = np.moveaxis(arr_c, axis, 0)
    return moved.reshape(moved.shape[0], -1)


def extract_segment(
    ch_by_sample: np.ndarray,
    sample_rate_hz: float,
    start_s: float | None,
    duration_s: float | None,
    max_samples: int,
) -> np.ndarray:
    n_total = ch_by_sample.shape[1]
    start = int(round((start_s or 0.0) * sample_rate_hz))
    start = max(0, min(start, n_total))
    if duration_s is None:
        stop = n_total
    else:
        stop = start + int(round(duration_s * sample_rate_hz))
    stop = max(start, min(stop, n_total))

    seg = ch_by_sample[:, start:stop]
    if seg.shape[1] > max_samples:
        seg = seg[:, :max_samples]
    return seg


def estimate_tone_hz(x: np.ndarray, sample_rate_hz: float) -> float:
    n = min(x.size, 1 << 19)
    if n < 256:
        return 0.0
    xw = x[:n] * np.hanning(n)
    spec = np.fft.fft(xw)
    freqs = np.fft.fftfreq(n, d=1.0 / sample_rate_hz)
    mag = np.abs(spec)
    # avoid DC dominating auto-detect
    dc_bin = np.argmin(np.abs(freqs))
    lo = max(0, dc_bin - 3)
    hi = min(mag.size, dc_bin + 4)
    mag[lo:hi] = 0.0
    idx = int(np.argmax(mag))
    return float(freqs[idx])


def tone_response(ch_by_sample: np.ndarray, sample_rate_hz: float, tone_hz: float) -> np.ndarray:
    n = ch_by_sample.shape[1]
    if n == 0:
        return np.zeros(ch_by_sample.shape[0], dtype=np.complex64)
    t = np.arange(n, dtype=np.float64) / sample_rate_hz
    ref = np.exp(-1j * 2.0 * math.pi * tone_hz * t).astype(np.complex64)
    return np.mean(ch_by_sample * ref[None, :], axis=1)


def parse_manifest(path: Path) -> list[CaptureSpec]:
    out: list[CaptureSpec] = []
    base = path.parent
    with path.open("r", newline="") as fh:
        reader = csv.DictReader(fh)
        needed = {"freq_hz", "file_path"}
        if not needed.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"Manifest needs columns {sorted(needed)}")
        for row in reader:
            file_path = Path(row["file_path"]).expanduser()
            if not file_path.is_absolute():
                file_path = (base / file_path).resolve()
            out.append(
                CaptureSpec(
                    freq_hz=float(row["freq_hz"]),
                    file_path=file_path,
                    start_s=float(row["start_s"]) if row.get("start_s") else None,
                    duration_s=float(row["duration_s"]) if row.get("duration_s") else None,
                    tone_hz=float(row["tone_hz"]) if row.get("tone_hz") else None,
                    main_dataset=row.get("main_dataset") or None,
                    intf_dataset=row.get("intf_dataset") or None,
                )
            )
    return out


def parse_sweep_plan(path: Path, sweep_file: Path) -> list[CaptureSpec]:
    out: list[CaptureSpec] = []
    with path.open("r", newline="") as fh:
        reader = csv.DictReader(fh)
        needed = {"freq_hz", "start_s", "duration_s"}
        if not needed.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"Sweep plan needs columns {sorted(needed)}")
        for row in reader:
            out.append(
                CaptureSpec(
                    freq_hz=float(row["freq_hz"]),
                    file_path=sweep_file.expanduser(),
                    start_s=float(row["start_s"]),
                    duration_s=float(row["duration_s"]),
                    tone_hz=float(row["tone_hz"]) if row.get("tone_hz") else None,
                    main_dataset=None,
                    intf_dataset=None,
                )
            )
    return out


def weighted_circular_mean(z: np.ndarray, w: np.ndarray | None = None) -> complex:
    if z.size == 0:
        return 0.0 + 0.0j
    nz = z / np.maximum(np.abs(z), 1e-12)
    if w is None:
        return complex(np.sum(nz))
    return complex(np.sum(nz * w))


def pick_channels(
    responses: np.ndarray,
    explicit: list[int] | None,
    amplitude_floor_db: float,
) -> np.ndarray:
    if responses.size == 0:
        return np.array([], dtype=np.int64)
    if explicit:
        return np.array([i for i in explicit if 0 <= i < responses.size], dtype=np.int64)
    amps = np.abs(responses)
    ref = np.max(amps) + 1e-12
    mask = 20.0 * np.log10((amps + 1e-12) / ref) >= amplitude_floor_db
    return np.where(mask)[0].astype(np.int64)


def calc_phase_point(
    main_resp: np.ndarray,
    intf_resp: np.ndarray,
    method: str,
    main_ref: int,
    intf_ref: int,
    main_use: list[int] | None,
    intf_use: list[int] | None,
    amplitude_floor_db: float,
) -> tuple[float, float, dict]:
    if method == "refs":
        if not (0 <= main_ref < main_resp.size):
            raise ValueError(f"main_ref {main_ref} out of range for {main_resp.size} channels")
        if not (0 <= intf_ref < intf_resp.size):
            raise ValueError(f"intf_ref {intf_ref} out of range for {intf_resp.size} channels")
        z = intf_resp[intf_ref] * np.conj(main_resp[main_ref])
        phase = float(np.angle(z))
        quality = float(min(np.abs(main_resp[main_ref]), np.abs(intf_resp[intf_ref])))
        meta = {"main_indices": [main_ref], "intf_indices": [intf_ref]}
        return phase, quality, meta

    mi = pick_channels(main_resp, main_use, amplitude_floor_db)
    ii = pick_channels(intf_resp, intf_use, amplitude_floor_db)
    if mi.size == 0 or ii.size == 0:
        raise ValueError("No valid channels after amplitude-floor filtering for array-mean mode.")

    mw = np.abs(main_resp[mi])
    iw = np.abs(intf_resp[ii])
    mmean = weighted_circular_mean(main_resp[mi], w=mw)
    imean = weighted_circular_mean(intf_resp[ii], w=iw)
    z = imean * np.conj(mmean)
    phase = float(np.angle(z))
    quality = float(min(np.abs(mmean), np.abs(imean)))
    meta = {"main_indices": mi.tolist(), "intf_indices": ii.tolist()}
    return phase, quality, meta


def fit_tdiff(freq_hz: np.ndarray, phase_rad: np.ndarray, weights: np.ndarray | None) -> dict:
    order = np.argsort(freq_hz)
    x = freq_hz[order]
    y_wrap = phase_rad[order]
    y = np.unwrap(y_wrap)

    if x.size < 2:
        raise ValueError("Need at least two frequency points for tdiff fit.")

    if weights is None:
        p = np.polyfit(x, y, deg=1)
    else:
        w = np.sqrt(np.maximum(weights[order], 1e-12))
        p = np.polyfit(x, y, deg=1, w=w)
    slope, intercept = float(p[0]), float(p[1])
    yhat = slope * x + intercept
    resid = y - yhat
    rmse = float(np.sqrt(np.mean(resid * resid)))
    ss_res = float(np.sum(resid * resid))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2)) + 1e-12
    r2 = float(1.0 - ss_res / ss_tot)
    tdiff_s = slope / (2.0 * math.pi)
    return {
        "freq_hz_sorted": x,
        "phase_wrapped_sorted_rad": y_wrap,
        "phase_unwrapped_sorted_rad": y,
        "slope_rad_per_hz": slope,
        "intercept_rad": intercept,
        "fit_rmse_rad": rmse,
        "fit_r2": r2,
        "tdiff_seconds": tdiff_s,
        "residuals_rad": resid,
    }


def maybe_plot(path: Path, fit: dict) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"matplotlib is required for plotting: {exc}")

    x = fit["freq_hz_sorted"]
    y_wrap = fit["phase_wrapped_sorted_rad"]
    y_unwrap = fit["phase_unwrapped_sorted_rad"]
    slope = fit["slope_rad_per_hz"]
    intercept = fit["intercept_rad"]
    yhat = slope * x + intercept

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(x / 1e6, y_wrap, label="wrapped phase", s=28)
    ax.scatter(x / 1e6, y_unwrap, label="unwrapped phase", s=28)
    ax.plot(x / 1e6, yhat, label="linear fit", linewidth=2.0)
    ax.set_xlabel("RF frequency (MHz)")
    ax.set_ylabel("Phase difference (rad)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def load_main_intf_segments(
    spec: CaptureSpec,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray, float, str, str]:
    with h5py.File(spec.file_path, "r") as hf:
        main_name = find_dataset(
            hf, spec.main_dataset or args.main_dataset, hints=MAIN_DATASET_HINTS
        )
        intf_name = find_dataset(
            hf, spec.intf_dataset or args.intf_dataset, hints=INTF_DATASET_HINTS
        )
        main_ds = hf[main_name]
        intf_ds = hf[intf_name]

        fs = get_sample_rate(hf, main_ds, args.sample_rate_hz)
        main = normalize_channel_samples(main_ds[...], channel_axis=args.channel_axis)
        intf = normalize_channel_samples(intf_ds[...], channel_axis=args.channel_axis)

    main_seg = extract_segment(
        main, fs, start_s=spec.start_s, duration_s=spec.duration_s, max_samples=args.max_samples
    )
    intf_seg = extract_segment(
        intf, fs, start_s=spec.start_s, duration_s=spec.duration_s, max_samples=args.max_samples
    )
    return main_seg, intf_seg, fs, main_name, intf_name


def main() -> None:
    args = parse_args()
    main_use = parse_indices(args.main_use)
    intf_use = parse_indices(args.intf_use)

    if args.manifest:
        captures = parse_manifest(args.manifest.expanduser())
    else:
        captures = parse_sweep_plan(args.sweep_plan.expanduser(), args.sweep_file.expanduser())

    results = []
    for idx, spec in enumerate(captures):
        if not spec.file_path.exists():
            raise FileNotFoundError(f"Capture file not found: {spec.file_path}")

        main_seg, intf_seg, fs, main_ds_name, intf_ds_name = load_main_intf_segments(spec, args)
        if main_seg.shape[1] == 0 or intf_seg.shape[1] == 0:
            raise ValueError(f"Empty segment for frequency {spec.freq_hz}")

        tone_hz = args.tone_hz
        if tone_hz is None:
            tone_hz = spec.tone_hz
        if tone_hz is None:
            ref_idx = args.main_ref
            if not (0 <= ref_idx < main_seg.shape[0]):
                ref_idx = 0
            tone_hz = estimate_tone_hz(main_seg[ref_idx], fs)

        main_resp = tone_response(main_seg, fs, tone_hz)
        intf_resp = tone_response(intf_seg, fs, tone_hz)

        phase, quality, meta = calc_phase_point(
            main_resp=main_resp,
            intf_resp=intf_resp,
            method=args.phase_method,
            main_ref=args.main_ref,
            intf_ref=args.intf_ref,
            main_use=main_use,
            intf_use=intf_use,
            amplitude_floor_db=args.amplitude_floor_db,
        )

        row = {
            "index": idx,
            "freq_hz": spec.freq_hz,
            "file_path": str(spec.file_path),
            "start_s": spec.start_s,
            "duration_s": spec.duration_s,
            "tone_hz_used": tone_hz,
            "sample_rate_hz": fs,
            "phase_rad": phase,
            "quality": quality,
            "main_dataset": main_ds_name,
            "intf_dataset": intf_ds_name,
        }
        row.update(meta)
        results.append(row)

        if args.verbose:
            print(
                f"[{idx:03d}] f={spec.freq_hz/1e6:.6f} MHz "
                f"tone={tone_hz:.1f} Hz phase={phase:+.4f} rad quality={quality:.3g}"
            )

    if len(results) < 2:
        raise SystemExit("Need at least 2 valid frequency points for tdiff fit.")

    freq = np.array([r["freq_hz"] for r in results], dtype=np.float64)
    phase = np.array([r["phase_rad"] for r in results], dtype=np.float64)
    qual = np.array([max(r["quality"], 1e-12) for r in results], dtype=np.float64)
    fit = fit_tdiff(freq_hz=freq, phase_rad=phase, weights=qual)

    tdiff_raw_s = float(fit["tdiff_seconds"])
    tdiff_geom_s = float(args.known_geom_delay_ns) * 1e-9
    tdiff_corrected_s = tdiff_raw_s - tdiff_geom_s

    out = {
        "n_points": len(results),
        "phase_method": args.phase_method,
        "main_ref": args.main_ref,
        "intf_ref": args.intf_ref,
        "known_geom_delay_ns": args.known_geom_delay_ns,
        "fit_rmse_rad": fit["fit_rmse_rad"],
        "fit_r2": fit["fit_r2"],
        "slope_rad_per_hz": fit["slope_rad_per_hz"],
        "intercept_rad": fit["intercept_rad"],
        "tdiff_raw_s": tdiff_raw_s,
        "tdiff_raw_ns": tdiff_raw_s * 1e9,
        "tdiff_corrected_s": tdiff_corrected_s,
        "tdiff_corrected_ns": tdiff_corrected_s * 1e9,
        "points": results,
        "fit_freq_hz_sorted": np.asarray(fit["freq_hz_sorted"]).tolist(),
        "fit_phase_wrapped_sorted_rad": np.asarray(fit["phase_wrapped_sorted_rad"]).tolist(),
        "fit_phase_unwrapped_sorted_rad": np.asarray(fit["phase_unwrapped_sorted_rad"]).tolist(),
        "fit_residuals_rad": np.asarray(fit["residuals_rad"]).tolist(),
    }

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(out, indent=2))
    print(f"Wrote: {args.json_out}")
    print(f"tdiff (raw):       {tdiff_raw_s * 1e9:.3f} ns")
    if args.known_geom_delay_ns != 0.0:
        print(f"tdiff (corrected): {tdiff_corrected_s * 1e9:.3f} ns")
    print(f"fit R^2={fit['fit_r2']:.5f}, RMSE={fit['fit_rmse_rad']:.4f} rad")

    if args.plot_out:
        maybe_plot(args.plot_out, fit=fit)
        print(f"Wrote plot: {args.plot_out}")


if __name__ == "__main__":
    main()
