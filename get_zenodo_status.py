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

DELAY = 30 # seconds
MIN_FILE_SIZE = 1e4 # bytes
MAX_NUM_TRIES = 10

REMOVE_REMOTE_FILE_LIST = False

START_DATE = dt.datetime(1993,9,29)
END_DATE = dt.datetime(1993,12,31)
#END_DATE = dt.datetime.now()

BAS_FILE_LIST_DIR = '/project/superdarn/data/data_status/BAS_files'
GLOBUS_FILE_LIST_DIR = '/project/superdarn/data/data_status/Globus_files'
MIRROR_FILE_LIST_DIR = '/project/superdarn/data/data_status/mirror_files'
ZENODO_FILE_LIST_DIR = '/project/superdarn/data/data_status/zenodo_files'
DATA_STATUS_DIR = '/project/superdarn/data/data_status'

years_to_check = []

def main():
    startTime = time.time()
    emailSubject = '"Starting Data Check"'
    emailBody    = 'Starting Mirror vs Zenodo data check'
    helper.send_email(emailSubject, emailBody)
    
    getMirrorFileList()
    getZenodoFileList()

    radarList = sd_utils.get_all_radars()
    
    output_file = create_new_inventory_file()

    date = START_DATE
    data = {}
    existing_data = {}
    
    while date <= END_DATE:
        if date.year not in years_to_check:
            # This year's mirror data hasn't changed since the last check, so skip it
            date = date.replace(year=date.year + 1, month=1, day=1)
            continue

        day = date.strftime('%Y%m%d')
        data[day] = []
        print('{0} - Comparing data between the mirror and Zenodo on {1}'.format(time.strftime('%Y-%m-%d %H:%M'), day))
        for radar in radarList:
            mirrorDataExists = getMirrorData(date, radar)
            zenodoDataExists = getZenodoData(date, radar)
            result = get_result(mirrorDataExists, zenodoDataExists)        
 
            data[day].append({
                'radar': radar,
                'result': result
            })
                        
        with open(output_file, 'r') as infile:
            existing_data = json.load(infile)

        existing_data[day] = data[day]

        date += dt.timedelta(days=1)

    with open(output_file, 'w') as outfile:
        json.dump(existing_data, outfile)


    
    totalTime = helper.get_time_string(time.time() - startTime)
    emailSubject = '"Data Status Check Complete"'
    emailBody    = '"Finished checking Globus vs Zenodo data.\nTotal check runtime: {0}\nNew JSON file created: {1}"'.format(totalTime, output_file)
    helper.send_email(emailSubject, emailBody)

    if REMOVE_REMOTE_FILE_LIST:
        os.system('rm -rf {0}'.format(MIRROR_FILE_LIST_DIR))
    
def create_new_inventory_file():
    files = os.listdir(DATA_STATUS_DIR)
    filtered_files = [f for f in files if f.endswith("_data_status.json")]
    sorted_files = sorted(filtered_files)
    latest_inventory_file = sorted_files[-1]
    new_filename = '{0}_data_status.json'.format(END_DATE.strftime('%Y%m%d'))
    shutil.copy(os.path.join(DATA_STATUS_DIR, latest_inventory_file), os.path.join(DATA_STATUS_DIR, new_filename))
    return os.path.join(DATA_STATUS_DIR, new_filename)

def get_result(mirror, zenodo):
    # Get a numerical result based on the Globus and Zenodo values as follows:
    # 0: No data exists
    # 1: Data exists only on Mirror
    # 2: Data exists only on Zenodo
    # 3: Data exists on both Mirror and Zenodo
    sources = [zenodo, mirror]
    resultBinary = '0b' + ''.join(['1' if source else '0' for source in sources])
    result = int(resultBinary, 2)
    return result


def getMirrorData(date, radar):
    day = date.strftime('%Y%m%d')
    f = open('{0}/mirror_data_inventory.json'.format(MIRROR_FILE_LIST_DIR))
    mirror_data = json.load(f)

    # If the date isn't even in the remote data, return false because Globus 
    # has no data at all for any radars on that date
    if day not in mirror_data:
        return False

    # If the date is in the remote date, return true if the radar is listed
    # for that date
    return radar in mirror_data[day]


