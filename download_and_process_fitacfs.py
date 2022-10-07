import sys
import filecmp
import os
import shutil
import datetime
import socket
import time
from dateutil.relativedelta import relativedelta
import helper
import fit_to_nc
import subprocess

DELETE_FITACFS = True

def main(date, two_five, three_zero):
    # Capture the start time in order to caluclate total processing time
    startTime = time.time()
    
    startDate, endDate = get_first_and_last_days_of_month(date)

    fitDir = startDate.strftime(helper.FITACF_DIR_FMT)
    netDir = startDate.strftime(helper.NETCDF_DIR_FMT)

    os.makedirs(fitDir, exist_ok=True)
    os.makedirs(netDir, exist_ok=True)

    # fitACF 2.5
    if two_five:
        download_fitacfs_from_globus(fitDir, startDate, 'fitacf_25')

        convert_fitacf_to_netcdf(startDate, endDate, fitDir, netDir, 2.5)
#        remove_converted_files(fitDir)


    # fitACF 3.0 (speckled)
    if three_zero:
        download_fitacfs_from_globus(fitDir, startDate, 'fitacf_30')

        convert_fitacf_to_netcdf(startDate, endDate, fitDir, netDir, 3.0)
#        remove_converted_files(fitDir)
#        os.rmdir(fitDir)


    totalTime = helper.getTimeString(time.time() - startTime)
    emailSubject = '"FitACF Download and Conversion Complete"'
    emailBody    = '"Finished downloading and converting {month} fitACF data\nTotal time: {time}"'.format(month = startDate.strftime('%Y/%m'), time = totalTime)
    helper.send_email(emailSubject, emailBody)


def download_fitacfs_from_globus(fitDir, date, pattern):
    # Start Globus Connect Personal and establish connection
    # Also allow access to /project/superdarn/data/
    subprocess.call('{0} -start -restrict-paths \'rw~/,rw/project/superdarn/data/fitacf\' &'.format(helper.GLOBUS_PATH), shell=True)

    # Initiate the Globus -> APL transfer
    subprocess.call('nohup /project/superdarn/software/python-3.8.1/bin/python3 /homes/superdarn/globus/sync_radar_data_globus.py -y {0} -m {1} -t {2} {3}'.format(date.year, date.month, pattern, fitDir), shell=True)

    # Stop Globus Connect Personal
    #subprocess.call('{0} -stop'.format(helper.GLOBUS_PATH), shell=True)

    emailSubject = '"{0} {1} Data Successfully Downloaded"'.format(date.strftime('%Y/%m'), pattern)
    emailBody    = '"{0} {1} source files have been downloaded. Starting conversion to netCDF."'.format(date.strftime('%Y/%m'), pattern)
    helper.send_email(emailSubject, emailBody)


def convert_fitacf_to_netcdf(startDate, endDate, fitDir, netDir, fitVersion):

    fit_to_nc.main(startDate, endDate, fitDir, netDir, fitVersion)

    dateString = startDate.strftime('%Y/%m')
    emailSubject = '"{date} fitACF to netCDF Conversion Successful"'.format(date = dateString)
    emailBody    = 'Finished converting {date} fitACF files to netCDF'.format(date = dateString)
    helper.send_email(emailSubject, emailBody)


def remove_converted_files(fitDir):
    if DELETE_FITACFS:
        os.system('rm -rf {0}/*'.format(fitDir))


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
    
    main(date, True, True)
