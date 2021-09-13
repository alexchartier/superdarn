import sys
import filecmp
import os
import datetime

def get_last_day_of_prev_month():
    now = datetime.datetime.now()
    lastDayOfPrevMonth = now.replace(day=1) - datetime.timedelta(days=1)
    return lastDayOfPrevMonth

def get_date_string(date):
    '''Return the year and month in 'YYYY/MM' format'''
    dateString = "{year:04d}/{month:02d}".format(year = date.year, month = date.month)
    return dateString

def get_first_and_last_days_of_month(date):
    firstDay = '{year:04d},{month:02d},01'.format(year = date.year, month = date.month)
    lastDay = '{year:04d},{month:02d},{day:02d}'.format(year = date.year, month = date.month, day = date.day)
    return firstDay, lastDay 

def send_email(subject, body, addresses):
    os.system('echo {bd} | mail -s {sub} {addr}'.format(bd = body, sub = subject, addr = addresses))

# Get month of interest in YYYY/MM format
lastDayOfPrevMonth = get_last_day_of_prev_month()
dateString = get_date_string(lastDayOfPrevMonth)

# Month of interest in YYYY_MM format for use in filename
fileNameDateString = dateString.replace("/","_")


# Set up email message parameters
emailSubject   = ''
emailBody      = ''
emailAddresses = 'jordan.wiker@jhuapl.edu'#,Alex.Chartier@jhuapl.edu'

os.environ['RSTPATH'] = '/project/superdarn/software/rst'
rstpath = os.getenv('RSTPATH')
assert rstpath, 'RSTPATH environment variable needs to be set'
print(rstpath)
# Convert the rawACF files to netCDF
startDateString, stopDateString = get_first_and_last_days_of_month(lastDayOfPrevMonth)
os.system('nohup /project/superdarn/software/python-3.8.1/bin/python3 /homes/superdarn/superdarn/raw_to_nc.py {startDate} {stopDate} /project/superdarn/data/rawacf/%Y/%m/ /project/superdarn/data/fitacf/%Y/%m/ /project/superdarn/data/netcdf/%Y/%m/ >& ~/logs/rawACF_to_netCDF_logs/rawACF_to_netCDF_{date}.log'.format(startDate = startDateString, stopDate = stopDateString, date = fileNameDateString))

emailSubject = '"%s rawACF to netCDF Successful"' % dateString
emailBody    = '"Finished converting %s rawACF files to netCDF"' % dateString

send_email(emailBody, emailSubject, emailAddresses)







