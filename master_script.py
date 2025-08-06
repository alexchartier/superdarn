#!/usr/bin/env python3
"""master_script.py

Daily SuperDARN processing driver.

This updated version adds **incremental re-processing** for the last *N*
days (default: 30) so that if new *rawACF* files appear on the BAS
server **after** an earlier run, only the *missing* radars are pulled
and processed.

Key workflow per day
--------------------
1. Determine which **fitacf.nc** files already exist → *processed* radars.
2. Download *rawACF* only for radars **not** in that set.
3. Run the normal → *fitacf2/3 → despeck.fitacf3 → netCDF* chain.
4. Delete the day's rawACF (excluding Wallops files as before).

python3 master_script.py 20250101 20250131
```
"""

import os
import sys
import time
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
def process_day(day: datetime, known_radars: set[str]) -> None:
    day_str = day.strftime('%Y%m%d')
    log_message(f"=== {day_str}: start ===")

    already_done = list_processed_radars(day)
    pending      = sorted(known_radars - already_done)

    if not pending:
        print(f"{day_str}: all radars already processed - skipping")
        log_message(f"{day_str}: nothing to do")
        return

    print(f"{day_str}: {len(pending)} radars need processing → {', '.join(pending)}")

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
        convert_rawacf_to_fitacf.main(day_str)
        convert_fitacf_to_netcdf.main(day_str)
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
    # Date range parsing
    # --------------------------------------------------------------
    if len(sys.argv) == 3:
        # Explicit range
        try:
            start = datetime.strptime(sys.argv[1], '%Y%m%d')
            end   = datetime.strptime(sys.argv[2], '%Y%m%d')
        except ValueError:
            sys.exit('Dates must be in YYYYMMDD format')
    else:
        sys.exit('Usage: python3 master_script.py [START_YYYYMMDD END_YYYYMMDD]')

    if start > end:
        sys.exit('Start-date must be ≤ end-date')

    known_radars = list_known_radars()
    if not known_radars:
        print('No radars discovered - check SD_HDWPATH')
        return

    current = start
    while current <= end:
        t0 = time.time()
        process_day(current, known_radars)
        elapsed = helper.get_time_string(time.time() - t0)
        print(f"{current.strftime('%Y-%m-%d')}: finished in {elapsed}\n")
        current += timedelta(days=1)


if __name__ == '__main__':
    main()
