#!/usr/bin/env python
"""
Starting at 1993-09-29 and stepping one day at a date
to the present, look at the SuperDARN data stored at APL
vs the SuperDARN data stored on BAS. For each day, 
determine whether no data exists, data exists only on 
BAS, or data exsits on BAS and at APL. Save the results
to a json file.
"""

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2021, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

import datetime as dt 
import socket
import sys
import os
import time
import helper
import glob
import json

DELAY = 300 # 5 minutes
RETRY = 12 # Try to connect for an hour
TIMEOUT = 10 # seconds

DAT_START_DATE = dt.datetime(1993,9,29)
DAT_END_DATE = dt.datetime(2005,12,31)
BAS_START_DATE = dt.datetime(2021,7,21)
BAS_END_DATE = dt.datetime.now()
BAS_END_DATE = dt.datetime(2021,7,22)

BAS_FILE_LIST_DIR = '/project/superdarn/data/data_status/BAS_files'
DATA_STATUS_DIR = '/project/superdarn/data/data_status'
BAS_SERVER = helper.BAS_SERVER
BAS_RAWACF_DIR_FMT = helper.BAS_RAWACF_DIR_FMT
BAS_DAT_DIR_FMT = helper.BAS_DAT_DIR_FMT 

def main():
    radarList = helper.get_radar_list()

    date = BAS_START_DATE
    data = {}
    while date <= BAS_END_DATE:
        day = date.strftime('%Y%m%d')
        data[day] = []
        print('Comparing data on {d}\n'.format(d = day))
        for radar in radarList:
            basDataExists = bas_data(date, radar)
            aplDataExists = apl_data(date, radar)
            result = get_result(basDataExists, aplDataExists)        
 
            data[day].append({
                'radar': radar,
                'result': result
            })
                        
        date += dt.timedelta(days=1)

    with open('{dir}/data_status.txt', 'w') as outfile:
        json.dump(data, outfile)
    os.system('rm -rf {bas_dir}'.format(BAS_FILE_LIST_DIR))
    

def get_result(bas, apl):
    # Get a numerical result as follows:
    # 0: No data exists
    # 1: Data exists only on BAS
    # 2: Data exists only at APL
    # 3: Data exists at both BAS and APL
    sources = [apl, bas]
    resultBinary = '0b' + ''.join(['1' if source else '0' for source in sources])
    result = int(resultBinary, 2)
    return result

def bas_data(date, radar):
    day = date.strftime('%Y%m%d')
    numBASFiles = len(glob.glob('{dir}/*{d}**{r}*'.format(dir = BAS_FILE_LIST_DIR, d = day, r = radar)))
    return numBASFiles > 0



def apl_data(date, radar):
    day = date.strftime('%Y%m%d')
    netDir = date.strftime(helper.NETCDF_DIR_FMT)
    numAPLFiles = len(glob.glob('{dir}*{d}**{r}*'.format(dir = netDir, d = day, r = radar)))
    return numAPLFiles > 0

def getBasFileList():

    # Make sure the BAS server is reachable
    if not BASServerConnected():
        # Send email if BAS couldn't be reached  
        emailSubject = '"Unable to reach BAS"'
        emailBody    = 'Unable to reach BAS after trying for {hours} hours.'.format(hours = RETRY * DELAY / 3600)
        helper.send_email(emailSubject, emailBody)
        sys.exit('{message}'.format(message = emailBody))

    os.makedirs(BAS_FILE_LIST_DIR, exist_ok=True)

    year = BAS_START_DATE.year
    endYear = BAS_END_DATE.year
    while year <= endYear:
        filename = '{dir}/{yr}_basRawFiles.txt'.format(dir = BAS_FILE_LIST_DIR, yr = year)

        # Get a list of all rawACF files on BAS for the given year and put them in a file
        os.system('ssh apl@{bas} ls -R /sddata/raw/{yr}/ > {fname}'.format(bas = helper.BAS_SERVER, yr = year, fname = filename))

        # Go through the file line by line and add each line to the appropriate daily text file
        with open(filename) as mainFileList:
            lines = mainFileList.readlines()        
            for line in lines:
                rawFilename = line.strip()
                extension = rawFilename.split('.')[-1]
                if not extension == 'bz2':
                    # This line isn't a rawACF filename
                    continue
                
                day = rawFilename.split('.')[0]
                # dayDir = '{dir}/{d}'.format(dir = BAS_FILE_LIST_DIR, d = day)
                # os.makedirs(dayDir, exist_ok=True)
                radar = rawFilename.split('.')[3]
                radarFileList = '{dir}/{d}_{r}.txt'.format(dir = BAS_FILE_LIST_DIR, d = day, r = radar)
                with open(radarFileList, "a+") as fp: 
                    fp.write(rawFilename + '\n')

        year += 1

def BASServerConnected():
    BASup = False
    for i in range(RETRY):
        if isOpen(BAS_SERVER, 22):
            BASup = True
            break
        else:
            time.sleep(DELAY)
    return BASup


def isOpen(server, port):
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
    main()
