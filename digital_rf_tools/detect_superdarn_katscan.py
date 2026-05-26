#!/usr/bin/env python3
"""
Detect SuperDARN 8-pulse katscan transmissions in a DigitalRF recording.

This is a convenience detector built on the existing SuperDARN matched-filter
logic in `detect_superdarn_sequence.py`, but with katscan/8-pulse as the
default sequence and with carrier inference from metadata when available.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from detect_superdarn_sequence import (
    Candidate,
    Detection,
    _infer_center_hz,
    _infer_start_epoch,
    _load_span,
    _mix_decimate,
    _output_prefix,
    _plot_results,
    _refine_frequency,
    _spectral_candidates,
    _match_sequence,
    SEQUENCES as BASE_SEQUENCES,
)
from drf_compat import open_drf_like_reader


SEQUENCES = dict(BASE_SEQUENCES)
SEQUENCES["katscan"] = dict(BASE_SEQUENCES["8p"])


def _center_hz_from_properties(props: dict[str, object]) -> float | None:
    for key in ("center_frequency_hz", "center_frequency", "center_freq_hz", "cf_hz"):
        value = props.get(key)
        if value not in (None, ""):
            return float(value)
    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect SuperDARN 8-pulse katscan transmissions in DigitalRF.")
    p.add_argument("--dataset-root", type=Path, required=True, help="DigitalRF dataset root.")
    p.add_argument("--channel", default=None, help="Channel name. Default: first channel in the dataset.")
    p.add_argument(
        "--center-hz",
        type=float,
        default=None,
        help="RF center frequency. Default: infer from DigitalRF metadata when available.",
    )
    p.add_argument(
        "--sequence",
        choices=sorted(SEQUENCES),
        default="katscan",
        help="Pulse sequence to match. Default: katscan (alias for the repo's 8-pulse sequence).",
    )
    p.add_argument("--skip-seconds", type=float, default=10.0, help="Skip this many seconds from the start. Default: 10.")
    p.add_argument("--seconds", type=float, default=20.0, help="Seconds of RF to analyze. Default: 20.")
    p.add_argument(
        "--search-span-hz",
        type=float,
        default=100e3,
        help="Search candidate carriers within +/- this span. Default: 100e3.",
    )
    p.add_argument("--nfft", type=int, default=4096, help="FFT length for candidate search. Default: 4096.")
    p.add_argument("--max-candidates", type=int, default=12, help="Maximum candidate carriers to evaluate. Default: 12.")
    p.add_argument(
        "--decimated-rate",
        type=float,
        default=100e3,
        help="Baseband rate for matched filtering. Default: 100e3.",
    )
    p.add_argument("--channel-lp-hz", type=float, default=12e3, help="Lowpass cutoff before decimation. Default: 12e3.")
    p.add_argument("--fine-span-hz", type=float, default=1500.0, help="Residual frequency search span around the best coarse hit.")
    p.add_argument("--fine-step-hz", type=float, default=50.0, help="Residual frequency search step.")
    p.add_argument(
        "--output-prefix",
        type=Path,
        default=None,
        help="Output prefix for PNG and JSON files. Default: <dataset>_<sequence>_superdarn.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = SEQUENCES[args.sequence]

    reader, resolved_channel, reader_mode = open_drf_like_reader(args.dataset_root, args.channel)
    channels = reader.get_channels()
    if not channels:
        raise RuntimeError("No DigitalRF channels found.")
    if reader_mode != "digital_rf":
        print(f"Using flat Data/rf@*.h5 reader for channel {resolved_channel} under {args.dataset_root}")

    channel = resolved_channel
    if channel not in channels:
        raise RuntimeError(f"Channel {channel!r} not found. Available: {channels}")

    props = reader.get_properties(channel)
    fs = float(props["samples_per_second"])
    dataset_start, dataset_stop = reader.get_bounds(channel)
    start_sample = int(dataset_start + int(round(args.skip_seconds * fs)))
    total_samples = int(round(args.seconds * fs))
    if total_samples <= 0:
        raise RuntimeError("--seconds must be positive.")
    if start_sample + total_samples - 1 > dataset_stop:
        total_samples = dataset_stop - start_sample + 1
    if total_samples <= 0:
        raise RuntimeError("Requested analysis window is outside dataset bounds.")

    center_hz = float(args.center_hz) if args.center_hz is not None else _center_hz_from_properties(props)
    if center_hz is None:
        center_hz = _infer_center_hz(args.dataset_root)
    if center_hz is None:
        raise RuntimeError("Could not infer center frequency from channel properties or metadata. Supply --center-hz.")

    x, finite_frac = _load_span(reader, channel, start_sample, total_samples)

    freqs, mean_db, candidates = _spectral_candidates(
        x,
        fs=fs,
        center_hz=center_hz,
        pri_hz=1.0 / cfg["pri_s"],
        search_span_hz=args.search_span_hz,
        nfft=args.nfft,
        max_candidates=args.max_candidates,
    )
    if not candidates:
        raise RuntimeError("No spectral candidates found in the requested search span.")

    decim = int(round(fs / args.decimated_rate))
    group_delay_raw = (161 - 1) // 2
    global_start_dec = start_sample // decim + group_delay_raw // decim

    best_coarse: Candidate | None = None
    best_y = np.array([], dtype=np.complex64)
    best_det: Detection | None = None

    for cand in candidates:
        y = _mix_decimate(
            x,
            fs_in=fs,
            mix_hz=cand.offset_hz,
            fs_out=args.decimated_rate,
            lp_hz=args.channel_lp_hz,
        )
        if y.size == 0:
            continue
        _, _, det = _match_sequence(
            y,
            fs=args.decimated_rate,
            global_start_sample=global_start_dec,
            pulse_sequence=cfg["pulse_sequence"],
            tau_us=cfg["tau_us"],
            pulse_len_us=cfg["pulse_len_us"],
            pri_s=cfg["pri_s"],
        )
        if best_det is None or det.score > best_det.score:
            best_coarse = cand
            best_y = y
            best_det = det

    if best_coarse is None or best_det is None or best_y.size == 0:
        raise RuntimeError("No candidate produced a matched-filter hit.")

    best_offset, profile, series, best_det = _refine_frequency(
        best_y,
        fs=args.decimated_rate,
        global_start_sample=global_start_dec,
        coarse_offset_hz=best_coarse.offset_hz,
        pulse_sequence=cfg["pulse_sequence"],
        tau_us=cfg["tau_us"],
        pulse_len_us=cfg["pulse_len_us"],
        pri_s=cfg["pri_s"],
        fine_span_hz=args.fine_span_hz,
        fine_step_hz=args.fine_step_hz,
    )
    best_det.offset_hz = float(best_offset)
    best_det.abs_freq_hz = float(center_hz + best_offset)

    prefix = _output_prefix(args)
    png_path = prefix.with_suffix(".png")
    json_path = prefix.with_suffix(".json")

    _plot_results(
        png_path,
        center_hz=center_hz,
        freqs=freqs,
        mean_db=mean_db,
        candidates=candidates,
        best=best_det,
        profile=profile,
        series=series,
        fs_match=args.decimated_rate,
        pri_s=cfg["pri_s"],
        dataset_name=args.dataset_root.name,
        sequence_label=args.sequence,
    )

    start_epoch = _infer_start_epoch(args.dataset_root, start_sample, fs)
    payload = {
        "dataset_root": str(args.dataset_root),
        "channel": channel,
        "analysis_start_sample": int(start_sample),
        "analysis_start_epoch_seconds": float(start_epoch + args.skip_seconds),
        "analysis_seconds": float(total_samples / fs),
        "input_fs_hz": fs,
        "center_hz": center_hz,
        "finite_fraction": finite_frac,
        "sequence": args.sequence,
        "pulse_sequence": cfg["pulse_sequence"],
        "tau_us": cfg["tau_us"],
        "pulse_len_us": cfg["pulse_len_us"],
        "pri_s": cfg["pri_s"],
        "spectral_candidates": [asdict(c) for c in candidates],
        "best_detection": asdict(best_det),
        "output_png": str(png_path),
    }
    json_path.write_text(json.dumps(payload, indent=2))

    print(f"Dataset: {args.dataset_root}")
    print(f"Channel: {channel}")
    print(f"Center frequency: {center_hz/1e6:.6f} MHz")
    print(f"Analyzed span: start_sample={start_sample}, seconds={total_samples/fs:.3f}, finite_fraction={finite_frac:.6f}")
    print(
        f"Sequence: {args.sequence} pulses={cfg['pulse_sequence']} "
        f"tau_us={cfg['tau_us']:.1f} pulse_len_us={cfg['pulse_len_us']:.1f}"
    )
    print("Top spectral candidates:")
    for cand in candidates:
        print(
            f"  {cand.abs_freq_hz/1e6:.6f} MHz "
            f"(offset {cand.offset_hz:+.1f} Hz, line_db={cand.line_db:.2f}, "
            f"mod10={cand.mod10:.4f}, score={cand.score:.4f})"
        )
    print("Best detection:")
    print(
        f"  freq={best_det.abs_freq_hz/1e6:.6f} MHz "
        f"(offset {best_det.offset_hz:+.1f} Hz), "
        f"lag={best_det.lag_us:.1f} us, range~{best_det.one_way_range_km:.1f} km, "
        f"score={best_det.score:.2f}, doppler_hz={best_det.doppler_hz}"
    )
    print(f"Saved plot: {png_path}")
    print(f"Saved summary: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
