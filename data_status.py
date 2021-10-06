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

DELAY = 300 # 5 minutes
RETRY = 12 # Try to connect for an hour
TIMEOUT = 10 # seconds

DAT_START_DATE = dt.datetime(1993,9,29)
DAT_END_DATE = dt.datetime(2005,12,31)
BAS_START_DATE = dt.datetime(2006,1,1)
BAS_END_DATE = dt.datetime.now()

BAS_FILE_LIST_DIR = '/homes/superdarn/BAS_files/'
BAS_SERVER = helper.BAS_SERVER
BAS_RAWACF_DIR_FMT = helper.BAS_RAWACF_DIR_FMT
BAS_DAT_DIR_FMT = helper.BAS_DAT_DIR_FMT 

def main():
    radarList = helper.get_radar_list()
    getBasFileList()

    date = BAS_START_DATE
    while date <= BAS_END_DATE:
        print('Comparing data on {day}\n'.format(date = date))
        for radar in radarList:
            basDataExists = bas_data(date, radar)
            aplDataExists = apl_data(date, radar)
            update_data_status(date, radar, basDataExists, aplDataExists)        
                
        date += dt.timedelta(days=1)

    os.system('rm -rf {bas_dir}'.format(BAS_FILE_LIST_DIR))

def update_data_status(date, radar, bas, apl):
    # 0: No data exists
    # 1: Data exists only on BAS
    # 2: Data exists only at APL
    # 3: Data exists at both BAS and APL
    result = bas + apl

    
    print(result)

    # Store result for date in json file

def bas_data(date, radar):
    # Make sure the BAS server is reachable
    if not BASServerConnected():
        # Send email if BAS couldn't be reached  
        emailSubject = '"Unable to reach BAS"'
        emailBody    = 'Unable to reach BAS after trying for {hours} hours.'.format(hours = RETRY * DELAY / 3600)
        helper.send_email(emailSubject, emailBody)
        sys.exit('{message}'.format(message = emailBody))
    

    
    dateString = date.strftime('%Y%m%d')
    os.system('ssh apl@{bas} ls'.format())

    os.system('ssh apl@{bas} ls /sddata/raw/{date} > {ncDir}bas_rawacfs_{dateSuffix}.txt'.format(bas = BAS_SERVER, date = dateString, ncDir = netDir, dateSuffix = fileNameDateString))

    os.system("rsync -avhe ssh --include '*/' --include '%s*' --exclude '*' %s %s" % (dateString, tdirs['bas'], tdirs['rawacf']))



def apl_data(date, radar):
    print()

def getBasFileList():
    radarList = helper.get_radar_list()
    os.makedirs(BAS_FILE_LIST_DIR, exist_ok=True)

    year = BAS_START_DATE.strftime('%Y')
    endYear = BAS_END_DATE.strftime('%Y')
    getBasFileList()    

    while year <= endYear:
        filename = '{dir}/{yr}_basRawFiles.txt'.format(dir = BAS_FILE_LIST_DIR, yr = year)

        # Get a list of all rawACF files on BAS for the given year and put them in a file
        os.system('ssh apl@{bas} ls -R /sddata/raw/{yr}/ > {fname}'.format(bas = helper.BAS_SERVER, fname = filename))

        # Go through the file line by line and add each line to the appropriate daily text file
        with open(filename) as mainFileList:
            lines = mainFileList.readlines()        
            for line in lines:
                rawFilename = line.strip()
                extension = rawFilename.split('.')[-1]
                if not extension == '.bz2':
                    # This line isn't a rawACF filename
                    breakpoint()
                    continue

                dayFileList = '{day}.txt'.format(day = rawFilename.split('.')[0])
                with open(dayFileList, "a+") as fp: 
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