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
import sd_utils

START_DATE = dt.datetime(1993, 9, 29)
END_DATE = dt.datetime.now()

def main():
    """
    Main function that orchestrates the data comparison process.
    """
    startTime = time.time()
    emailSubject = '"Starting Data Check"'
    emailBody    = 'Starting Mirror vs Zenodo data check'
    helper.send_email(emailSubject, emailBody)

    print(f"Starting data comparison for date range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    output_file = create_new_inventory_file()
    print(f"Created new inventory file: {output_file}")
    data = {}

    print("Retrieving Zenodo file list...")
    getZenodoFileList()
    print("Retrieving mirror file list...")
    getMirrorFileList()

    print("Loading mirror data inventory...")
    with open(os.path.join(helper.MIRROR_FILE_LIST_DIR, 'mirror_data_inventory.json'), 'r') as f:
        mirror_data = json.load(f)

    print("Loading Zenodo data inventory...")
    with open(os.path.join(helper.ZENODO_FILE_LIST_DIR, 'zenodo_data_inventory.json'), 'r') as f:
        zenodo_data = json.load(f)

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
    helper.send_email(emailSubject, emailBody)

    print("Data comparison complete.")

def getZenodoFileList():
    """
    Retrieve the list of files on Zenodo for the specified date range and save it to a JSON file.
    """
    os.makedirs(helper.ZENODO_FILE_LIST_DIR, exist_ok=True)
    zenodoData = {}

    date = START_DATE
    while date <= END_DATE:
        month = date.strftime('%Y-%b')
        print(f"{time.strftime('%Y-%m-%d %H:%M')}: Getting Zenodo fitACF netCDF data for {month}")

        response = requests.get('https://zenodo.org/api/records',
                                params={'q': f'"SuperDARN data in netCDF format ({month})"',
                                        'access_token': helper.ZENODO_TOKEN})

        if response.json()["hits"]["hits"]:
            files = response.json()["hits"]["hits"][0].get('files')
            for file in files:
                filename = file['key']
                if filename.endswith('.nc'):
                    date_str = filename.split('.')[0]
                    radar = filename.split('.')[1]
                    if date_str not in zenodoData:
                        zenodoData[date_str] = [radar]
                    elif radar not in zenodoData[date_str]:
                        zenodoData[date_str].append(radar)

        date += relativedelta(months=1)

    outputFile = f"{helper.ZENODO_FILE_LIST_DIR}/zenodo_data_inventory.json"
    print(f"Saving Zenodo file list to {outputFile}")
    with open(outputFile, 'w') as outfile:
        json.dump(zenodoData, outfile)

def getMirrorFileList():
    """
    Retrieve the list of files on the BAS mirror server for the specified date range and save it to a JSON file.
    """
    os.makedirs(helper.MIRROR_FILE_LIST_DIR, exist_ok=True)
    mirror_data = {}

    date = START_DATE
    while date <= END_DATE:
        day = date.strftime('%Y%m%d')
        month = date.strftime('%m')
        print(f"{time.strftime('%Y-%m-%d %H:%M')}: Getting mirror data for {day}")

        ssh_command_raw = f"ssh bas 'ls -R /sddata/raw/{date.year}/{month}/{day}*' 2>/dev/null"
        ssh_command_dat = f"ssh bas 'ls -R /sddata/dat/{date.year}/{month}/{day}*' 2>/dev/null"

        result_raw = subprocess.run(ssh_command_raw, shell=True, capture_output=True, text=True)
        result_dat = subprocess.run(ssh_command_dat, shell=True, capture_output=True, text=True)

        lines = result_raw.stdout.split('\n') + result_dat.stdout.split('\n')
        for line in lines:
            filename = line.strip()
            # print(line)
            if filename.endswith('.bz2'):
                if filename.startswith('/sddata/raw/'):
                    radar = filename.split('.')[3]
                elif filename.startswith('/sddata/dat/'):
                    radar_letter = filename.split('.')[0].split('/')[-1][10]
                    radar = helper.get_three_letter_radar_id(radar_letter)
                else:
                    continue

                if day not in mirror_data:
                    mirror_data[day] = [radar]
                elif radar not in mirror_data[day]:
                    mirror_data[day].append(radar)

        date += dt.timedelta(days=1)

    outputFile = f"{helper.MIRROR_FILE_LIST_DIR}/mirror_data_inventory.json"
    print(f"Saving mirror file list to {outputFile}")
    with open(outputFile, 'w') as outfile:
        json.dump(mirror_data, outfile)

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

    if latest_inventory_file:
        shutil.copy(os.path.join(helper.DATA_STATUS_DIR, latest_inventory_file), os.path.join(helper.DATA_STATUS_DIR, new_filename))
        print(f"Created new inventory file {new_filename} based on {latest_inventory_file}")
    else:
        with open(os.path.join(helper.DATA_STATUS_DIR, new_filename), 'w') as f:
            json.dump({}, f)
        print(f"Created new empty inventory file {new_filename}")

    return os.path.join(helper.DATA_STATUS_DIR, new_filename)

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