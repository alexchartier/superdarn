#!/usr/bin/env python3

"""Render 1-minute polar FOV frames from one or more fitacf files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors
import numpy as np

from plot_fitacf_fov import (
    _aggregate_cells,
    _beam_azimuth_map,
    _beam_edges_deg,
    _draw_panel,
    _load_fitacf_records,
    _most_common_value,
    _parse_float_list,
    _parse_int_list,
    _record_time_utc,
)


def _parse_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _render_frame(
    records: list[dict],
    frame_index: int,
    minute_start: datetime,
    args: argparse.Namespace,
    beam_ids: list[int],
    plot_beams: list[int],
    beam_az_override: list[float] | None,
) -> Path:
    frang = _most_common_value(records, "frang")
    rsep = _most_common_value(records, "rsep")
    nrang = _most_common_value(records, "nrang")
    tfreq = _most_common_value(records, "tfreq")
    if frang is None or rsep is None or nrang is None:
        raise RuntimeError(f"Could not infer frang/rsep/nrang for minute {minute_start.isoformat()}")

    beam_az_deg = _beam_azimuth_map(records, beam_ids, beam_az_override)
    beam_edges_deg = _beam_edges_deg(beam_az_deg)
    range_edges_km = (float(frang) - 0.5 * float(rsep)) + np.arange(nrang + 1, dtype=float) * float(rsep)

    power, doppler = _aggregate_cells(records, plot_beams, nrang)

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(14, 6),
        subplot_kw={"projection": "polar"},
        constrained_layout=True,
    )

    power_norm = colors.Normalize(vmin=args.power_min, vmax=args.power_max)
    doppler_norm = colors.TwoSlopeNorm(
        vmin=-args.doppler_max_abs,
        vcenter=0.0,
        vmax=args.doppler_max_abs,
    )

    sm_power = _draw_panel(
        axes[0],
        values=power,
        plot_beams=plot_beams,
        beam_edges_deg=beam_edges_deg,
        range_edges_km=range_edges_km,
        cmap="turbo",
        norm=power_norm,
        title="Power",
    )
    sm_doppler = _draw_panel(
        axes[1],
        values=doppler,
        plot_beams=plot_beams,
        beam_edges_deg=beam_edges_deg,
        range_edges_km=range_edges_km,
        cmap="RdBu_r",
        norm=doppler_norm,
        title="Doppler",
    )

    cbar_power = fig.colorbar(sm_power, ax=axes[0], pad=0.08)
    cbar_power.set_label("Power (dB)")
    cbar_doppler = fig.colorbar(sm_doppler, ax=axes[1], pad=0.08)
    cbar_doppler.set_label("Doppler (m/s)")

    radar = args.radar.upper()
    tfreq_text = f", tfreq={tfreq} kHz" if tfreq is not None else ""
    start_utc = _record_time_utc(records[0])
    stop_utc = _record_time_utc(records[-1])
    fig.suptitle(
        f"{radar} {args.mode_label} polar FOV (cp={args.cp}{tfreq_text})\n"
        f"{start_utc.strftime('%Y-%m-%d %H:%M:%S')} to "
        f"{stop_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    stamp = minute_start.strftime("%Y%m%dT%H%MZ")
    output_png = args.frames_dir / f"frame_{frame_index:04d}_{stamp}.png"
    fig.savefig(output_png, dpi=args.dpi)
    plt.close(fig)
    return output_png


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", nargs="+", required=True, help="Input fitacf files")
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
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    args.frames_dir = Path(args.frames_dir).expanduser().resolve()
    args.frames_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else args.frames_dir / "manifest.json"
    input_paths = [Path(p).expanduser().resolve() for p in args.input]
    start_bound = _parse_utc(args.start_utc)
    stop_bound = _parse_utc(args.stop_utc)

    beam_ids = _parse_int_list(args.beam_ids)
    if beam_ids is None or not beam_ids:
        raise ValueError("--beam-ids must not be empty")
    plot_beams = _parse_int_list(args.plot_beams) or beam_ids
    beam_az_override = _parse_float_list(args.beam_az_deg)

    frame_paths: list[str] = []
    minute_count = 0
    record_count = 0
    minute_start: datetime | None = None
    minute_records: list[dict] = []

    for input_path in sorted(input_paths):
        records, _ = _load_fitacf_records(input_path)
        for rec in records:
            if int(rec.get("cp", -1)) != args.cp:
                continue
            rec_time = _record_time_utc(rec)
            if start_bound is not None and rec_time < start_bound:
                continue
            if stop_bound is not None and rec_time > stop_bound:
                continue
            minute_key = rec_time.replace(second=0, microsecond=0)
            if minute_start is None:
                minute_start = minute_key
            if minute_key != minute_start:
                output_png = _render_frame(
                    records=minute_records,
                    frame_index=minute_count,
                    minute_start=minute_start,
                    args=args,
                    beam_ids=beam_ids,
                    plot_beams=plot_beams,
                    beam_az_override=beam_az_override,
                )
                frame_paths.append(str(output_png))
                minute_count += 1
                minute_records = []
                minute_start = minute_key
            minute_records.append(rec)
            record_count += 1

    if minute_records and minute_start is not None:
        output_png = _render_frame(
            records=minute_records,
            frame_index=minute_count,
            minute_start=minute_start,
            args=args,
            beam_ids=beam_ids,
            plot_beams=plot_beams,
            beam_az_override=beam_az_override,
        )
        frame_paths.append(str(output_png))
        minute_count += 1

    if not frame_paths:
        raise RuntimeError("No matching fitacf records found for the requested interval")

    payload = {
        "status": "ok",
        "cp": args.cp,
        "frames_dir": str(args.frames_dir),
        "frame_count": minute_count,
        "record_count": record_count,
        "first_frame": frame_paths[0],
        "last_frame": frame_paths[-1],
        "start_utc": start_bound.isoformat().replace("+00:00", "Z") if start_bound else None,
        "stop_utc": stop_bound.isoformat().replace("+00:00", "Z") if stop_bound else None,
        "input_files": [str(p) for p in input_paths],
        "power_min": args.power_min,
        "power_max": args.power_max,
        "doppler_max_abs": args.doppler_max_abs,
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
