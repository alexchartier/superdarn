import sys
import filecmp
import os
import datetime
import raw_to_nc

MAKE_FIT_VERSION = 2.5

def get_first_and_last_days_of_prev_month():
    now = datetime.datetime.now()
    lastDay = now.replace(day=1) - datetime.timedelta(days=1)
    firstDay = lastDay.replace(day=1)
  

    firstDay = datetime.datetime(2021,7,5,0,0)
    lastDay = datetime.datetime(2021,7,5,0,0)
    return firstDay, lastDay 

def send_email(subject, body, addresses):
    os.system('echo {bd} | mail -s {sub} {addr}'.format(bd = body, sub = subject, addr = addresses))

if not "RSTPATH" in os.environ:
    os.environ['RSTPATH'] = '/project/superdarn/software/rst'

startDate, endDate = get_first_and_last_days_of_prev_month()
dateString = startDate.strftime('%Y/%m')
fileNameDateString = startDate.strftime('%Y_%m')

# Get month of interest in YYYY/MM format
#lastDayOfPrevMonth = get_last_day_of_prev_month()

# Month of interest in YYYY_MM format for use in filename
#fileNameDateString = dateString.replace("/","_")

# Set up email message parameters
emailSubject   = ''
emailBody      = ''
emailAddresses = 'jordan.wiker@jhuapl.edu,jordan.wiker@gmail.com'#,Alex.Chartier@jhuapl.edu'

netcdfDir = '/project/superdarn/data/netcdf/{month}'.format(month = dateString)
#if not os.path.exists(netcdfDir):
#    os.makedirs(netcdfDir)
os.makedirs(netcdfDir, exist_ok=True)

## Save a list of all rawACF files on BAS for the given month and store it in the netcdf directory
#os.system('ssh apl@bslsuperdarnb.nerc-bas.ac.uk ls /sddata/raw/%s > %s/bas_rawacfs_%s.txt' % (dateString, netcdfDir,  fileNameDateString))
## Remove the first line (hashes filename)
#os.system('sed -i \'1d\' %s/bas_rawacfs_%s.txt' % (netcdfDir, fileNameDateString))
#
## Copy all rawACF files from BAS for the given month
#rawacfDir = '/project/superdarn/data/rawacf/%s' % dateString
##if not os.path.exists(rawacfDir):
##    os.makedirs(rawacfDir)
#os.makedirs(rawacfDir, exist_ok=True)
#
#numTries = 0
#maxNumSyncTries = 3
#rsyncSuccess = False
#while numTries < maxNumSyncTries:
#    os.system('nohup rsync -r -v apl@bslsuperdarnb.nerc-bas.ac.uk:/sddata/raw/%s/ %s >& ~/logs/BAS_rsync_logs/%s_BAS_rsync.out' % (dateString, rawacfDir, fileNameDateString))
#
#    # Check that all files were copied
#    os.system('ls %s > %s/bas_rawacfs_copied_%s.txt' % (rawacfDir, netcdfDir, fileNameDateString))
#
#    basList = "%s/bas_rawacfs_%s.txt" % (netcdfDir, fileNameDateString)
#    aplList = "%s/bas_rawacfs_copied_%s.txt" % (netcdfDir, fileNameDateString)
#  
#    # Compare the list of files on BAS to the list of copied files at APL
#    result = filecmp.cmp(basList, aplList, shallow=False)
#
#    # If the BAS file list matches the APL file list, the rsync succeeded and the rawACFs are
#    # ready to be processed
#    if result == 0:
#        rsyncSuccess = True
#        break
#    
#    numTries += 1
#
## If the rsync did not succeed, send a notification email and end the script
#if not rsyncSuccess:
#    emailSubject = '"Unsuccessful attempt to copy %s BAS rawACF Data"' % dateString
#    emailBody    = '"Tried to copy %s rawACFs from BAS %i times, but did not succeed."' % (dateString, maxNumSyncTries)
#    send_email(emailSubject, emailBody, emailAddresses)
#    sys.exit('%s' % emailBody)
#    
## Send a notification email saying the rsync succeeded
#emailSubject = '"%s BAS rawACF Data Successfully Copied"' % dateString
#emailBody    = '"%s rawACF files from BAS have been copied. Starting conversion to netCDF."' % dateString    
#os.system('rm %s/bas_rawacfs_copied_%s.txt' % (netcdfDir, fileNameDateString))
#send_email(emailSubject, emailBody, emailAddresses)
   
# Convert the rawACF files to netCDF
#startDate, endDate = get_first_and_last_days_of_month(lastDayOfPrevMonth)
# os.system('nohup /project/superdarn/software/python-3.8.1/bin/python3 /homes/superdarn/superdarn/raw_to_nc.py {startDate} {stopDate} /project/superdarn/data/rawacf/%Y/%m/ /project/superdarn/data/fitacf/%Y/%m/ /project/superdarn/data/netcdf/%Y/%m/ >& ~/logs/rawACF_to_netCDF_logs/rawACF_to_netCDF_{date}.log'.format(startDate = startDateString, stopDate = stopDateString, date = fileNameDateString))
original_stdout = sys.stdout
with open('../logs/raw_to_nc.txt', 'w') as f:
    sys.stdout = f
    raw_to_nc.main(startDate, endDate, '/project/superdarn/data/rawacf/%Y/%m/','/project/superdarn/data/fitacf/%Y/%m/','/project/superdarn/data/netcdf/%Y/%m/',MAKE_FIT_VERSION)
    sys.stdout = original_stdout

emailSubject = '"%s rawACF to netCDF Successful"' % dateString
emailBody    = '"Finished converting %s rawACF files to netCDF"' % dateString

send_email(emailSubject, emailBody, emailAddresses)







