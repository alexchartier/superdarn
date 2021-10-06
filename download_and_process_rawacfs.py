import sys
import filecmp
import os
import shutil
import datetime
import raw_to_nc
import socket
import time
import helper

DOWNLOAD_RAWACFS = False

DELAY = 1800 # 30 minutes
RETRY = 17   # Try to connect every 30 minutes for a day
TIMEOUT = 10 # seconds

MAX_NUM_RSYNC_TRIES = 3

# Directories
BAS_SERVER = helper.BAS_SERVER
BAS_RAWACF_DIR_FMT = helper.BAS_RAWACF_DIR_FMT        
RAWACF_DIR_FMT = helper.RAWACF_DIR_FMT
FITACF_DIR_FMT = helper.FITACF_DIR_FMT
NETCDF_DIR_FMT = helper.NETCDF_DIR_FMT
LOG_DIR = helper.LOG_DIR

def main():

    startDate, endDate = get_first_and_last_days_of_prev_month()

    basRawDir = startDate.strftime(BAS_RAWACF_DIR_FMT)
    rawDir = startDate.strftime(RAWACF_DIR_FMT)
    fitDir = startDate.strftime(FITACF_DIR_FMT)
    netDir = startDate.strftime(NETCDF_DIR_FMT)

    os.makedirs(rawDir, exist_ok=True)    
    os.makedirs(fitDir, exist_ok=True)
    os.makedirs(netDir, exist_ok=True)
    
    if DOWNLOAD_RAWACFS:
        download_rawacfs(basRawDir, rawDir, netDir, startDate)

    convert_rawacf_to_fitacf_and_netcdf(startDate, endDate, rawDir, fitDir, netDir)

    remove_converted_files(rawDir, fitDir)


def download_rawacfs(basRawDir, rawDir, netDir, startDate):

    # Make sure the BAS server is reachable
    if not BASServerConnected():
        # Send email if BAS couldn't be reached  
        emailSubject = '"Unable to reach BAS"'
        emailBody    = 'Unable to reach BAS after trying for {hours} hours.'.format(hours = RETRY * DELAY / 3600)
        helper.send_email(emailSubject, emailBody)
        sys.exit('{message}'.format(message = emailBody))

    dateString = startDate.strftime('%Y/%m')
    fileNameDateString = startDate.strftime('%Y_%m')
    rsyncLogFilename = LOG_DIR + 'BAS_rsync_logs/{datePrefix}_BAS_rsync.out'.format(datePrefix = fileNameDateString)
 
    # Save a list of all rawACF files on BAS for the given month and store it in the netcdf directory
    os.system('ssh apl@{bas} ls /sddata/raw/{date} > {ncDir}bas_rawacfs_{dateSuffix}.txt'.format(bas = BAS_SERVER, date = dateString, ncDir = netDir, dateSuffix = fileNameDateString))
    # Remove the first line (hashes filename)
    os.system('sed -i \'1d\' {ncDir}bas_rawacfs_{dateSuffix}.txt'.format(ncDir = netDir, dateSuffix = fileNameDateString))
    
    numTries = 0
    rsyncSuccess = False
    while numTries < MAX_NUM_RSYNC_TRIES:
        os.system('nohup rsync -rv apl@{bas}:{basRaw} {aplRaw} >& {logFile}'.format(bas = BAS_SERVER, basRaw = basRawDir, aplRaw = rawDir, logFile = rsyncLogFilename))
    
        # Check that all files were copied
        os.system('ls {aplRaw} > {ncDir}bas_rawacfs_copied_{dateSuffix}.txt'.format(aplRaw = rawDir, ncDir = netDir, dateSuffix = fileNameDateString))
    
        basList = "{ncDir}bas_rawacfs_{dateSuffix}.txt".format(ncDir = netDir, dateSuffix = fileNameDateString)
        aplList = "{ncDir}bas_rawacfs_copied_{dateSuffix}.txt".format(ncDir = netDir, dateSuffix = fileNameDateString)
    
        # Compare the list of files on BAS to the list of copied files at APL
        result = filecmp.cmp(basList, aplList, shallow=False)
    
        # If the BAS file list matches the APL file list, the rsync succeeded and the rawACFs are
        # ready to be processed
        if result == 0:
            rsyncSuccess = True
            break
        
        numTries += 1
    
    # Confirm that the rsync succeeded
    if not rsyncSuccess:
        # Send an email and end the script if rsync didn't succeed
        emailSubject = '"Unsuccessful attempt to copy {date} BAS rawACF Data"'.format(date = dateString)
        emailBody    = '"Tried to copy {date} rawACFs from BAS {num} times, but did not succeed. \nSee {logfile} for more details."'.format(date = dateString, num = MAX_NUM_RSYNC_TRIES, logfile = rsyncLogFilename)
        helper.send_email(emailSubject, emailBody)
        sys.exit('{message}'.format(message = emailBody))
        
    # Send a notification email saying the rsync succeeded
    emailSubject = '"{date} BAS rawACF Data Successfully Downloaded"'.format(date = dateString)
    emailBody    = '"{date} rawACF files from BAS have been downloaded. Starting conversion to fitACF and netCDF."'.format(date = dateString)  
    os.system('rm {ncDir}bas_rawacfs_copied_{dateSuffix}.txt'.format(ncDir = netDir, dateSuffix = fileNameDateString))
    helper.send_email(emailSubject, emailBody)
    

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

def convert_rawacf_to_fitacf_and_netcdf(startDate, endDate, rawDir, fitDir, netDir):

    raw_to_nc.main(startDate, endDate, rawDir,fitDir,netDir)

    dateString = startDate.strftime('%Y/%m')

    emailSubject = '"{date} rawACF to netCDF Conversion Successful"'.format(date = dateString)
    emailBody    = 'Finished converting {date} rawACF files to fitACF and netCDF'.format(date = dateString)
    helper.send_email(emailSubject, emailBody)


def remove_converted_files(rawDir, fitDir):
    
    os.system('rm {fitacfDir}*v2.5*'.format(fitacfDir = fitDir))

    # All rawACFs should have been deleted after the conversion to
    # fitACF was completed. Make sure the rawACF directory is empty,
    # then delete the directory.
    if len(os.listdir(rawDir)) == 0:
        shutil.rmtree(rawDir)


def get_first_and_last_days_of_prev_month():
        now = datetime.datetime.now()
        lastDay = now.replace(day=1) - datetime.timedelta(days=1)
        firstDay = lastDay.replace(day=1)
    

        firstDay = datetime.datetime(2021,7,21,0,0)
        lastDay = datetime.datetime(2021,7,21,0,0)
        return firstDay, lastDay 

if __name__ == '__main__':
    main()
