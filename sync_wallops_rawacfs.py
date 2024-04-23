#!/usr/bin/env python3
"""
Script: Sync Wallops rawACFs
Description: This script syncs yesterday's files from Wallops to APL
"""

import sys
import subprocess
import datetime
import os


def parse_date(date_str):
    try:
        return datetime.datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError:
        print("Invalid date format. Please use YYYYMMDD.")
        sys.exit(1)


# Get the date argument if provided, or default to yesterday's date
if len(sys.argv) > 1:
    date_str = sys.argv[1]
    target_date = parse_date(date_str)
else:
    target_date = datetime.date.today() - datetime.timedelta(days=1)

# Format the date components
year = target_date.strftime('%Y')
month = target_date.strftime('%m')
day = target_date.strftime('%d')

# Define the server and path components
borealis_server = "radar@38.124.149.234"
path = f"/borealis_nfs/borealis_data/rawacf_dmap/{year}{month}{day}*"

# Create the source and destination paths
source_path = f"{borealis_server}:{path}"
destination_path = f"/project/superdarn/data/rawacf/{year}/{month}"

# Create the destination directory if it doesn't exist
os.makedirs(destination_path, exist_ok=True)

# Get a list of the files to sync
files_to_sync = subprocess.check_output(f"ssh {borealis_server} 'ls {
                                        path}'", shell=True, stderr=subprocess.DEVNULL)
files_to_sync = files_to_sync.decode().strip().split("\n")

# Iterate over the files to sync and only sync them if they don't already exist at APL
for file_to_sync in files_to_sync:
    filename = os.path.basename(file_to_sync)
    destination_file = os.path.join(destination_path, filename)
    if not os.path.exists(destination_file):
        # Construct the scp command
        command = f"scp -r {borealis_server}:{file_to_sync} {destination_path}"

        # Execute the command
        subprocess.call(command, shell=True, stderr=subprocess.DEVNULL)
        print(f"Synced file: {filename}")
    else:
        print(f"File already exists: {filename}")

print("Sync completed.")
