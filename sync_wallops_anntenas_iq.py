#!/usr/bin/env python3
"""
Script: Sync Wallops Antennas IQ Data
Description: This script syncs antennas IQ data from Wallops to APL for a specific date range.
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

def get_dates():
    start_date = datetime.date(2025, 1, 23)
    end_date = datetime.date(2025, 1, 31)
    return [(start_date + datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range((end_date - start_date).days + 1)]

# Define the server and source directories
borealis_server = "radar@38.124.149.234"
sources = [
    "/borealis_nfs/borealis_data/antennas_iq",
    "/borealis_nfs/borealis_data/daily"
]

dates_to_sync = get_dates()

year = "2025"
month = "01"

# Define destination path
destination_path = f"/project/superdarn/data/antennas_iq/{year}/{month}"

# Create the destination directory if it doesn't exist
os.makedirs(destination_path, exist_ok=True)

try:
    for source in sources:
        for date in dates_to_sync:
            path = f"{source}/{date}*"
            result = subprocess.run(
                f"ssh {borealis_server} 'ls {path}'", 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.DEVNULL,
                text=True
            )
            
            files_to_sync = result.stdout.strip().split("\n") if result.stdout.strip() else []
            
            if not files_to_sync:
                print(f"No files found in {source} for {date}.")
                continue
            
            for file_to_sync in files_to_sync:
                filename = os.path.basename(file_to_sync)
                destination_file = os.path.join(destination_path, filename)
                if not os.path.exists(destination_file):
                    command = f"scp -r {borealis_server}:{file_to_sync} {destination_path}"
                    result = subprocess.call(command, shell=True, stderr=subprocess.DEVNULL)
                    if result != 0:
                        send_email("Error syncing Wallops Antennas IQ file", f"Error syncing file from borealis to tuvalu: {filename}\n")
                        raise Exception(f"Error syncing file: {filename}")
                    print(f"Synced file: {filename}")
                else:
                    print(f"File already exists: {filename}")
    
    print("Sync completed successfully.")

except subprocess.CalledProcessError as e:
    send_email("Sync Script Error", f"Error connecting to {borealis_server} or fetching file list.\n{e}")
    sys.exit(1)

except Exception as e:
    send_email("Sync Script Error", f"An error occurred during file sync.\n{e}")
    sys.exit(1)
