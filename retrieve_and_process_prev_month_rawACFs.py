import sys
import filecmp
import subprocess
import os
import datetime
import raw_to_nc

EMAIL_ADDRESSES = 'jordan.wiker@jhuapl.edu'#,Alex.Chartier@jhuapl.edu'
MAKE_FIT_VERSION = 2.5
DOWNLOAD_RAWACFS = False
MAX_NUM_RSYNC_TRIES = 3

def main():

    dirs  = {
        'basServer': 'apl@bslsuperdarnb.nerc-bas.ac.uk',
        'basRawacf': 'apl@bslsuperdarnb.nerc-bas.ac.uk:/sddata/raw/%Y/%m/',        
        'rawacf': '/project/superdarn/data/rawacf/%Y/%m/',
        'fitacf': '/project/superdarn/data/fitacf/%Y/%m/',
        'netcdf': '/project/superdarn/data/netcdf/%Y/%m/',
        'log': '/homes/superdarn/logs/'
    }
        
    # if not "RSTPATH" in os.environ:
    #     os.environ['RSTPATH'] = '/project/superdarn/software/rst'

    startDate, endDate = get_first_and_last_days_of_prev_month()
    download_rawacfs(dirs, startDate)
    convert_rawacf_to_fitacf_and_netcdf(startDate, endDate, dirs)

def download_rawacfs(dirs, startDate):
    basServer = dirs['basServer']
    basRawacf = dirs['basRawacf']
    rawacfDir = startDate.strftime(dirs['rawacf'])
    netcdfDir = startDate.strftime(dirs['netcdf'])
    logsDir = dirs['log']

    dateString = startDate.strftime('%Y/%m')
    fileNameDateString = startDate.strftime('%Y_%m')
    rsyncLogFilename = logsDir + '/BAS_rsync_logs/{datePrefix}_BAS_rsync.out'.format(datePrefix = fileNameDateString)

    if DOWNLOAD_RAWACFS:
        # Save a list of all rawACF files on BAS for the given month and store it in the netcdf directory
        os.system('ssh {bas} ls /sddata/raw/{date} > {ncDir}/bas_rawacfs_{dateSuffix}.txt'.format(bas = basServer, date = dateString, ncDir = netcdfDir, dateSuffix = fileNameDateString))
        #TODO: replace os.system with subprocess.call
        # subprocess.call(('ssh {bas} ls /sddata/raw/{date} > '
        #                 '{ncDir}/bas_rawacfs_{dateSuffix}.txt'.
        #                 format(bas = basServer, date = dateString, ncDir = netcdfDir, dateSuffix = fileNameDateString)))

        # Remove the first line (hashes filename)
        os.system('sed -i \'1d\' {ncDir}/bas_rawacfs_{dateSuffix}.txt'.format(ncDir = netcdfDir, dateSuffix = fileNameDateString))
        
        # Copy all rawACF files from BAS for the given month
        # rawacfDir = '/project/superdarn/data/rawacf/%s' % dateString
        # os.makedirs(rawacfDir, exist_ok=True)
        
        numTries = 0
        rsyncSuccess = False
        while numTries < MAX_NUM_RSYNC_TRIES:
            os.system('nohup rsync -rv {basRaw} {rawDir} >& {logFile}'.format(basRaw = basRawacf, rawDir = rawacfDir, logfile = rsyncLogFilename))
        
            # Check that all files were copied
            os.system('ls {rawDir} > {ncDir}/bas_rawacfs_copied_{dateSuffix}.txt'.format(rawDir = rawacfDir, ncDir = netcdfDir, dateSuffix = fileNameDateString))
        
            basList = "{ncDir}/bas_rawacfs_{dateSuffix}.txt".format(ncDir = netcdfDir, dateSuffix = fileNameDateString)
            aplList = "{ncDir}/bas_rawacfs_copied_{dateSuffix}.txt".format(ncDir = netcdfDir, dateSuffix = fileNameDateString)
        
            # Compare the list of files on BAS to the list of copied files at APL
            result = filecmp.cmp(basList, aplList, shallow=False)
        
            # If the BAS file list matches the APL file list, the rsync succeeded and the rawACFs are
            # ready to be processed
            if result == 0:
                rsyncSuccess = True
                break
            
            numTries += 1
        
        # If the rsync did not succeed, send a notification email and end the script
        if not rsyncSuccess:
            emailSubject = '"Unsuccessful attempt to copy {date} BAS rawACF Data"'.format(date = dateString)
            emailBody    = '"Tried to copy {date} rawACFs from BAS {num} times, but did not succeed. \nSee {logfile} for more details."'.format(date = dateString, num = MAX_NUM_RSYNC_TRIES, logfile = rsyncLogFilename)
            send_email(emailSubject, emailBody, EMAIL_ADDRESSES)
            sys.exit('{message}'.format(message = emailBody))
            
        # Send a notification email saying the rsync succeeded
        emailSubject = '"{date} BAS rawACF Data Successfully Copied"'.format(date = dateString)
        emailBody    = '"{date} rawACF files from BAS have been copied. Starting conversion to netCDF."'.format(date = dateString)  
        os.system('rm {ncDir}/bas_rawacfs_copied_{dateSuffix}.txt'.format(ncDir = netcdfDir, dateSuffix = fileNameDateString))
        send_email(emailSubject, emailBody, EMAIL_ADDRESSES)
    

def convert_rawacf_to_fitacf_and_netcdf(startDate, endDate, dirs):

    rawacfDir = startDate.strftime(dirs['rawacf'])
    fitacfDir = startDate.strftime(dirs['fitacf'])
    netcdfDir = startDate.strftime(dirs['netcdf'])

    raw_to_nc.main(startDate, endDate, rawacfDir,fitacfDir,netcdfDir,MAKE_FIT_VERSION)

    dateString = startDate.strftime('%Y/%m')

    emailSubject = '"{date} rawACF to netCDF Conversion Successful"'.format(date = dateString)
    emailBody    = 'Finished converting {date} rawACF files to fitACF and netCDF'.format(date = dateString)
    send_email(emailSubject, emailBody, EMAIL_ADDRESSES)

def get_first_and_last_days_of_prev_month():
        now = datetime.datetime.now()
        lastDay = now.replace(day=1) - datetime.timedelta(days=1)
        firstDay = lastDay.replace(day=1)
    

        firstDay = datetime.datetime(2021,8,5,0,0)
        lastDay = datetime.datetime(2021,8,5,0,0)
        return firstDay, lastDay 

def send_email(subject, body, addresses):
    os.system('echo {bd} | mail -s {sub} {addr}'.format(bd = body, sub = subject, addr = addresses))

if __name__ == '__main__':
    main()