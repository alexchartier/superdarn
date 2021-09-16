"""
Download and process data one day at a time
"""
import raw_to_nc
import datetime as dt

time = dt.datetime(2015, 9, 19)
dirs  = {
    'rawacf': '/project/superdarn/data/rawacf/%Y/%Y%m%d/',
    'fitacf': '/project/superdarn/data/fitacf/%Y/%m/',
    'netcdf': '/project/superdarn/data/netcdf/%Y/%m/',
    'log': 'logs/',
}
for key, dirn in dirs.items():
    os.makedirs(time.strftime(dirn), exist_ok=True)

dateString = time.strftime('%Y%m%d')
logfn = os.path.join(dirs['log'], 'dl_log.txt')
os.system("rsync -rav -e ssh --include '*/' --include '%s' apl@bslsuperdarnb.nerc-bas.ac.uk:/sddata/raw/ %s" % (dateString, dirs['rawacf']))

raw_to_nc.main(time, time, dirs['rawacf'], dirs['fitacf'], dirs['netcdf'])
