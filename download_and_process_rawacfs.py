import sys
import filecmp
import os
import shutil
import datetime
import socket
import time
from dateutil.relativedelta import relativedelta
import helper
import raw_to_nc
import subprocess

DOWNLOAD_SOURCE_FILES = True
DELETE_FITACFS_V2_5 = True
PROCESS_JME_RAWACFS = True

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

def main(date):
    startTime = time.time()
    startDate, endDate = get_first_and_last_days_of_month(date)

    rawDir = startDate.strftime(RAWACF_DIR_FMT) + '/'
    fitDir = startDate.strftime(FITACF_DIR_FMT)
    netDir = startDate.strftime(NETCDF_DIR_FMT)

    os.makedirs(rawDir, exist_ok=True)    
    os.makedirs(fitDir, exist_ok=True)
    os.makedirs(netDir, exist_ok=True)

    if DOWNLOAD_SOURCE_FILES:
        download_source_files(rawDir, netDir, startDate)

    convert_rawacf_to_fitacf_and_netcdf(startDate, endDate, rawDir, fitDir, netDir)

    remove_converted_files(rawDir, fitDir)

    totalTime = helper.getTimeString(time.time() - startTime)
    emailSubject = '"RawACF Download and Conversion Complete"'
    emailBody    = '"Finished downloading and converting {month} RawACF data\nTotal time: {time}"'.format(month = startDate.strftime('%Y/%m'), time = totalTime)
    helper.send_email(emailSubject, emailBody)


def download_source_files(rawDir, netDir, startDate):
    rawDir = startDate.strftime(RAWACF_DIR_FMT)
    netDir = startDate.strftime(NETCDF_DIR_FMT)

    download_files_from_bas(rawDir, netDir, startDate)


def download_files_from_globus(rawDir, netDir, date):
    # Start Globus Connect Personal and establish connection
    # Also allow access to /project/superdarn/data/
    subprocess.call('{0} -start -restrict-paths \'rw~/,rw/project/superdarn/data\' &'.format(helper.GLOBUS_PATH), shell=True)

    # Initiate the transfer from Globus to APL
    subprocess.call('nohup /project/superdarn/software/python-3.8.1/bin/python3 /homes/superdarn/globus/sync_radar_data_globus.py -y {0} -m {1} {2}'.format(date.year, date.month, rawDir), shell=True)

    # Stop Globus Connect Personal
    subprocess.call('{0} -stop'.format(helper.GLOBUS_PATH), shell=True)

    emailSubject = '"{0} rawACF Data Successfully Downloaded"'.format(date.strftime('%Y/%m'))
    emailBody    = '"{0} rawACF source files have been downloaded. Starting conversion to fitACF and netCDF."'.format(date.strftime('%Y/%m'))
    helper.send_email(emailSubject, emailBody)


def download_files_from_bas(rawDir, netDir, startDate):

    basRawDir = startDate.strftime(BAS_RAWACF_DIR_FMT)

    # Make sure the BAS server is reachable
    if not BASServerConnected():
        # Send email if BAS couldn't be reached  
        emailSubject = '"Unable to reach BAS"'
        emailBody    = 'Unable to reach BAS after trying for {hours} hours.'.format(hours = RETRY * DELAY / 3600)
        helper.send_email(emailSubject, emailBody)
        sys.exit('{message}'.format(message = emailBody))

    dateString = startDate.strftime('%Y/%m')
    fileNameDateString = startDate.strftime('%Y_%m')
    print('Downloading {m} rawACFs'.format(m = dateString))
    rsyncLogDir = LOG_DIR + 'BAS_rsync_logs/{yr}'.format(yr = startDate.strftime('%Y'))
    os.makedirs(rsyncLogDir, exist_ok=True)
    rsyncLogFilename = '{dir}/BAS_rsync_{month}.out'.format(dir = rsyncLogDir, month = fileNameDateString)
 
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
    
    # JME rawacf files lead to segmentation faults during make_fit, so skip them until we determine the root cause
    if not PROCESS_JME_RAWACFS:
        os.system('rm {0}*jme*'.format(rawDir))    
        emailSubject = '"JME rawACFs Deleted"'
        emailBody    = '"{date} JME rawACF files deleted"'.format(date = dateString)  
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
    if DELETE_FITACFS_V2_5:
        os.system('rm {0}*v2.5*'.format(fitDir))

    # All rawACFs should have been deleted after the conversion to
    # fitACF was completed. Make sure the rawACF directory is empty
    # except for the YYYYMM.hashes file, then delete the directory.
    if len(os.listdir(rawDir)) == 1:
        shutil.rmtree(rawDir)


def get_first_and_last_days_of_month(date):
    firstDayOfMonth = date.replace(day=1)
    lastDayOfMonth = (firstDayOfMonth + relativedelta(months=1)) - datetime.timedelta(days=1)
    return firstDayOfMonth, lastDayOfMonth 


if __name__ == '__main__':
    args = sys.argv
    
    if len(args) < 2:
        # If no date was passed in, process the previous month
        today = datetime.datetime.now()
        date = today - relativedelta(months=1)
    else:
        date = args[0]
    
    main(date)
