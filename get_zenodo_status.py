#!/usr/bin/env python3
"""
Starting at 1993-09-29 and stepping one day at a date
to the present, look at the SuperDARN data stored on Zenodo
vs the SuperDARN data stored on Globus and BAS. For each day, 
determine whether no data exists, data exists only on 
BAS/Globus, or data exsits on BAS/Globus and Zenodo. Save the results
to a json file.
"""

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2023, JHUAPL"
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

START_DATE = dt.datetime(2023, 6, 1)
END_DATE = dt.datetime(2023, 6, 31)

def main():
    output_file = create_new_inventory_file()
    data = {}

    with open(os.path.join(helper.MIRROR_FILE_LIST_DIR, 'mirror_data_inventory.json'), 'r') as f:
        mirror_data = json.load(f)

    with open(os.path.join(helper.ZENODO_FILE_LIST_DIR, 'zenodo_data_inventory.json'), 'r') as f:
        zenodo_data = json.load(f)

    date = START_DATE
    while date <= END_DATE:
        day = date.strftime('%Y%m%d')
        month = date.strftime('%Y-%b')
        data[day] = []

        for radar in sd_utils.get_all_radars():
            mirror_exists = day in mirror_data and radar in mirror_data[day]
            zenodo_exists = month in zenodo_data and any(f.startswith(f'{day}.{radar}') for f in zenodo_data[month])
            result = get_result(mirror_exists, zenodo_exists)

            data[day].append({
                'radar': radar,
                'result': result
            })

        date += dt.timedelta(days=1)

    with open(output_file, 'w') as outfile:
        json.dump(data, outfile, indent=2)

def getZenodoFileList():
    os.makedirs(helper.ZENODO_FILE_LIST_DIR, exist_ok=True)
    zenodoData = {}

    date = START_DATE
    while date <= END_DATE:
        month = date.strftime('%Y-%b')
        print('{0}: Getting Zenodo netCDF data for {1}'.format(time.strftime('%Y-%m-%d %H:%M'), month))

        response = requests.get('https://zenodo.org/api/records',
                                params={'q': '"SuperDARN data in netCDF format ({0})"'.format(month),
                                        'access_token': helper.ZENODO_TOKEN})

        if response.json()["hits"]["hits"]:
            files = response.json()["hits"]["hits"][0].get('files')
            for file in files:
                filename = file['key']
                if filename.endswith('.nc'):
                    date_str = filename.split('_')[0]
                    radar = filename.split('_')[1]
                    if date_str not in zenodoData:
                        zenodoData[date_str] = [radar]
                    elif radar not in zenodoData[date_str]:
                        zenodoData[date_str].append(radar)

        date += relativedelta(months=1)

    outputFile = '{0}/zenodo_data_inventory.json'.format(helper.ZENODO_FILE_LIST_DIR)
    with open(outputFile, 'w') as outfile:
        json.dump(zenodoData, outfile, indent=2)


def getMirrorFileList():
    os.makedirs(helper.MIRROR_FILE_LIST_DIR, exist_ok=True)
    mirror_data = {}

    date = START_DATE
    while date <= END_DATE:
        day = date.strftime('%Y%m%d')
        print('{0}: Getting mirror data for {1}'.format(time.strftime('%Y-%m-%d %H:%M'), day))

        ssh_command = f"ssh bas 'ls -R /sddata/raw/{date.year}/{day} /sddata/dat/{date.year}/{day}'"
        result = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                filename = line.strip()
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
        else:
            print("Error:", result.stderr)

        date += dt.timedelta(days=1)

    outputFile = '{0}/mirror_data_inventory.json'.format(helper.MIRROR_FILE_LIST_DIR)
    with open(outputFile, 'w') as outfile:
        json.dump(mirror_data, outfile, indent=2)

def create_new_inventory_file():
    files = os.listdir(helper.DATA_STATUS_DIR)
    filtered_files = [f for f in files if f.endswith("_data_status.json")]
    sorted_files = sorted(filtered_files)
    latest_inventory_file = sorted_files[-1] if sorted_files else None
    new_filename = f'{END_DATE.strftime("%Y%m%d")}_data_status.json'

    if latest_inventory_file:
        shutil.copy(os.path.join(helper.DATA_STATUS_DIR, latest_inventory_file), os.path.join(helper.DATA_STATUS_DIR, new_filename))
    else:
        with open(os.path.join(helper.DATA_STATUS_DIR, new_filename), 'w') as f:
            json.dump({}, f)

    return os.path.join(helper.DATA_STATUS_DIR, new_filename)

def get_result(mirror_exists, zenodo_exists):
    # Get a numerical result based on the Globus and Zenodo values as follows:
    # 0: No data exists
    # 1: Data exists only on Mirror
    # 2: Data exists only on Zenodo
    # 3: Data exists on both Mirror and Zenodo
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