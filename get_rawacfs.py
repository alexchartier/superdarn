#!/usr/bin/env python3
# coding: utf-8
"""
Downloads and combines rawACF files for the specified date from the specified source.
"""

import sys
import os
import datetime
import socket
import time
import helper
import subprocess
import bz2
import re
import glob

DELAY = 1800  # 30 minutes
RETRY = 17    # Try to connect every 30 minutes for a day
TIMEOUT = 10  # seconds
MAX_NUM_RSYNC_TRIES = 3

# Global date variable
date = None

def main(dateString, dataSource=None):
    """
    Downloads rawACF files for the specified date from the specified source and combines them.

    Args:
        dateString (str): The date in 'YYYYMMDD' format.
        dataSource (str, optional): The data source ('bas' or 'globus'). Defaults to 'bas'.
    """
    global date
    date = datetime.datetime.strptime(dateString, '%Y%m%d')
    if dataSource is None:
        dataSource = 'bas'
    else:
        dataSource = dataSource.lower().strip()

    download_source_files(dataSource)
    combine_source_files()

def download_source_files(dataSource):
    """
    Downloads rawACF files from the specified data source.

    Args:
        dataSource (str): The data source ('bas' or 'globus').
    """
    rawDir = date.strftime(helper.RAWACF_DIR_FMT)
    os.makedirs(rawDir, exist_ok=True)

    if dataSource == 'bas':
        download_files_from_bas(rawDir)
    elif dataSource == 'globus':
        download_files_from_globus(rawDir)
    else:
        print(f'ERROR: Specified rawACF source is invalid {dataSource}. Valid options are: \'bas\' or \'globus\'')

def download_files_from_globus(rawDir):
    """
    Downloads rawACF files from Globus.

    Args:
        rawDir (str): The directory to save the downloaded files.
    """
    # Start Globus Connect Personal and establish connection
    # Also allow access to /project/superdarn/data/
    subprocess.call(f'{helper.GLOBUS_PATH} -start -restrict-paths \'rw~/,rw/project/superdarn/data\' &', shell=True)

    # Initiate the transfer from Globus to APL
    subprocess.call(f'nohup /project/superdarn/software/python-3.8.1/bin/python3 /homes/superdarn/superdarn/globus/sync_radar_data_globus.py -y {date.year} -m {date.month} -t raw {rawDir}', shell=True)

    # Stop Globus Connect Personal
    subprocess.call(f'{helper.GLOBUS_PATH} -stop', shell=True)

    # emailSubject = f'"{date.strftime("%Y/%m")} rawACF Data Successfully Downloaded from Globus"'
    # emailBody = f'"{date.strftime("%Y/%m")} rawACF source files have been downloaded. Starting conversion to fitACF and netCDF."'
    # helper.send_email(emailSubject, emailBody)

def download_files_from_bas(rawDir):
    """
    Downloads rawACF files from BAS.

    Args:
        rawDir (str): The directory to save the downloaded files.
    """
    basRawDir = date.strftime(helper.BAS_RAWACF_DIR_FMT)

    # Make sure the BAS server is reachable
    if not BASServerConnected():
        # Send email if BAS couldn't be reached
        emailSubject = '"Unable to reach BAS"'
        emailBody = 'Unable to reach BAS after trying for {hours} hours.'.format(hours=RETRY * DELAY / 3600)
        helper.send_email(emailSubject, emailBody)
        sys.exit('{message}'.format(message=emailBody))

    dateString = date.strftime('%Y%m%d')
    print(f'Downloading {dateString} rawACFs from BAS')
    rsyncLogDir = os.path.join(helper.LOG_DIR, 'BAS_rsync_logs', date.strftime('%Y'))
    os.makedirs(rsyncLogDir, exist_ok=True)
    rsyncLogFilename = f'BAS_rsync_{dateString}.out'
    fullLogFilename = os.path.join(rsyncLogDir, rsyncLogFilename)
    rsyncCommand = f'nohup rsync -rv apl@{helper.BAS_SERVER}:{basRawDir}/{dateString}*.rawacf.bz2 {rawDir} >& {fullLogFilename}'
    rsyncProcess = subprocess.Popen(rsyncCommand, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    rsyncExitCode = rsyncProcess.wait()

    if rsyncExitCode == 0:
        print(f'Successfully downloaded {dateString} rawACFs from BAS')
    else:
        # Send an email and end the script if rsync didn't succeed
        emailSubject = f'"Unsuccessful attempt to copy {dateString} BAS rawACF data"'
        emailBody = f'"Failed to copy {dateString} rawACFs from BAS with exit code {rsyncExitCode}. \nSee {fullLogFilename} for more details."'
        helper.send_email(emailSubject, emailBody)
        print(emailBody)
        sys.exit('{message}'.format(message=emailBody))

def combine_source_files():
    print(f'Starting to combine {dateString} rawACF files')

    basRawDir = date.strftime(helper.BAS_RAWACF_DIR_FMT)
    dateString = date.strftime('%Y%m%d')

    # Get all files for the date
    filenames = glob.glob(f"{os.path.join(basRawDir, dateString)}.*")

    radarSites = []

    for filename in filenames:
        # Use regular expression to extract the station string
        # E.g. get 'inv.a' from 20230901.2200.03.inv.a.rawacf.bz2
        match = re.search(r'\d{8}\.\d{4}\.\d{2}\.(.*?)\.rawacf\.bz2', filename)
        if match:
            radarSites.append(match.group(1))

    for site in radarSites:
        siteFiles = glob.glob(f"{dateString}.*{site}")
        outputFilename = f"{dateString}.{site}.rawacf"
        fullOutputFilename = os.path.join(basRawDir, outputFilename)
        unzipAndCombine(siteFiles, fullOutputFilename)


def unzipAndCombine(files, outputFile):
  """
  Unzips and combines the given files into a single output file.

  Args:
    files: A list of file paths to the files to be unzipped and combined.
    outputFile: The path to the output file.
  """

  with open(outputFile, "wb") as f_out:
    for file in files:
      with bz2.open(file, "rb") as f_in:
        f_out.write(f_in.read())

def BASServerConnected():
    """
    Checks if the BAS server is reachable.

    Returns:
        bool: True if the server is reachable, False otherwise.
    """
    BASup = False
    for i in range(RETRY):
        if isOpen(helper.BAS_SERVER, 22):
            BASup = True
            break
        else:
            time.sleep(DELAY)
    return BASup

def isOpen(server, port):
    """
    Checks if a server is reachable on the specified port.

    Args:
        server (str): The server hostname or IP address.
        port (int): The port number to check.

    Returns:
        bool: True if the server is reachable on the port, False otherwise.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        s.connect((server, int(port)))
        s.shutdown(socket.SHUT_RDWR)
        return True
    except:
        return False
    finally:
        s.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python script.py <date> [<dataSource>]")
        sys.exit(1)

    # Extract the day argument in 'YYYYMMDD' format
    dateString = sys.argv[1]

    # Extract the optional source argument if provided
    dataSource = sys.argv[2] if len(sys.argv) > 2 else None

    # Check if the day argument is in the correct format
    if not dateString.isdigit() or len(dateString) != 8:
        print("Date argument must be in 'YYYYMMDD' format.")
        sys.exit(1)

    main(dateString, dataSource)