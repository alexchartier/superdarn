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
__copyright__ = "Copyright 2022, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

import datetime as dt
import os
import time
import helper
import glob
import json
import requests

DELAY = 300 # 5 minutes
RETRY = 12 # Try to connect for an hour
TIMEOUT = 10 # seconds

REMOVE_REMOTE_FILE_LIST = False

START_DATE = dt.datetime(1993,1,1)
END_DATE = dt.datetime.now()

BAS_FILE_LIST_DIR = '/project/superdarn/data/data_status/BAS_files'
GLOBUS_FILE_LIST_DIR = '/project/superdarn/data/data_status/Globus_files'
DATA_STATUS_DIR = '/project/superdarn/data/data_status'

def main():
    startTime = time.time()
    emailSubject = '"Starting Data Check"'
    emailBody    = 'Starting Globus vs Zenodo data check'
    helper.send_email(emailSubject, emailBody)
    
    getRemoteFileList()
    radarList = helper.get_radar_list()

    date = START_DATE
    data = {}
    while date <= END_DATE:
        day = date.strftime('%Y%m%d')
        data[day] = []
        print('Comparing data between Globus and Zenodo on {d}'.format(d = day))
        for radar in radarList:
            remoteDataExists = remote_data(date, radar)
            zenodoDataExists = zenodo_data(date, radar)
            result = get_result(remoteDataExists, zenodoDataExists)        
 
            data[day].append({
                'radar': radar,
                'result': result
            })
                        
        date += dt.timedelta(days=1)

    outputFile = '{0}/data_status_{1}.txt'.format(DATA_STATUS_DIR, END_DATE.strftime('%Y%m%d'))
    with open(outputFile, 'w') as outfile:
        json.dump(data, outfile)
    
    totalTime = helper.getTimeString(time.time() - startTime)
    emailSubject = '"Data Status Check Complete"'
    emailBody    = '"Finished checking Globus vs Zenodo data.\nTotal check runtime: {0}\nNew JSON file created: {1}"'.format(totalTime, outputFile)
    helper.send_email(emailSubject, emailBody)

    if REMOVE_REMOTE_FILE_LIST:
        os.system('rm -rf {0}'.format(GLOBUS_FILE_LIST_DIR))
    

def get_result(globus, zenodo):
    # Get a numerical result based on the Globus and Zenodo values as follows:
    # 0: No data exists
    # 1: Data exists only on Globus
    # 2: Data exists only on Zenodo
    # 3: Data exists on both Globus and Zenodo
    sources = [zenodo, globus]
    resultBinary = '0b' + ''.join(['1' if source else '0' for source in sources])
    result = int(resultBinary, 2)
    return result


def remote_data(date, radar):
    day = date.strftime('%Y%m%d')
    numRemoteFiles = len(glob.glob('{0}/*{1}**{2}*'.format(GLOBUS_FILE_LIST_DIR, day, radar)))
    return numRemoteFiles > 0


def zenodo_data(date, radar):
    day = date.strftime('%Y%m%d')
    fileStart = '{0}.{1}'.format(day, radar)

    month = date.strftime('%Y-%b')
    response = requests.get('https://zenodo.org/api/records',
                        params={'q': '"SuperDARN data in netCDF format ({0})"'.format(month),
                                'access_token': helper.ZENODO_TOKEN})

    files = response.json()["hits"]["hits"][0].get('files').get('files')
    files = str(files)
    if fileStart in files:
        return True

    # for file in files:
    #     filename = file['key']  # E.g. '20200603.wal.v3.0.nc'
    #     if day in filename and radar in filename:
    #         return True

    return False


def getRemoteFileList():

    os.makedirs(GLOBUS_FILE_LIST_DIR, exist_ok=True)

    year = START_DATE.year
    while year <= END_DATE.year:
        print('\nGetting Globus data for {0}\n'.format(year))

        if year >= 2005:
            # Get a list of all rawACF files on Globus for the given year and store them in a file
            filename_raw = '{0}/{1}_GlobusFilesRaw.txt'.format(GLOBUS_FILE_LIST_DIR, year)
            os.system('globus ls -r \'{0}:/chroot/sddata/raw/{1}\' > {2}'.format(helper.GLOBUS_SUPERDARN_ENDPOINT, year, filename_raw))

        if year <= 2006:
            # Get a list of all DAT files on Globus for the given year and store them in a file
            filename_dat = '{0}/{1}_GlobusFilesDat.txt'.format(GLOBUS_FILE_LIST_DIR, year)
            os.system('globus ls -r \'{0}:/chroot/sddata/dat/{1}\' > {2}'.format(helper.GLOBUS_SUPERDARN_ENDPOINT, year, filename_dat))

        files  = glob.glob(os.path.join(GLOBUS_FILE_LIST_DIR, '*'))
        for file in files:

            # Go through the file(s) line by line and add each line to the appropriate daily text file
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
                        day = filename.split('.')[0]
                        radar = filename.split('.')[3]
                    elif file.split('.')[0][-3:] == 'Dat':
                        day = filename.split('.')[0][:8]
                        radar_letter = filename.split('.')[0][10]
                        radar = helper.get_three_letter_radar_id(radar_letter)
                    else:
                        raise ValueError('Filename does not match expectations: {0}'.format(filename))

                    radarFileList = '{0}/{1}_{2}.txt'.format(GLOBUS_FILE_LIST_DIR, day, radar)
                    with open(radarFileList, "a+") as fp: 
                        fp.write(filename + '\n')

        year += 1

if __name__ == '__main__':
    main()
