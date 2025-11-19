#!/usr/bin/env python3
"""Convenience wrapper for sync_radar_data_globus.

This script loops over a range of years and months (defaults 1993-2016) and
invokes sync_radar_data_globus.py for each period. It creates year/month
subdirectories beneath the supplied destination directory so every run gets its
own target path.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import helper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call sync_radar_data_globus.py for every month between two years "
            "(defaults 1993-2016). Each invocation stores files inside "
            "<sync_local_dir>/<year>/<month>."
        )
    )
    parser.add_argument(
        "sync_local_dir",
        help="Base directory to populate with YYYY/MM subdirectories for downloads.",
    )
    parser.add_argument(
        "-s",
        "--sync_station",
        default="*",
        help="Radar code to sync (passed through to sync_radar_data_globus.py).",
    )
    parser.add_argument(
        "-p",
        "--sync_pattern",
        default="*",
        help="Filename pattern forwarded to sync_radar_data_globus.py.",
    )
    parser.add_argument(
        "-t",
        "--data_type",
        default="raw",
        help="Data type passed to sync_radar_data_globus.py (e.g., raw, dat, fitacf_30).",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=1993,
        help="First year to sync (inclusive).",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2016,
        help="Last year to sync (inclusive).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing them.",
    )
    return parser.parse_args()


def build_command(
    script_path: Path,
    args: argparse.Namespace,
    year: int,
    month: int,
    destination: Path,
) -> list[str]:
    """Compose the subprocess command invocation."""
    return [
        sys.executable,
        str(script_path),
        "-y",
        str(year),
        "-m",
        f"{month:02d}",
        "-s",
        args.sync_station,
        "-p",
        args.sync_pattern,
        "-t",
        args.data_type,
        str(destination),
    ]


def allow_globus_write(base_dir: Path) -> None:
    """Allow Globus Connect Personal to write to the destination tree."""
    destination = str(base_dir)
    if not destination.endswith("/"):
        destination += "/"
    restrict_paths = f"rw~/,rw{destination}"
    cmd = (
        f"{helper.GLOBUS_PATH} -start -restrict-paths '{restrict_paths}' &"
    )
    subprocess.call(cmd, shell=True)


def ensure_destination_dir(base_dir: Path, year: int, month: int) -> Path:
    """Ensure a YYYY/MM directory exists and return its path."""
    destination = base_dir / f"{year:04d}" / f"{month:02d}"
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def main() -> None:
    args = parse_args()
    script_path = Path(__file__).with_name("sync_radar_data_globus.py")
    if not script_path.exists():
        raise SystemExit(f"Unable to locate {script_path} next to this wrapper.")

    base_dir = Path(args.sync_local_dir).expanduser().resolve()
    years = range(args.start_year, args.end_year + 1)

    globus_started = False
    try:
        for year in years:
            for month in range(1, 13):
                destination = ensure_destination_dir(base_dir, year, month)
                cmd = build_command(script_path, args, year, month, destination)
                print(f"Syncing {year}-{month:02d} into {destination}")
                if args.dry_run:
                    print("DRY RUN:", " ".join(cmd))
                    continue
                if not globus_started:
                    allow_globus_write(base_dir)
                    globus_started = True
                completed = subprocess.run(cmd, check=False)
                if completed.returncode != 0:
                    raise SystemExit(
                        f"sync_radar_data_globus.py failed for {year}-{month:02d} "
                        f"(exit code {completed.returncode})"
                    )
    except KeyboardInterrupt:
        raise SystemExit("Sync interrupted by user.")


if __name__ == "__main__":
    main()
