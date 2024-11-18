#!/usr/bin/env python3
"""
Script: Check Borealis Reachability
Description: Check Borealis reachability via SSH to confirm the machine is up.
"""

import subprocess
import smtplib
from email.mime.text import MIMEText

# Configuration
host = "radar@38.124.149.234"
ssh_command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, "exit"]

def check_host_reachability(command):
    """Checks if the specified host is reachable via SSH and returns True if reachable, False otherwise."""
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error checking host reachability: {e}")
        return False

def send_email(subject, body):
    """Send an email notification."""
    # Configure email settings
    sender = "superdarn@tuvalu"
    recipient = "jordan.wiker@jhuapl.edu"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP("localhost") as server:
            server.sendmail(sender, [recipient], msg.as_string())
    except Exception as e:
        print(f"Error sending email: {e}")

# Check the host status and send email based on the result
if not check_host_reachability(ssh_command):
    send_email("Borealis Is Down", "Borealis is not reachable via SSH.")
# else:
#     send_email("Borealis Is Up", "Borealis is reachable via SSH.")