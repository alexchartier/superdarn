#!/usr/bin/env python3
# coding: utf-8
"""
get_fitacfs.py
--------------
Grab FITACF files from the SuperDARN Globus mirror using the existing
`sync_radar_data_globus.py` helper script.

Compared to get_rawacfs.py (which targets rawACFs), this script targets FITACF
products and lets you choose which variants to fetch:
  - fitacf2  -> Globus data_type "fitacf_25"
  - fitacf3  -> Globus data_type "fitacf_30"
  - fitacf3_despeckled -> Globus data_type "despeck_fitacf_30"

If no types are specified, all three are fetched.

Examples
--------
# All three types for 20250115, all radars, default destination
./get_fitacfs.py 20250115

# Specific radar (sas) for a day
./get_fitacfs.py 20250115 sas

# Two types only, verbose
./get_fitacfs.py 20250115 sas -t fitacf2 fitacf3 -v

# Custom destination directory
./get_fitacfs.py 20250115 sas -t fitacf3 -d /project/superdarn/data/fitacf/2025/01/

Notes
-----
- This script invokes `sync_radar_data_globus.py`. You can point to it with
  --sync-script, or set an environment variable:
      GLOBUS_SYNC_SCRIPT=/path/to/sync_radar_data_globus.py
  If neither is set, we search common locations including a local 'globus/' folder.
- Globus Connect Personal must be installed and authorized on the host
  used as the destination endpoint (see the README referenced in the sync script).
"""

import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Optional helper import (used by other project scripts for standard paths)
_HELPER = None
try:
    import helper as _HELPER
except Exception:
    _HELPER = None

# Type mapping from friendly names -> globus sync data_type values
TYPE_MAP = {
    "fitacf2": "fitacf_25",
    "fitacf3": "fitacf_30",
    "fitacf3_despeckled": "despeck_fitacf_30",
    # allow a dash variant too
    "fitacf3-despeckled": "despeck_fitacf_30",
}

def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Download FITACF files from Globus for a given date (YYYYMMDD) and optional radar.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("date", help="Date in YYYYMMDD")
    p.add_argument("radar", nargs="?", default="all",
                   help="Three-letter radar code (e.g., sas). Use 'all' for all radars.")
    p.add_argument("-t", "--types", nargs="*", default=None,
                   choices=sorted(set(TYPE_MAP.keys())),
                   help="One or more FITACF types to fetch. If omitted, all will be fetched.")
    p.add_argument("-d", "--dest", default=None,
                   help="Destination directory. Defaults to helper.FITACF_DIR_FMT for the given date, "
                        "or ./fitacf/YYYY/MM if helper is unavailable.")
    p.add_argument("--sync-script", default=None,
                   help="Path to sync_radar_data_globus.py (overrides auto-detection).")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Verbose: print filenames as they are fetched and other details.")
    return p.parse_args(argv)


def _validate_date(datestr: str) -> _dt.date:
    if not re.fullmatch(r"\d{8}", datestr):
        raise ValueError("Date must be in YYYYMMDD format")
    return _dt.datetime.strptime(datestr, "%Y%m%d").date()


def _default_dest(date_obj: _dt.date) -> str:
    """Compute default destination directory following project conventions if possible."""
    if _HELPER is not None and hasattr(_HELPER, "FITACF_DIR_FMT"):
        try:
            # Expecting something like '/project/superdarn/data/fitacf/%Y/%m'
            return _dt.datetime.combine(date_obj, _dt.time()).strftime(_HELPER.FITACF_DIR_FMT)
        except Exception:
            pass
    # Fallback to cwd/fitacf/YYYY/MM
    return str(Path.cwd() / "fitacf" / f"{date_obj.year:04d}" / f"{date_obj.month:02d}")


def _ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


def _existing_set(dest_dir: str):
    """Return a set of existing file basenames in dest_dir (non-recursive)."""
    if not os.path.isdir(dest_dir):
        return set()
    return set(os.listdir(dest_dir))


