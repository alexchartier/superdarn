#!/usr/bin/env python3
"""
Starting at a specified START_DATE and stepping one day at a time until END_DATE,
look at the SuperDARN data stored on Zenodo vs the SuperDARN data stored on the
BAS mirror server. For each day, determine whether no data exists, data exists
only on BAS, data exists only on Zenodo, or data exists on both BAS and Zenodo.
Save the results to a JSON file.
"""

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2024, JHUAPL"
__version__ = "1.1.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

import datetime as dt
import os
import shutil
import subprocess
import time
import helper
import glob
import json
import requests
from dateutil.relativedelta import relativedelta
import sys
from requests.adapters import HTTPAdapter, Retry
import sd_utils

# START_DATE = dt.datetime(1993, 9, 29)
START_DATE = dt.datetime.now() - relativedelta(years=15)
END_DATE = dt.datetime.now()

def main():
    """
    Main function that orchestrates the data comparison process.
    """
    startTime = time.time()
    emailSubject = '"Starting Data Check"'
    emailBody    = 'Starting Mirror vs Zenodo data check'
    # helper.send_email(emailSubject, emailBody)

    print(f"Starting data comparison for date range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    output_file = create_new_inventory_file()

    try:
        with open(output_file, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    zenodo_data = getZenodoFileList()
    mirror_data = getMirrorFileList()

    date = START_DATE
    while date <= END_DATE:
        day = date.strftime('%Y%m%d')
        print(f"{time.strftime('%Y-%m-%d %H:%M')}: Processing date: {day}")
        data[day] = []

        for radar in sd_utils.get_all_radars():
            mirror_exists = day in mirror_data and radar in mirror_data[day]
            zenodo_exists = day in zenodo_data and radar in zenodo_data[day]
            result = get_result(mirror_exists, zenodo_exists)
            #print(f"Radar: {radar}, Mirror exists: {mirror_exists}, Zenodo exists: {zenodo_exists}, Result: {result}")

            data[day].append({
                'radar': radar,
                'result': result
            })

        date += dt.timedelta(days=1)

    print(f"Saving results to {output_file}")
    with open(output_file, 'w') as outfile:
        json.dump(data, outfile)

    totalTime = helper.get_time_string(time.time() - startTime)
    emailSubject = '"Data Status Check Complete"'
    emailBody    = '"Finished checking BAS vs Zenodo data.\nTotal check runtime: {0}\nNew JSON file created: {1}"'.format(totalTime, output_file)
    # helper.send_email(emailSubject, emailBody)

    print("Data comparison complete.")

def _make_retry_session(retries=3, backoff=2.0) -> requests.Session:
    """Return a requests.Session that retries on *transient* errors (HTTP 5xx, 429)."""
    retry_strategy = Retry(
        total=retries,
        status_forcelist=[429, 500, 502, 503, 504],
        backoff_factor=backoff,
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    sess = requests.Session()
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    return sess

# one session reused for all Zenodo calls
_ZENODO_SESSION = _make_retry_session()

def getZenodoFileList():
    """
    Retrieve the list of files on Zenodo for the specified date range and save it to a JSON file.
    Handles API hiccups gracefully so the whole run doesn't abort.
    """
    os.makedirs(helper.ZENODO_FILE_LIST_DIR, exist_ok=True)
    try:
        print("Loading Zenodo data inventory...")
        with open(os.path.join(helper.ZENODO_FILE_LIST_DIR,
                               'zenodo_data_inventory.json'), 'r') as f:
            zenodo_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("No existing Zenodo data inventory found. Creating a new one.")
        zenodo_data = {}

    date = START_DATE
    while date <= END_DATE:
        month = date.strftime('%Y-%b')
        print(f"{time.strftime('%Y-%m-%d %H:%M')}: Getting Zenodo fitACF netCDF data for {month}")

        try:
            resp = _ZENODO_SESSION.get(
                'https://zenodo.org/api/records',
                params={
                    'q': f'"SuperDARN data in netCDF format ({month})"',
                    'access_token': helper.ZENODO_TOKEN,
                    'all_versions': 1,
                    'size': 1000           # grab as many hits as allowed
                },
                timeout=30
            )
            # Make sure it’s JSON
            resp.raise_for_status()
            if 'application/json' not in resp.headers.get('Content-Type', ''):
                raise ValueError(f"Unexpected content type {resp.headers.get('Content-Type')}")
            payload = resp.json()
        except Exception as exc:
            # Log the problem, skip this month, and keep going
            print(f"⚠️  Zenodo request for {month} failed: {exc}", file=sys.stderr)
            date += relativedelta(months=1)
            continue

        # payload.get("hits", {}).get("hits", []) returns a list of records (possibly empty)
        for record in payload.get("hits", {}).get("hits", []):
            for file in record.get("files", []):
                filename = file["key"]
                if filename.endswith(".nc"):
                    date_str, radar = filename.split(".")[:2]
                    zenodo_data.setdefault(date_str, []).append(radar)

        date += relativedelta(months=1)

    # deduplicate & sort radar lists
    for day, radars in zenodo_data.items():
        zenodo_data[day] = sorted(set(radars))

    outputFile = f"{helper.ZENODO_FILE_LIST_DIR}/zenodo_data_inventory.json"
    print(f"Saving Zenodo file list to {outputFile}")
    with open(outputFile, 'w') as outfile:
        json.dump(zenodo_data, outfile, indent=4)

    return zenodo_data

def _query_bas_api(block_start: dt.datetime, block_end: dt.datetime) -> list[dict]:
    """Helper: call the BAS mirror API for one <=1-year block and return the raw list of records."""
    timespan = (
        f"{block_start.strftime('%Y-%m-%dT%H:%M:%S')}/"
        f"{block_end.strftime('%Y-%m-%dT%H:%M:%S')}"
    )
    curl_cmd = [
        "curl", "-sfS",
        f"https://api.bas.ac.uk/superdarn/mirror/v3/files?timespan={timespan}"
    ]
    result = subprocess.run(
        curl_cmd,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)

def getMirrorFileList(
        start_date: dt.datetime = START_DATE,
        end_date:   dt.datetime = END_DATE,
) -> dict[str, list[str]]:
    """
    Loop over full calendar years between start_date and end_date (inclusive),
    query the BAS mirror API once per year-sized block, build a
      { 'YYYYMMDD': ['sas', 'rkn', …] }
    mapping, and save it to MIRROR_FILE_LIST_DIR/mirror_data_inventory.json.
    """
    os.makedirs(helper.MIRROR_FILE_LIST_DIR, exist_ok=True)

    mirror_data: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # 1. Build list of year-sized chunks
    # ------------------------------------------------------------------
    year_blocks: list[tuple[dt.datetime, dt.datetime]] = []
    current_year = start_date.year
    while current_year <= end_date.year:
        block_start = max(start_date, dt.datetime(current_year, 1, 1, 0, 0, 0))
        block_end   = min(end_date,   dt.datetime(current_year, 12, 31, 23, 59, 59))
        year_blocks.append((block_start, block_end))
        current_year += 1

    # ------------------------------------------------------------------
    # 2. Query BAS once per block and accumulate results
    # ------------------------------------------------------------------
    for block_start, block_end in year_blocks:
        print(f"Querying BAS API for data list from {block_start.strftime('%Y-%m-%d')} to {block_end.strftime('%Y-%m-%d')}")
        records = _query_bas_api(block_start, block_end)

        for rec in records:
            filename = rec.get("filename", "")
            # skip anything unexpected
            if not filename.endswith(".bz2") or "rawacf" not in filename:
                continue

            day   = filename[:8]              # 'YYYYMMDD'
            radar = filename.split(".")[3]    # 3-letter site code

            mirror_data.setdefault(day, []).append(radar)

    # Deduplicate + sort radars for each day
    for day, radars in mirror_data.items():
        mirror_data[day] = sorted(set(radars))

    # ------------------------------------------------------------------
    # 3. Save pretty-printed JSON
    # ------------------------------------------------------------------
    out_file = os.path.join(
        helper.MIRROR_FILE_LIST_DIR, "mirror_data_inventory.json"
    )
    with open(out_file, "w") as f:
        json.dump(mirror_data, f, indent=4)

    return mirror_data

def create_new_inventory_file():
    """
    Create a new inventory file based on the latest existing inventory file.
    If no existing inventory file is found, create a new empty file.
    """
    files = os.listdir(helper.DATA_STATUS_DIR)
    filtered_files = [f for f in files if f.endswith("_data_status.json")]
    sorted_files = sorted(filtered_files)
    latest_inventory_file = sorted_files[-1] if sorted_files else None
    new_filename = f'{END_DATE.strftime("%Y%m%d")}_data_status.json'
    new_file_path = os.path.join(helper.DATA_STATUS_DIR, new_filename)

    if latest_inventory_file:
        latest_path = os.path.join(helper.DATA_STATUS_DIR, latest_inventory_file)
        if os.path.abspath(latest_path) != os.path.abspath(new_file_path):
            shutil.copy(latest_path, new_file_path)
            print(f"Created new inventory file {new_filename} based on {latest_inventory_file}")
        else:
            print(f"File {new_filename} already exists and is the latest — skipping copy.")
    else:
        with open(new_file_path, 'w') as f:
            json.dump({}, f)
        print(f"Created new empty inventory file {new_filename}")

    return new_file_path

def get_result(mirror_exists, zenodo_exists):
    """
    Get a numerical result based on the existence of data on the mirror and Zenodo.
    0: No data exists
    1: Data exists only on Mirror
    2: Data exists only on Zenodo
    3: Data exists on both Mirror and Zenodo
    """
    if not mirror_exists and not zenodo_exists:
        return 0
    elif mirror_exists and not zenodo_exists:
        return 1
    elif not mirror_exists and zenodo_exists:
        return 2
    else:
        return 3

if __name__ == '__main__':
    main()
