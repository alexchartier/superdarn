#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pydarnio


def record_time_utc(rec: dict) -> datetime:
    return datetime(
        int(rec["time.yr"]),
        int(rec["time.mo"]),
        int(rec["time.dy"]),
        int(rec["time.hr"]),
        int(rec["time.mt"]),
        int(rec["time.sc"]),
        int(rec["time.us"]),
        tzinfo=timezone.utc,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render the latest Wallops live FOV PNGs from rawacf files.")
    p.add_argument("--plot-script", required=True, help="Path to plot_fitacf_fov.py on wal")
    p.add_argument("--output-dir", required=True, help="Directory for PNG/JSON products on wal")
    p.add_argument("--data-root", default="/data/borealis_data", help="Wallops data root")
    p.add_argument("--channels", default="a,b", help="Comma-separated rawacf channel suffixes")
    p.add_argument("--lookback-days", type=int, default=1, help="How many previous UTC days to search")
    p.add_argument("--accumulate-scans", type=int, default=1, help="Number of scans to keep in the plot")
    return p.parse_args()


def candidate_dirs(data_root: Path, lookback_days: int) -> list[Path]:
    now = datetime.now(timezone.utc).date()
    dirs: list[Path] = []
    for day_offset in range(lookback_days + 1):
        stamp = (now - timedelta(days=day_offset)).strftime("%Y%m%d")
        dirs.append(data_root / stamp)
    return dirs


def find_latest_rawacf(data_root: Path, channel: str, lookback_days: int) -> Path:
    matches: list[Path] = []
    for day_dir in candidate_dirs(data_root, lookback_days):
        if not day_dir.exists():
            continue
        matches.extend(day_dir.glob(f"*.wal.{channel}.rawacf"))
    if not matches:
        raise FileNotFoundError(f"No rawacf files found for wal channel {channel}")
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def inspect_rawacf(path: Path) -> dict:
    records = pydarnio.read_rawacf(str(path), mode="strict")
    if not records:
        raise RuntimeError(f"No records found in {path}")

    cp_counts = Counter(int(rec.get("cp", -1)) for rec in records if "cp" in rec)
    tfreq_counts = Counter(int(rec.get("tfreq", -1)) for rec in records if "tfreq" in rec)
    valid_cps = {cp: count for cp, count in cp_counts.items() if cp >= 0}
    valid_tfreqs = {tfreq: count for tfreq, count in tfreq_counts.items() if tfreq >= 0}
    if not valid_cps:
        raise RuntimeError(f"Could not infer cp from {path}")

    return {
        "cp": max(valid_cps.items(), key=lambda item: item[1])[0],
        "tfreq_khz": max(valid_tfreqs.items(), key=lambda item: item[1])[0] if valid_tfreqs else None,
        "start_utc": record_time_utc(records[0]).isoformat().replace("+00:00", "Z"),
        "stop_utc": record_time_utc(records[-1]).isoformat().replace("+00:00", "Z"),
        "records": len(records),
    }


def current_radar_control_state() -> dict[str, str | None]:
    try:
        proc = subprocess.run(
            ["ps", "-eo", "cmd"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return {"experiment_name": None, "scheduling_mode": None}

    for line in proc.stdout.splitlines():
        if "src/radar_control.py" not in line:
            continue
        match = re.search(r"src/radar_control\.py\s+(\S+)\s+(\S+)", line)
        if not match:
            continue
        return {
            "experiment_name": match.group(1),
            "scheduling_mode": match.group(2),
        }

    return {"experiment_name": None, "scheduling_mode": None}


def render_channel(
    plot_script: Path,
    output_dir: Path,
    data_root: Path,
    channel: str,
    lookback_days: int,
    accumulate_scans: int,
) -> dict:
    rawacf_path = find_latest_rawacf(data_root, channel, lookback_days)
    source_meta = inspect_rawacf(rawacf_path)

    output_png = output_dir / f"wal_live_fov_{channel}.png"
    output_json = output_dir / f"wal_live_fov_{channel}.json"
    cmd = [
        sys.executable,
        str(plot_script),
        "--input",
        str(rawacf_path),
        "--input-format",
        "rawacf",
        "--cp",
        str(source_meta["cp"]),
        "--radar",
        "wal",
        "--mode-label",
        "live",
        "--accumulate-scans",
        str(accumulate_scans),
        "--output",
        str(output_png),
        "--json-output",
        str(output_json),
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    render_meta = json.loads(proc.stdout)

    sidecar = json.loads(output_json.read_text())
    return {
        "channel": channel,
        "source_rawacf": str(rawacf_path),
        "cp": int(sidecar["cp"]),
        "tfreq_khz": sidecar.get("tfreq_khz"),
        "start_utc": sidecar["start_utc"],
        "stop_utc": sidecar["stop_utc"],
        "duration_s": sidecar["duration_s"],
        "records": int(render_meta["records"]),
        "output_png": output_png.name,
        "output_json": output_json.name,
    }


def main() -> int:
    args = parse_args()
    plot_script = Path(args.plot_script).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    channels = [part.strip() for part in args.channels.split(",") if part.strip()]

    output_dir.mkdir(parents=True, exist_ok=True)
    status = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "radar": "wal",
        **current_radar_control_state(),
        "channels": [],
        "errors": [],
    }

    exit_code = 0
    for channel in channels:
        try:
            status["channels"].append(
                render_channel(
                    plot_script=plot_script,
                    output_dir=output_dir,
                    data_root=data_root,
                    channel=channel,
                    lookback_days=args.lookback_days,
                    accumulate_scans=args.accumulate_scans,
                )
            )
        except Exception as exc:
            exit_code = 1
            status["errors"].append(
                {
                    "channel": channel,
                    "error": str(exc),
                }
            )

    status_path = output_dir / "wal_live_fov_status.json"
    status_path.write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
