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
from glob import glob
import sd_utils

DELAY = 60  # 1 minute
RETRIES = 15    # Try to connect every 30 minutes for a day
TIMEOUT = 10  # seconds

# Global date variable
date = None
total_files = 0
transferred_files = -1

def main(dateString, radar='all', show_progress=True):
    """
    Downloads rawACF files for the specified date from the specified source and combines them.

    Args:
        dateString (str): The date in 'YYYYMMDD' format.
        radar (str, optional): The three-letter radar site code or 'all' for all radars. Defaults to 'all'.
        show_progress (bool, optional): Whether to show the progress bar. Defaults to True.
    """
    global date
    date = datetime.datetime.strptime(dateString, '%Y%m%d')
    dataSource = 'bas'  # Set the default data source to 'bas'

    download_source_files(dataSource, radar, show_progress)


def download_source_files(dataSource, radar, show_progress):
    """
    Downloads rawACF files from the specified data source.

    Args:
        dataSource (str): The data source ('bas' or 'globus').
        radar (str): The three-letter radar site code or 'all' for all radars.
        show_progress (bool): Whether to show the progress bar.
    """
    rawDir = date.strftime(helper.RAWACF_DIR_FMT)
    os.makedirs(rawDir, exist_ok=True)

    if dataSource == 'bas':
        download_files_from_bas(rawDir, radar, show_progress)
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

def download_files_from_bas(rawDir, radar, show_progress):
    """
    Downloads rawACF files from BAS.

    Args:
        rawDir (str): The directory to save the downloaded files.
        radar (str): The three-letter radar site code or 'all' for all radars.
        show_progress (bool): Whether to show the progress bar.
    """
    basRawDir = date.strftime(helper.BAS_RAWACF_DIR_FMT)

    # Make sure the BAS server is reachable
    if not BASServerConnected():
        # Send email if BAS couldn't be reached
        emailSubject = '"Unable to reach BAS"'
        emailBody = 'Unable to reach BAS after trying for {} minutes.'.format(RETRIES * DELAY / 60)
        helper.send_email(emailSubject, emailBody)
        sys.exit('{message}'.format(message=emailBody))

    dateString = date.strftime('%Y%m%d')
    if radar == 'all':
        print(f'\n{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - Downloading {dateString} rawACFs from BAS for all radars')
    else:
        print(f'\n{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - Downloading {dateString} rawACFs from BAS for radar {radar}')
    
    print("=========================================================================")
    # Initialize progress bar
    # update_progress_bar('1 0% / 0:00:00 (xfr#0, to-chk=0/999)')
    rsyncLogDir = os.path.join(helper.LOG_DIR, 'BAS_rsync_logs', date.strftime('%Y'))
    os.makedirs(rsyncLogDir, exist_ok=True)
    rsyncLogFilename = f'BAS_rsync_{dateString}.out'
    fullLogFilename = os.path.join(rsyncLogDir, rsyncLogFilename)

    if radar == 'all':
        rsyncCommand = f'nohup rsync -av --info=progress2 --ignore-errors --log-file={fullLogFilename} apl@{helper.BAS_SERVER}:{basRawDir}/ {rawDir} --include "*{dateString}*" --exclude "*"'
    else:
        rsyncCommand = f'nohup rsync -av --info=progress2 --ignore-errors --log-file={fullLogFilename} apl@{helper.BAS_SERVER}:{basRawDir}/ {rawDir} --include "*{dateString}*.{radar}.*" --exclude "*"'

    rsyncProcess = subprocess.Popen(rsyncCommand, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    for line in rsyncProcess.stdout:
        if line.strip() and show_progress:
            update_progress_bar(line)

    rsyncExitCode = rsyncProcess.wait()

    if rsyncExitCode == 0:
        print(f'\nSuccessfully downloaded {dateString} rawACFs from BAS')
    else:
        # Send an email and end the script if rsync didn't succeed
        emailSubject = f'"Unsuccessful attempt to copy {dateString} BAS rawACF data"'
        emailBody = f'"Failed to copy {dateString} rawACFs from BAS with exit code {rsyncExitCode}. \nSee {fullLogFilename} for more details."'
        # helper.send_email(emailSubject, emailBody)
        print(emailBody)
        #sys.exit('{message}'.format(message=emailBody))

def combine_source_files():
    dateString = date.strftime('%Y%m%d')
    print(f'Starting to combine {dateString} rawACF files')

    rawDir = date.strftime(helper.RAWACF_DIR_FMT)

    # Get all files for the date
    filenames = glob(f"{os.path.join(rawDir, dateString)}.*")

    radarSites = set()  # Use a set to store unique radar sites

    for filename in filenames:
        # Use regular expression to extract the station string
        # E.g. get 'inv.a' from 20230901.2200.03.inv.a.rawacf.bz2
        match = re.search(r'\d{8}\.\d{4}\.\d{2}\.(.*?)\.rawacf\.bz2', filename)
        if match:
            radarSites.add(match.group(1))
    
    for site in radarSites:
        siteFilesFormat = os.path.join(rawDir, f"{dateString}*{site}*")
        siteFiles = glob.glob(siteFilesFormat)
        outputFilename = f"{dateString}.{site}.rawacf"
        fullOutputFilename = os.path.join(rawDir, outputFilename)
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
    for i in range(RETRIES):
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

def update_progress_bar(line):
    global total_files, transferred_files
    if 'to-chk' in line:
        total_files = int(line.split('to-chk=')[1].split('/')[1].split(')')[0]) - 1
        transferred_files += 1
        percent = transferred_files / total_files * 100
        progress_bar = '█' * int(percent // 2) + '-' * (50 - int(percent // 2))
        transfer_rate = line.split()[3]
        print(f"\rProgress: [{progress_bar}] {percent:.2f}% ({transferred_files}/{total_files}) | Transfer time: {transfer_rate}", end='', flush=True)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python script.py <date> [<radar>] [<show_progress>]")
        sys.exit(1)

    # Extract the day argument in 'YYYYMMDD' format
    dateString = sys.argv[1]

    # Extract the optional radar argument if provided
    radar = sys.argv[2] if len(sys.argv) > 2 else 'all'

    # Extract the optional show_progress argument if provided
    show_progress = sys.argv[3].lower() == 'true' if len(sys.argv) > 3 else False

    # Get the list of radar names from sd_utils.get_radar_params(hdw_dat_dir)
    rstpath = os.getenv('RSTPATH')
    assert rstpath, 'RSTPATH environment variable needs to be set'
    hdw_dat_dir = os.getenv('SD_HDWPATH')
    radar_list = sd_utils.get_radar_params(hdw_dat_dir)

    # Check if the radar argument is valid
    if radar != 'all' and radar not in radar_list:
        print(f"Radar argument must be a valid three-letter radar code. Valid radars: {', '.join(radar_list.keys())}")
        sys.exit(1)

    # Check if the day argument is in the correct format
    if not dateString.isdigit() or len(dateString) != 8:
        print("Date argument must be in 'YYYYMMDD' format.")
        sys.exit(1)

    main(dateString, radar, show_progress)
