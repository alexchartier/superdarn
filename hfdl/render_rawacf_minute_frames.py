#!/usr/bin/env python3

"""Render 1-minute polar FOV frames directly from rawacf files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import partial
import json
import multiprocessing as mp
import os
from pathlib import Path

from backscatter import fitacf as backscatter_fitacf

from plot_fitacf_fov import (
    _load_rawacf_records,
    _parse_float_list,
    _parse_int_list,
    _record_time_utc,
)
from render_fitacf_minute_frames import _parse_utc, _render_frame


def _fit_record(rec: dict, tdiff: float | None = None) -> dict | None:
    return backscatter_fitacf._fit(rec, tdiff=tdiff)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", nargs="+", required=True, help="Input rawacf files")
    p.add_argument("--cp", type=int, required=True, help="Control program ID to keep")
    p.add_argument("--radar", default="wal", help="Radar code for title labels")
    p.add_argument("--mode-label", default="fullfov", help="Mode label for titles")
    p.add_argument("--frames-dir", required=True, help="Directory for rendered PNG frames")
    p.add_argument("--manifest", help="Optional JSON summary output")
    p.add_argument("--start-utc", help="Optional UTC start bound, ISO 8601")
    p.add_argument("--stop-utc", help="Optional UTC stop bound, ISO 8601")
    p.add_argument("--beam-ids", default="0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23")
    p.add_argument("--plot-beams", help="Subset of beam IDs to render")
    p.add_argument("--beam-az-deg", help="Comma-separated beam azimuth centers in degrees")
    p.add_argument("--power-min", type=float, default=0.0, help="Power color scale minimum (dB)")
    p.add_argument("--power-max", type=float, default=16.0, help="Power color scale maximum (dB)")
    p.add_argument("--doppler-max-abs", type=float, default=2500.0, help="Symmetric Doppler color scale half-width (m/s)")
    p.add_argument("--dpi", type=int, default=150, help="Frame DPI")
    p.add_argument("--processes", type=int, default=max((os.cpu_count() or 1) - 2, 1), help="Worker processes for rawacf fitting")
    p.add_argument("--chunksize", type=int, default=64, help="Multiprocessing imap chunk size")
    p.add_argument("--tdiff", type=float, help="Optional tdiff override passed to the fitter")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    args.frames_dir = Path(args.frames_dir).expanduser().resolve()
    args.frames_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else args.frames_dir / "manifest.json"

    start_bound = _parse_utc(args.start_utc)
    stop_bound = _parse_utc(args.stop_utc)
    input_paths = [Path(p).expanduser().resolve() for p in args.input]

    beam_ids = _parse_int_list(args.beam_ids)
    if beam_ids is None or not beam_ids:
        raise ValueError("--beam-ids must not be empty")
    plot_beams = _parse_int_list(args.plot_beams) or beam_ids
    beam_az_override = _parse_float_list(args.beam_az_deg)

    frame_paths: list[str] = []
    frame_count = 0
    raw_record_count = 0
    fitted_record_count = 0
    current_minute: datetime | None = None
    current_records: list[dict] = []

    fit_fn = partial(_fit_record, tdiff=args.tdiff)

    for input_path in sorted(input_paths):
        raw_records, _ = _load_rawacf_records(input_path)
        selected_raw_records: list[dict] = []
        for rec in raw_records:
            if int(rec.get("cp", -1)) != args.cp:
                continue
            rec_time = _record_time_utc(rec)
            if start_bound is not None and rec_time < start_bound:
                continue
            if stop_bound is not None and rec_time > stop_bound:
                continue
            selected_raw_records.append(rec)
        raw_record_count += len(selected_raw_records)
        if not selected_raw_records:
            continue

        with mp.Pool(processes=args.processes) as pool:
            for fit_rec in pool.imap(fit_fn, selected_raw_records, chunksize=args.chunksize):
                if not fit_rec:
                    continue
                fitted_record_count += 1
                fit_time = _record_time_utc(fit_rec)
                minute_key = fit_time.replace(second=0, microsecond=0)
                if current_minute is None:
                    current_minute = minute_key
                if minute_key != current_minute:
                    output_png = _render_frame(
                        records=current_records,
                        frame_index=frame_count,
                        minute_start=current_minute,
                        args=args,
                        beam_ids=beam_ids,
                        plot_beams=plot_beams,
                        beam_az_override=beam_az_override,
                    )
                    frame_paths.append(str(output_png))
                    frame_count += 1
                    current_records = []
                    current_minute = minute_key
                current_records.append(fit_rec)

    if current_records and current_minute is not None:
        output_png = _render_frame(
            records=current_records,
            frame_index=frame_count,
            minute_start=current_minute,
            args=args,
            beam_ids=beam_ids,
            plot_beams=plot_beams,
            beam_az_override=beam_az_override,
        )
        frame_paths.append(str(output_png))
        frame_count += 1

    if not frame_paths:
        raise RuntimeError("No matching rawacf records found for the requested interval")

    payload = {
        "status": "ok",
        "cp": args.cp,
        "frames_dir": str(args.frames_dir),
        "frame_count": frame_count,
        "raw_record_count": raw_record_count,
        "fitted_record_count": fitted_record_count,
        "first_frame": frame_paths[0],
        "last_frame": frame_paths[-1],
        "start_utc": start_bound.isoformat().replace("+00:00", "Z") if start_bound else None,
        "stop_utc": stop_bound.isoformat().replace("+00:00", "Z") if stop_bound else None,
        "input_files": [str(p) for p in input_paths],
        "power_min": args.power_min,
        "power_max": args.power_max,
        "doppler_max_abs": args.doppler_max_abs,
        "processes": args.processes,
        "chunksize": args.chunksize,
        "tdiff": args.tdiff,
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
