#!/usr/bin/env python3
"""master_script.py

Daily SuperDARN processing driver.

This version introduces a **--clobber / -c** flag that **forces a full re-download
and re-processing** of *rawACF* files for every radar on each day in the chosen
range. When the flag is **absent** (default), the script keeps its previous
behaviour: it skips radars that already have a corresponding *fitacf.nc* file.

Incremental re-processing (default)
----------------------------------
* For each day, determine which **fitacf.nc** files already exist → *processed*
  radars.
* Download *rawACF* only for radars **not** in that set.
* Run the usual conversion chain.
* Delete the day's rawACF files (excluding Wallops as before).

Full re-processing (when `--clobber` is set)
-------------------------------------------
* Ignore any existing **fitacf.nc** files.
* Download *rawACF* for **all** radars and convert them.
* Delete rawACF files afterwards.

Examples
~~~~~~~~
```bash
# Incremental (default)
python3 master_script.py 20250101 20250131

# Force full re-processing
python3 master_script.py 20250101 20250131 --clobber
``` 
"""

import os
import sys
import time
import argparse
from glob import glob
from datetime import datetime, timedelta

# Local modules
import helper
import get_rawacfs
import convert_rawacf_to_fitacf
import convert_fitacf_to_netcdf
# import convert_fitacf_to_grid_netcdf       # optional
# import convert_fitacf_to_meteorwind        # optional

LOG_FILE = os.path.join(helper.LOG_DIR, "master_log.txt")

# ----------------------------------------------------------------------
# Utility helpers
# ----------------------------------------------------------------------
def log_message(msg: str) -> None:
    """Write *msg* to the central log file with a timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d %H:%M")
    with open(LOG_FILE, "a") as fh:
        fh.write(f"{timestamp} - {msg}\n")


def list_processed_radars(day: datetime) -> set[str]:
    """Return a set of radar site codes that already have **fitacf.nc**
    files for *day*.
    """
    day_str = day.strftime('%Y%m%d')
    nc_dir  = day.strftime(helper.FIT_NC_DIR_FMT)
    pattern = os.path.join(nc_dir, f"{day_str}.*.nc")
    files   = glob(pattern)
    radars  = {os.path.basename(f).split('.')[1] for f in files}
    return radars


def list_known_radars() -> set[str]:
    """Derive the full list of radars from the SuperDARN *hdw.dat* files
    pointed to by the **SD_HDWPATH** environment variable.
    """
    hdw_path = os.getenv('SD_HDWPATH')
    if not hdw_path or not os.path.isdir(hdw_path):
        log_message("SD_HDWPATH not set or directory missing - falling back to empty radar list")
        return set()

    paths = glob(os.path.join(hdw_path, '*'))
    return {os.path.basename(p).split('.')[-1] for p in paths}


def delete_rawacfs(day: datetime) -> None:
    """Remove rawACF files for *day* (except Wallops - historically kept)."""
    day_str = day.strftime('%Y%m%d')
    raw_dir = day.strftime(helper.RAWACF_DIR_FMT)
    all_files = glob(os.path.join(raw_dir, f"{day_str}*.rawacf*"))
    to_remove = [fp for fp in all_files if '.wal.' not in fp]

    for fp in to_remove:
        try:
            os.remove(fp)
            print(f"Deleted {fp}")
        except Exception as exc:
            log_message(f"Unable to delete {fp}: {exc}")
    print(f"Removed {len(to_remove)} rawACF files for {day_str}")


# ----------------------------------------------------------------------
# Main daily processing routine
# ----------------------------------------------------------------------
def process_day(day: datetime, known_radars: set[str], *, clobber: bool = False) -> None:
    day_str = day.strftime('%Y%m%d')
    log_message(f"=== {day_str}: start ===")

    if clobber:
        pending = sorted(known_radars)
    else:
        already_done = list_processed_radars(day)
        pending      = sorted(known_radars - already_done)

    if not pending:
        print(f"{day_str}: all radars already processed - skipping")
        log_message(f"{day_str}: nothing to do")
        return

    action = "(clobber) processing" if clobber else "need processing"
    print(f"{day_str}: {len(pending)} radars {action} → {', '.join(pending)}")
    print(f"Already done: {', '.join(already_done)}")

    # ------------------------------------------------------------------
    # 1. Download rawACF for each *pending* radar
    # ------------------------------------------------------------------
    for radar in pending:
        try:
            get_rawacfs.main(day_str, radar=radar, show_progress=False)
        except Exception as exc:
            log_message(f"{day_str}: rawACF download failed for {radar}: {exc}")
            # continue with other radars
            continue

    # ------------------------------------------------------------------
    # 2. Convert chain (rawACF → fitACF → netCDF)
    # ------------------------------------------------------------------
    try:
        convert_rawacf_to_fitacf.main(day_str, clobber=clobber)
        convert_fitacf_to_netcdf.main(day_str, clobber=clobber)
        # convert_fitacf_to_grid_netcdf.main(day_str)
        # convert_fitacf_to_meteorwind.main(day_str)
    except Exception as exc:
        log_message(f"{day_str}: conversion failure: {exc}")

    # ------------------------------------------------------------------
    # 3. Clean-up
    # ------------------------------------------------------------------
    delete_rawacfs(day)

    log_message(f"=== {day_str}: end ===")


# ----------------------------------------------------------------------
# Entry-point
# ----------------------------------------------------------------------
def main() -> None:
    # --------------------------------------------------------------
    # Argument parsing
    # --------------------------------------------------------------
    parser = argparse.ArgumentParser(
        prog="master_script.py",
        description="Daily SuperDARN processing driver with optional full re-processing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:\n  python3 master_script.py 20250101 20250131\n  python3 master_script.py 20250101 20250131 --clobber""",
    )

    parser.add_argument("start", metavar="START_YYYYMMDD", help="Start date (inclusive) in YYYYMMDD format")
    parser.add_argument("end",   metavar="END_YYYYMMDD",   help="End date (inclusive) in YYYYMMDD format")
    parser.add_argument("-c", "--clobber", action="store_true", help="Force re-download and re-process ALL radars")

    args = parser.parse_args()

    # --------------------------------------------------------------
    # Date validation
    # --------------------------------------------------------------
    try:
        start = datetime.strptime(args.start, '%Y%m%d')
        end   = datetime.strptime(args.end,   '%Y%m%d')
    except ValueError:
        parser.error('Dates must be in YYYYMMDD format')

    if start > end:
        parser.error('Start-date must be ≤ end-date')

    known_radars = list_known_radars()
    if not known_radars:
        print('No radars discovered - check SD_HDWPATH')
        return

    current = start
    while current <= end:
        t0 = time.time()
        process_day(current, known_radars, clobber=args.clobber)
        elapsed = helper.get_time_string(time.time() - t0)
        print(f"{current.strftime('%Y-%m-%d')}: finished in {elapsed}\n")
        current += timedelta(days=1)


if __name__ == '__main__':
    main()