def getZenodoData(date, radar):
    day = date.strftime('%Y%m%d')
    f = open('{0}/zenodo_data_inventory.json'.format(ZENODO_FILE_LIST_DIR))
    zenodoData = json.load(f)
    fileStart = '{0}.{1}'.format(day, radar)

    month = date.strftime('%Y-%b')

    # If the date isn't even in the zenodo data, return false because Zenodo 
    # has no data at all for any radars on that date
    if month not in zenodoData:
        return False

    # If the month is in the zenodo date, return true if the radar is listed
    # for that date
    return fileStart in zenodoData[month]


def getZenodoFileList():
    os.makedirs(ZENODO_FILE_LIST_DIR, exist_ok=True)

    with open('{0}/zenodo_data_inventory.json'.format(ZENODO_FILE_LIST_DIR), 'r') as infile:
        existing_zenodo_data = json.load(infile)

    zenodoData = {}

    date = START_DATE
    while date <= END_DATE:
        month = date.strftime('%Y-%b')
        print('{0}: Getting Zenodo data for {1}'.format(time.strftime('%Y-%m-%d %H:%M'), month))

        response = requests.get('https://zenodo.org/api/records',
                        params={'q': '"SuperDARN data in netCDF format ({0})"'.format(month),
                                'access_token': helper.ZENODO_TOKEN})

        if response.json()["hits"]["hits"]:
            files = response.json()["hits"]["hits"][0].get('files')
            files = str(files)
        else:
            files = ''

        zenodoData[month] = files
        
        if month in existing_zenodo_data and existing_zenodo_data[month] != zenodoData[month] and date.year not in years_to_check:
            years_to_check.append(date.year)

        date += relativedelta(months=1)

    outputFile = '{0}/zenodo_data_inventory.json'.format(ZENODO_FILE_LIST_DIR)
    with open(outputFile, 'w') as outfile:
        json.dump(zenodoData, outfile)


