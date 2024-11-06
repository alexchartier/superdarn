#!/usr/bin/env python3
"""
Script: Sync Wallops rawACFs
Description: This script syncs yesterday's files from Wallops to APL.
"""

import sys
import subprocess
import datetime
import os
import smtplib
from email.mime.text import MIMEText

def send_email(subject, body):
    # Configure email settings
    sender = "superdar@tuvalu"
    recipient = "jordan.wiker@jhuapl.edu"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    
    # Send the email
    with smtplib.SMTP("localhost") as server:
        server.sendmail(sender, [recipient], msg.as_string())

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

try:
    # Get a list of the files to sync
    files_to_sync = subprocess.check_output(
        f"ssh {borealis_server} 'ls {path}'", 
        shell=True, 
        stderr=subprocess.DEVNULL
    ).decode().strip().split("\n")

    if not files_to_sync or files_to_sync == ['']:
        send_email("Sync Notification", f"No files to sync for {year}-{month}-{day}.")
        print("No new files to sync.")
        sys.exit(0)

    # Iterate over the files to sync and only sync them if they don't already exist at APL
    for file_to_sync in files_to_sync:
        filename = os.path.basename(file_to_sync)
        destination_file = os.path.join(destination_path, filename)
        if not os.path.exists(destination_file):
            # Construct the scp command
            command = f"scp -r {borealis_server}:{file_to_sync} {destination_path}"
            
            # Execute the command
            result = subprocess.call(command, shell=True, stderr=subprocess.DEVNULL)
            if result != 0:
                send_email("Error syncing Wallops rawACF file", f"Error syncing file from borealis to tuvalu: {filename}\n")
                raise Exception(f"Error syncing file: {filename}")
            print(f"Synced file: {filename}")
        else:
            print(f"File already exists: {filename}")

    print("Sync completed successfully.")
    
    if len(files_to_sync) != 12:
        send_email("Some Wallops Files Synced", f"{len(files_to_sync)} Wallops files successfully synced for {year}-{month}-{day}\n")

except subprocess.CalledProcessError as e:
    send_email("Sync Script Error", f"Error connecting to {borealis_server} or fetching file list.\n{e}")
    sys.exit(1)

except Exception as e:
    send_email("Sync Script Error", f"An error occurred during file sync.\n{e}")
    sys.exit(1)
