#!/usr/bin/env python3
# coding: utf-8
"""
Downloads and combines fitACF files for the specified date.
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

# Global date variable
date = None
total_files = 0
transferred_files = -1

def main(dateString, fitacf25='true', fitacf30='true', fitacf_30_despecked='true', radar='all'):
    """
    Downloads fitACF files for the specified date combines them.

    Args:
        dateString (str): The date in 'YYYYMMDD' format.
        fitacf25 (bool): True if fitACF 2.5 files should be downloaded
        fitacf30 (bool): True if fitACF 3.0 files should be downloaded
        fitacf_30_despecked (bool): True if fitACF 3.0 despeckled files should be downloaded
        radar (str, optional): The three-letter radar site code or 'all' for all radars. Defaults to 'all'.
    """
    global date
    date = datetime.datetime.strptime(dateString, '%Y%m%d')

    startTime = time.time()
    
    fitDir = date.strftime(helper.FITACF_DIR_FMT)

    os.makedirs(fitDir, exist_ok=True)

    if fitacf25:
        download_fitacfs_from_globus(fitDir, date, radar, 'fitacf_25')
        
    if fitacf30:
        download_fitacfs_from_globus(fitDir, date, radar, 'fitacf_30')

    if fitacf_30_despecked:
        download_fitacfs_from_globus(fitDir, date, radar, 'despeck_fitacf_30')

    totalTime = helper.get_time_string(time.time() - startTime)
    # emailSubject = '"FitACF Download Complete"'
    # emailBody    = '"Finished downloading and {date} fitACF data\nTotal time: {time}"'.format(month = date.strftime('%Y%m%d'), time = totalTime)
    #helper.send_email(emailSubject, emailBody)


def download_fitacfs_from_globus(fitDir, date, radar, pattern):
    # Start Globus Connect Personal and establish connection
    # Also allow access to /project/superdarn/data/
    command = f'{helper.GLOBUS_PATH} -start -restrict-paths \'rw~/,rw/project/superdarn/data\' &'
    print(command)
    subprocess.call(command, shell=True)
    # subprocess.call('{0} -start -restrict-paths \'rw~/,rw/project/superdarn/data/fitacf\' &'.format(helper.GLOBUS_PATH), shell=True)

    # Initiate the Globus -> APL transfer
    command = f'nohup /software/python-3.11.4/bin/python3 /homes/superdarn/superdarn/globus/sync_radar_data_globus.py -y {date.year} -m {date.month} -t {pattern} {fitDir}'
    print(command)
    subprocess.call(command, shell=True)

    # Stop Globus Connect Personal
    #subprocess.call('{0} -stop'.format(helper.GLOBUS_PATH), shell=True)

    emailSubject = '"{0} {1} Data Successfully Downloaded"'.format(date.strftime('%Y/%m'), pattern)
    emailBody    = '"{0} {1} source files have been downloaded. Starting conversion to netCDF."'.format(date.strftime('%Y/%m'), pattern)
    #helper.send_email(emailSubject, emailBody)

def combine_source_files():
    dateString = date.strftime('%Y%m%d')
    print(f'Starting to combine {dateString} fitACF files')

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


if __name__ == '__main__':
    if len(sys.argv) < 5:
        print("Usage: python3 get_fitacfs.py <date> <fitacf_25> <fitacf_30> <fitacf_30_despeckled> [<radar>]")
        print("Ex: python3 get_fitacfs.py 20230422 true false true")
        sys.exit(1)

    # Extract the day argument in 'YYYYMMDD' format
    dateString = sys.argv[1]
    fitacf_25 = sys.argv[2]
    fitacf_30 = sys.argv[3]
    fitacf_30_despeckled = sys.argv[4]

    # Extract the optional radar argument if provided
    radar = sys.argv[5] if len(sys.argv) > 5 else 'all'

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

    main(dateString, fitacf_25, fitacf_30, fitacf_30_despeckled, radar)