def getMirrorFileList():

    os.makedirs(MIRROR_FILE_LIST_DIR, exist_ok=True)

    year = START_DATE.year
    while year <= END_DATE.year:

        if year >= 2005:
            numTries = 1
            print('{0}: Getting mirror rawACF data for {1} - attempt #{2}'.format(time.strftime('%Y-%m-%d %H:%M:%S'), year, numTries))
            if numTries >= MAX_NUM_TRIES:
                failedToGrabData(year)
                break

            # Get a list of all rawACF files on Globus for the given year and store them in a file
            filename_raw_new = '{0}/{1}_MirrorFilesRawNew.txt'.format(MIRROR_FILE_LIST_DIR, year)
            filename_raw = '{0}/{1}_MirrorFilesRaw.txt'.format(MIRROR_FILE_LIST_DIR, year)

            ssh_command = f"ssh bas 'ls -R /sddata/raw/{year}'"
            result = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)

            # Check if the command was successful
            if result.returncode == 0:
                # Save the output to a text file
                with open(filename_raw_new, 'w') as file:
                    file.write(result.stdout)
            else:
                print("Error:", result.stderr)
                numTries += 1

            try:
                with open(filename_raw, 'r') as file1:
                    original_list = file1.read()
            except FileNotFoundError:
                print(f"The file {filename_raw} does not exist.")
                original_list = ''

            # Read the content of the second file
            with open(filename_raw_new, 'r') as file2:
                new_list = file2.read()

            if original_list != new_list:
                if os.path.isfile(filename_raw):
                    print('Overwriting existing {0} rawACF list file'.format(year))
                    os.remove(filename_raw)
                os.rename(filename_raw_new, filename_raw)
                if year not in years_to_check:
                    years_to_check.append(year)
            else:
                os.remove(filename_raw_new)


        if year <= 2006:
            numTries = 1
            print('{0}: Getting Mirror DAT data for {1} - attempt #{2}'.format(time.strftime('%Y-%m-%d %H:%M:%S'), year, numTries))
            if numTries >= MAX_NUM_TRIES:
                failedToGrabData(year)
                break

            # Get a list of all DAT files on the mirror for the given year and store them in a file
            filename_dat_new = '{0}/{1}_MirrorFilesDatNew.txt'.format(MIRROR_FILE_LIST_DIR, year)
            filename_dat = '{0}/{1}_MirrorFilesDat.txt'.format(MIRROR_FILE_LIST_DIR, year)

            ssh_command = f"ssh bas 'ls -R /sddata/dat/{year}'"
            result = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)

            # Check if the command was successful
            if result.returncode == 0:
                # Save the output to a text file
                with open(filename_dat_new, 'w') as file:
                    file.write(result.stdout)
            else:
                print("Error:", result.stderr)
                numTries += 1

            try:
                with open(filename_dat, 'r') as file1:
                    original_list = file1.read()
            except FileNotFoundError:
                print(f"The file {filename_dat} does not exist.")
                original_list = ''
            
            # Read the content of the second file
            with open(filename_dat_new, 'r') as file2:
                new_list = file2.read()

            if original_list != new_list:
                if os.path.isfile(filename_dat):
                    print('Overwriting existing {0} rawACF list file'.format(year))
                    os.remove(filename_dat)
                os.rename(filename_dat_new, filename_dat)
                if year not in years_to_check:
                    years_to_check.append(year)
            else:
                os.remove(filename_dat_new)
    
        year += 1

    # Create an empty dict to store all radars for each date
    mirror_data = {}
    
    files  = glob.glob(os.path.join(MIRROR_FILE_LIST_DIR, '*MirrorFiles*'))
    for file in files:

        # Go through the file(s) line by line and add each line to the mirror data dict
        with open(file) as mainFileList:
            lines = mainFileList.readlines()        
            for line in lines:
                filename = line.strip()
                extension = filename.split('.')[-1]
                if not extension == 'bz2':
                    # This line isn't a rawACF or DAT filename
                    continue
               
                # Get the day and the radar for the file
                if file.split('.')[0][-3:] == 'Raw':
                    day = filename.split('.')[0].split('/')[-1]
                    radar = filename.split('.')[3]
                elif file.split('.')[0][-3:] == 'Dat':
                    day = filename.split('.')[0].split('/')[-1][:8]
                    radar_letter = filename.split('.')[0].split('/')[-1][10]
                    radar = helper.get_three_letter_radar_id(radar_letter)
                else:
                    raise ValueError('Filename does not match expectations: {0}'.format(filename))

                # Add the current radar to a new date entry if the day doesn't exist in the dict yet
                if day not in mirror_data:
                    mirror_data[day] = [radar]
                    continue

                # Get the current radar list for the given day, then
                # add the radar to the list
                if radar not in mirror_data[day]:
                    mirror_data[day].append(radar)

    outputFile = '{0}/mirror_data_inventory.json'.format(MIRROR_FILE_LIST_DIR)
    with open(outputFile, 'w') as outfile:
        json.dump(mirror_data, outfile)


