import filecmp
import os
import datetime

def get_date_string(now):
    '''Return the month before the current month in 'YYYY/MM' format'''
    previousMonth = now - datetime.timedelta(weeks=4)
    dateString = "%s/%02d" % (previousMonth.year, previousMonth.month)
    return dateString

# Get month of interest in YYYY/MM format
dateString = get_date_string(datetime.datetime.now())

# Month of interest in YYYY_MM format for use in filename
fileNameDateString = dateString.replace("/","_")

# Save a list of all rawACF files on BAS for the given month and store it in the netcdf directory 
netcdf_dir = '/project/superdarn/data/netcdf/%s' % dateString
if not os.path.exists(netcdf_dir):
    os.makedirs(netcdf_dir)
os.system('ssh apl@bslsuperdarnb.nerc-bas.ac.uk ls /sddata/raw/%s > %s/bas_rawacfs_%s.txt' % (dateString, netcdf_dir,  fileNameDateString))
os.system('sed -i \'1d\' %s/bas_rawacfs_%s.txt' % (netcdf_dir, fileNameDateString))

# Copy all rawACF files from BAS for the given month
rawacf_dir = '/project/superdarn/data/rawacf/%s' % dateString
if not os.path.exists(rawacf_dir):
    os.makedirs(rawacf_dir)
os.system('nohup rsync -r -v apl@bslsuperdarnb.nerc-bas.ac.uk:/sddata/raw/%s/ %s >& ~/logs/BAS_rsync_logs/BAS_%s.out' % (dateString, rawacf_dir, fileNameDateString))

# Check that all files were copied
os.system('ls %s > %s/bas_rawacfs_copied_%s.txt' % (rawacf_dir, netcdf_dir, fileNameDateString))

basList = "%s/bas_rawacfs_%s.txt" % (netcdf_dir, fileNameDateString)
aplList = "%s/bas_rawacfs_copied_%s.txt" % (netcdf_dir, fileNameDateString)
  
result = filecmp.cmp(basList, aplList, shallow=False)

email_subject   = ''
email_body      = ''
email_addresses = 'jordan.wiker@jhuapl.edu,Alex.Chartier@jhuapl.edu'

if result == 0:
    email_subject = '"%s BAS rawACF Data Successfully Copied"' % dateString
    email_body    = '%s rawACF files from BAS have been copied. \nStarting conversion to netCDF.' % dateString
else:
    email_subject = '"Unsuccessful attempt to copy %s BAS rawACF Data"' % dateString
    email_body    = 'RawACF file list from %s on BAS do not match the list of copied files to %s' % (dateString, rawacf_dir)
    
os.system('rm %s/bas_rawacfs_copied_%s.txt' % (netcdf_dir, fileNameDateString))
os.system('echo %s | mail -s %s %s' % (email_body, email_subject, email_addresses))

# Convert the rawACF files to netCDF
os.system('nohup python3 /homes/superdarn/superdarn/raw_to_nc.py 2021,04,01 2021,04,30 /project/superdarn/data/rawacf/%Y/%m/  /project/superdarn/data/fitacf/%Y/%m/  /project/superdarn/data/netcdf/%Y/%m/ >& ~/logs/rawACF_to_netCDF_logs/rawACF_to_netCDF_2021_04.log')

email_subject = '"%s rawACF to netCDF Successful"' % dateString
email_body    = 'Finished converting %s rawACF files to netCDF' % dateString

os.system('echo %s | mail -s %s %s' % (email_body, email_subject, email_addresses))
