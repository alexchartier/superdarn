import sys
import glob
import filecmp
import os
import shutil
import datetime
import socket
import time
from dateutil.relativedelta import relativedelta
import helper
import fit_to_nc
import run_meteorproc
import fit_to_grid_nc
import subprocess

def main(date, two_five, three_zero):
    # Capture the start time in order to caluclate total processing time
    startTime = time.time()
    
    startDate, endDate = get_first_and_last_days_of_month(date)

    fitDir = startDate.strftime(helper.FITACF_DIR_FMT)
    meteorWindDir = startDate.strftime(helper.METEORWIND_DIR_FMT)

    os.makedirs(fitDir, exist_ok=True)
    os.makedirs(meteorWindDir, exist_ok=True)

    # fitACF 2.5
    if two_five:
        download_fitacfs_from_globus(fitDir, startDate, 'fitacf_25')
        convert_fitacf_to_meteor_wind_and_gridnc(startDate, endDate, fitDir, meteorWindDir, 2.5)
#        remove_converted_files(fitDir)


    # fitACF 3.0 (speckled)
    if three_zero:
        download_fitacfs_from_globus(fitDir, startDate, 'fitacf_30')
        convert_fitacf_to_meteor_wind_and_gridnc(startDate, endDate, fitDir, meteorWindDir, 3.0)
        # remove_converted_files(fitDir)
        # os.rmdir(fitDir)


    totalTime = helper.getTimeString(time.time() - startTime)
    emailSubject = '"FitACF Download and Conversion Complete"'
    emailBody    = '"Finished downloading and converting {month} fitACF data\nTotal time: {time}"'.format(month = startDate.strftime('%Y/%m'), time = totalTime)
    helper.send_email(emailSubject, emailBody)


def download_fitacfs_from_globus(fitDir, date, pattern):
    # Start Globus Connect Personal and establish connection
    # Also allow access to /project/superdarn/data/
    subprocess.call('{0} -start -restrict-paths \'rw~/,rw/project/superdarn/data/fitacf\' &'.format(helper.GLOBUS_PATH), shell=True)
    
    # Initiate the Globus -> APL transfer
    subprocess.run(['nohup', '/software/python-3.11.4/bin/python3', 
                    '/homes/superdarn/superdarn/globus/sync_radar_data_globus.py',
                    '-y', str(date.year), '-m', str(date.month), '-t', pattern, fitDir])

    # emailSubject = '"{0} {1} Data Successfully Downloaded"'.format(date.strftime('%Y/%m'), pattern)
    # emailBody    = '"{0} {1} source files have been downloaded. Starting conversion to netCDF."'.format(date.strftime('%Y/%m'), pattern)
    # helper.send_email(emailSubject, emailBody)


def convert_fitacf_to_meteor_wind_and_gridnc(startDate, endDate, fitDir, windDir, fitVersion):

    combine_fitacfs(startDate, endDate, fitDir, fitVersion)

    fitFilenameFormat = fitDir + '/%Y%m%d'
    windFilenameFormat = windDir + '/%Y%b%d'
    run_meteorproc.main(startDate, endDate, fitFilenameFormat, windFilenameFormat)
   # fit_to_grid_nc.main(startDate, endDate)

    dateString = startDate.strftime('%Y/%m')
    emailSubject = '"{date} fitACF to meteor wind Conversion Successful"'.format(date = dateString)
    emailBody    = 'Finished converting {date} fitACF files to meteor wind'.format(date = dateString)
    helper.send_email(emailSubject, emailBody)


def combine_fitacfs(startTime, endTime, fitDir, fitVersion):
    
    print('Combining fitACF files')

    # Loop through the fitACF files one day at a time
    time = startTime
    while time <= endTime:
        if not os.path.isdir(fitDir):
            time += relativedelta(months=1)
            print('%s not found - skipping' % fitDir)
            continue

        radar_list = get_radar_list(fitDir)
        for radar in radar_list:
            inFilenameFormat = time.strftime(os.path.join(fitDir, '%Y%m%d*{0}*fitacf.bz2'.format(radar)))

            outputFilename = time.strftime(os.path.join(fitDir, '%Y%m%d.{0}.v{1}.fit'.format(radar, fitVersion)))

            if os.path.isfile(outputFilename):
                print("File exists: %s\n" % outputFilename)
                print('Skipping')
                continue

            status = combine_files(inFilenameFormat, outputFilename, fitVersion)

        time += datetime.timedelta(days=1)


def combine_files(inFilenameFormat, outputFilename, fitVersion):

    # Set up storage directory
    outDir = os.path.dirname(outputFilename)
    os.makedirs(outDir, exist_ok=True)

    # Make fitacfs for the day
    zippedInputFiles = glob.glob(inFilenameFormat)
    if len(zippedInputFiles) == 0:
        print('No files in %s' % inFilenameFormat)
        return 1

    unzippedInputFileFormat = '.'.join(inFilenameFormat.split('.')[:-1])
    print('Unzipped File Format: {0}'.format(unzippedInputFileFormat))

    # Unzip the files that match the specified format
    for inputFitacf in zippedInputFiles:
        os.system('bzip2 -d {0}'.format(inputFitacf))

    # Combine the unzipped fitACFs for the given day
    combinedFile = os.path.join(outDir, 'combined.fit')
    os.system('cat {0} > {1}'.format(unzippedInputFileFormat, combinedFile))   
 
    shutil.move(combinedFile, outputFilename)

    # Make sure the combined fitACF is large enough
    fn_inf = os.stat(outputFilename)
    if fn_inf.st_size < helper.MIN_FITACF_FILE_SIZE:
        print('File %s too small, size %1.1f MB' % (outputFilename, fn_inf.st_size / 1E6))
        os.system('rm {0}'.format(outputFilename))
    else: 
        print('File created at %s, size %1.1f MB' % (outputFilename, fn_inf.st_size / 1E6))

    #os.system('rm {0}'.format(unzippedInputFileFormat))
        
    return 0

def get_first_and_last_days_of_month(date):
    firstDayOfMonth = date.replace(day=1)
    lastDayOfMonth = (firstDayOfMonth + relativedelta(months=1)) - datetime.timedelta(days=1)
    return firstDayOfMonth, lastDayOfMonth 

def get_radar_list(in_dir):
    print('Calculating list of radars')
    assert os.path.isdir(in_dir), 'Directory not found: %s' % in_dir
    flist = glob.glob(os.path.join(in_dir, '*.bz2'))

    if len(flist) == 0:
        print('No files in %s' % in_dir)
    radar_list = []

    for f in flist:
        items = f.split('.')
        if len(items) == 6:
            radarn = items[3]
        elif len(items) == 7:
            if 'despeck' in f:
                radarn = items[3]
            else:
                radarn = '.'.join(items[3:5])
        elif len(items) == 8:
            radarn = '.'.join(items[3:5])
        else:
            raise ValueError('filename does not match expectations: %s' % f)
        if radarn not in radar_list:
            radar_list.append(radarn)
            print(radarn)
    return radar_list

if __name__ == '__main__':
    args = sys.argv
    
    if len(args) < 2:
        # If no date was passed in, process the previous month
        today = datetime.datetime.now()
        date = today - relativedelta(months=1)
    else:
        date = args[0]
    
    main(date, True, True)