def getGlobusFileList():

    os.makedirs(GLOBUS_FILE_LIST_DIR, exist_ok=True)

    # Make sure we're logged in and can access the Globus file system
    os.system('globus login')

    year = START_DATE.year
    while year <= END_DATE.year:

        if year >= 2005:
            numTries = 1
            fileSize = 0
            while fileSize < MIN_FILE_SIZE:
                print('{0}: Getting Globus rawACF data for {1} - attempt #{2}'.format(time.strftime('%Y-%m-%d %H:%M:%S'), year, numTries))
                if numTries >= MAX_NUM_TRIES:
                    failedToGrabData(year)
                    break

                # Get a list of all rawACF files on Globus for the given year and store them in a file
                filename_raw_new = '{0}/{1}_GlobusFilesRawNew.txt'.format(GLOBUS_FILE_LIST_DIR, year)
                filename_raw = '{0}/{1}_GlobusFilesRaw.txt'.format(GLOBUS_FILE_LIST_DIR, year)
                os.system('globus ls -r \'{0}:/chroot/sddata/raw/{1}\' > {2}'.format(helper.GLOBUS_SUPERDARN_ENDPOINT, year, filename_raw_new))

                # Check that the file list was actually received and stored
                fileSize = os.path.getsize(filename_raw_new)
                if fileSize < MIN_FILE_SIZE:
                    time.sleep(DELAY)
                    numTries += 1
                else:
                    # File is big enough - replace old list file
                    if os.path.isfile(filename_raw):
                        print('Overwriting existing {0} rawACF list file'.format(year))
                        os.remove(filename_raw)
                    os.rename(filename_raw_new, filename_raw)

        if year <= 2006:
            numTries = 1
            fileSize = 0
            while fileSize < MIN_FILE_SIZE:
                print('{0}: Getting Globus DAT data for {1} - attempt #{2}'.format(time.strftime('%Y-%m-%d %H:%M:%S'), year, numTries))
                if numTries >= MAX_NUM_TRIES:
                    failedToGrabData(year)
                    break

                # Get a list of all DAT files on Globus for the given year and store them in a file
                filename_dat_new = '{0}/{1}_GlobusFilesDatNew.txt'.format(GLOBUS_FILE_LIST_DIR, year)
                filename_dat = '{0}/{1}_GlobusFilesDat.txt'.format(GLOBUS_FILE_LIST_DIR, year)
                os.system('globus ls -r \'{0}:/chroot/sddata/dat/{1}\' > {2}'.format(helper.GLOBUS_SUPERDARN_ENDPOINT, year, filename_dat_new))

                # Check that the file list was actually received and stored
                fileSize = os.path.getsize(filename_dat_new)
                if fileSize < MIN_FILE_SIZE:
                    time.sleep(DELAY)
                    numTries += 1
                else:
                    # File is big enough - replace old list file
                    if os.path.isfile(filename_dat):
                        print('Overwriting existing {0} DAT list file'.format(year))
                        os.remove(filename_dat)
                    os.rename(filename_dat_new, filename_dat)
        
        year += 1

    # Create an empty dict to store all radars for each date
    remoteData = {}
    
    files  = glob.glob(os.path.join(GLOBUS_FILE_LIST_DIR, '*GlobusFiles*'))
    for file in files:

        # Go through the file(s) line by line and add each line to the remoteData dict
        with open(file) as mainFileList:
            lines = mainFileList.readlines()        
            for line in lines:
                filename = line.strip()
                extension = filename.split('.')[-1]
                if not extension == 'bz2':
                    # This line isn't a rawACF or DAT filename
                    continue
               
                # Get the day and the radar for the file
                if file.split('.')[0][-3:] == 'Raw':
                    day = filename.split('.')[0].split('/')[-1]
                    radar = filename.split('.')[3]
                elif file.split('.')[0][-3:] == 'Dat':
                    day = filename.split('.')[0].split('/')[-1][:8]
                    radar_letter = filename.split('.')[0].split('/')[-1][10]
                    radar = helper.get_three_letter_radar_id(radar_letter)
                else:
                    raise ValueError('Filename does not match expectations: {0}'.format(filename))

                # Add the current radar to a new date entry if the day doesn't exist in the dict yet
                if day not in remoteData:
                    remoteData[day] = [radar]
                    continue

                # Get the current radar list for the given day, then
                # add the radar to the list
                if radar not in remoteData[day]:
                    remoteData[day].append(radar)

    outputFile = '{0}/globus_data_inventory.json'.format(GLOBUS_FILE_LIST_DIR)
    with open(outputFile, 'w') as outfile:
        json.dump(remoteData, outfile)


def failedToGrabData(year):
    # Send an email and end the script if rsync didn't succeed
    emailSubject = '"Unsuccessful attempt to grab {0} Mirror  Data"'.format(year)
    emailBody    = '"Tried to copy {0} from Mirror {1} times, but did not succeed. \nSee logfile for more details."'.format(year, MAX_NUM_TRIES)
    helper.send_email(emailSubject, emailBody)
    sys.exit(emailBody)


if __name__ == '__main__':
    main()