def _resolve_sync_script(user_arg: str | None, verbose: bool = False) -> str:
    """Resolve the path to sync_radar_data_globus.py with sensible fallbacks.
    Returns a path (or executable name) suitable for passing to subprocess.
    Raises FileNotFoundError if nothing plausible is found.
    """
    # 1) Environment variable overrides all
    env = os.getenv("GLOBUS_SYNC_SCRIPT") or os.getenv("SYNC_RADAR_DATA_GLOBUS")
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            if verbose:
                print(f"[INFO] Using sync script from env: {p}")
            return str(p)
        raise FileNotFoundError(f"Environment variable points to missing sync script: {p}")

    # 2) Explicit CLI arg
    if user_arg:
        p = Path(user_arg).expanduser()
        if p.is_file():
            if verbose:
                print(f"[INFO] Using sync script from --sync-script: {p}")
            return str(p)
        raise FileNotFoundError(f"--sync-script path does not exist: {p}")

    # 3) Common locations relative to this file and CWD
    here = Path(__file__).resolve().parent
    candidates = [
        here / "sync_radar_data_globus.py",
        here / "globus" / "sync_radar_data_globus.py",   # e.g., /homes/.../superdarn/globus/...
        Path.cwd() / "sync_radar_data_globus.py",
        Path.cwd() / "globus" / "sync_radar_data_globus.py",
    ]
    for c in candidates:
        if c.is_file():
            if verbose:
                print(f"[INFO] Using detected sync script: {c}")
            return str(c)

    # 4) Last resort: search PATH
    which = shutil.which("sync_radar_data_globus.py")
    if which:
        if verbose:
            print(f"[INFO] Using sync script found in PATH: {which}")
        return which

    raise FileNotFoundError(
        "Could not locate sync_radar_data_globus.py. "
        "Set --sync-script or GLOBUS_SYNC_SCRIPT, or place the script in ./globus/ next to get_fitacfs.py"
    )


def _run_sync(sync_script: str, year: int, month: int, data_type: str, pattern: str, station: str, dest_dir: str, verbose: bool):
    """Invoke the sync script for a single type. Returns (returncode, stdout, stderr)."""
    cmd = [
        sys.executable, sync_script,
        "-y", str(year),
        "-m", f"{month:02d}",
        "-t", data_type,
        "-p", pattern,
        "-s", station if station else "*",
        dest_dir,
    ]
    if verbose:
        print(f"[INFO] Running: {' '.join(cmd)}")
    # Stream output if verbose; else capture
    if verbose:
        return subprocess.call(cmd), None, None
    else:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return p.returncode, p.stdout, p.stderr


def main(argv=None):
    args = _parse_args(argv)
    date_obj = _validate_date(args.date)
    year, month = date_obj.year, date_obj.month

    # Determine destination directory
    dest_dir = args.dest or _default_dest(date_obj)
    _ensure_dir(dest_dir)

    # Resolve sync script path
    try:
        sync_script_path = _resolve_sync_script(args.sync_script, args.verbose)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return 2

    # Normalize and expand types
    if not args.types or len(args.types) == 0:
        chosen_types = ["fitacf2", "fitacf3", "fitacf3_despeckled"]
    else:
        # Support comma-separated values as well as space-separated
        expanded = []
        for t in args.types:
            expanded.extend([s for s in re.split(r"[,\s]+", t) if s])
        chosen_types = expanded

    # Build the globus sync pattern and station flag
    # Examples from sync script suggest using '-p 20141201*sas' for a single day/radar.
    if args.radar.lower() == "all":
        station = "*"
        pattern = f"{args.date}*"
    else:
        station = args.radar.lower()
        pattern = f"{args.date}*{station}"

    if args.verbose:
        print(f"[INFO] Destination: {dest_dir}")
        print(f"[INFO] Date: {args.date} (year={year}, month={month:02d})")
        print(f"[INFO] Radar: {args.radar}")
        print(f"[INFO] Pattern: {pattern}")
        print(f"[INFO] Types: {', '.join(chosen_types)}")

    # Track files to report per type
    overall_new = []

    for t in chosen_types:
        if t not in TYPE_MAP:
            print(f"[WARN] Unknown type '{t}' – skipping")
            continue
        data_type = TYPE_MAP[t]

        before = _existing_set(dest_dir)
        rc, out, err = _run_sync(sync_script_path, year, month, data_type, pattern, station, dest_dir, args.verbose)
        after = _existing_set(dest_dir)
        new_files = sorted(list(after - before))

        if rc != 0:
            print(f"[ERROR] sync_radar_data_globus.py failed for type '{t}' (data_type='{data_type}') with return code {rc}.")
            if not args.verbose:
                if out:
                    print("[STDOUT]\n" + out.strip())
                if err:
                    print("[STDERR]\n" + err.strip())
        else:
            print(f"[OK] Grabbed {len(new_files)} file(s) for {t} -> {dest_dir}")
            if args.verbose and new_files:
                for n in new_files:
                    print(f"  - {n}")
            overall_new.extend(new_files)

    # Final summary
    if args.verbose:
        # De-duplicate in case multiple types created the same filename (unlikely, but safe)
        unique_new = sorted(set(overall_new))
        if unique_new:
            print(f"[SUMMARY] Total new files: {len(unique_new)}")
        else:
            print("[SUMMARY] No new files were downloaded (they may already exist).")


if __name__ == "__main__":
    sys.exit(main())
