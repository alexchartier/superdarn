import sys
import filecmp
import os
import shutil
import datetime
import socket
import time
from dateutil.relativedelta import relativedelta
import helper
#import raw_to_nc
import fit_to_nc
import raw_to_fit
import run_meteorproc
import fit_to_grid_nc
import upload_nc_to_zenodo
import meteorproc_to_nc
import subprocess

def main(date):
    startTime = time.time()
    startDate, endDate = get_first_and_last_days_of_month(date)

    rawDir = startDate.strftime(helper.RAWACF_DIR_FMT) + '/'
    fitDir = startDate.strftime(helper.FITACF_DIR_FMT)
    netDir = startDate.strftime(helper.NETCDF_DIR_FMT)

    os.makedirs(rawDir, exist_ok=True)    
    os.makedirs(fitDir, exist_ok=True)
    os.makedirs(netDir, exist_ok=True)

    # Copy the files from Wallops
    subprocess.call('scp -r \'radar@38.124.149.234:/borealis_nfs/borealis_data/rawacf_dmap/{year}{month}*\' /project/superdarn/data/rawacf/{year}/{month}'.format(year = startDate.strftime('%Y'), month = startDate.strftime('%m')), shell=True)

    convert_rawacf_to_fitacf_and_netcdf(startDate, endDate, rawDir, fitDir, netDir)
#    upload_nc_to_zenodo.main()  

    totalTime = helper.getTimeString(time.time() - startTime)
    emailSubject = '"RawACF Download and Conversion Complete"'
    emailBody    = '"Finished downloading and converting {month} Wallops RawACF data\nTotal time: {time}"'.format(month = startDate.strftime('%Y/%m'), time = totalTime)
    helper.send_email(emailSubject, emailBody)


def convert_rawacf_to_fitacf_and_netcdf(startDate, endDate, rawDir, fitDir, netDir):
    from sd_utils import get_random_string
    runDir = '/project/superdarn/run/%s' % get_random_string(4)
    raw_to_fit.main(startDate, endDate, rawDir, fitDir)
    fit_to_nc.main(startDate, endDate, fitDir, netDir, 2.5)
    fit_to_nc.main(startDate, endDate, fitDir, netDir, 3.0)
    
    # Remove the fitACF 2.5 files
    os.system('rm {0}/*v2.5*'.format(fitDir))
    os.system('rm {0}/*.txt'.format(fitDir))

    fitFilenameFormat = fitDir + '/%Y%m%d'
    windDir = startDate.strftime(helper.METEORWIND_DIR_FMT)
    windncDir = startDate.strftime(helper.METEORWINDNC_DIR_FMT)
    windFilenameFormat = windDir + '/%Y%b%d'
    run_meteorproc.main(startDate, endDate, fitFilenameFormat, windFilenameFormat)
    meteorproc_to_nc.convert_winds(startDate, endDate, windDir, windncDir)

    fit_to_grid_nc.main(startDate, endDate)    

    dateString = startDate.strftime('%Y/%m')

    emailSubject = '"{date} rawACF to netCDF Conversion Successful"'.format(date = dateString)
    emailBody    = 'Finished converting {date} rawACF files to fitACF and netCDF'.format(date = dateString)
    helper.send_email(emailSubject, emailBody)


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

        # Process current month
#        date = today
    else:
        date = args[0]
    
    main(date)
