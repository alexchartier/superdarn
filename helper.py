#!/usr/bin/env python
"""
Helper functions for SuperDARN processing scripts
"""
import os

EMAIL_ADDRESSES = 'jordan.wiker@jhuapl.edu'#,Alex.Chartier@jhuapl.edu'

# Directories
BAS_SERVER = 'bslsuperdarnb.nerc-bas.ac.uk'
BAS_RAWACF_DIR_FMT = '/sddata/raw/%Y/%m/'   
BAS_DAT_DIR_FMT = '/sddata/dat/%Y/%m/'
RAWACF_DIR_FMT = '/project/superdarn/data/rawacf/%Y/%m/'
FITACF_DIR_FMT = '/project/superdarn/data/fitacf/%Y/%m/'
NETCDF_DIR_FMT = '/project/superdarn/data/netcdf/%Y/%m/'
LOG_DIR = '/homes/superdarn/logs/'
FIT_NET_LOG_DIR = '/homes/superdarn/logs/rawACF_to_netCDF_logs/%Y/fitACF_to_netCDF_logs/'

def send_email(subject, body, addresses = EMAIL_ADDRESSES):
    os.system('echo {bd} | mail -s {sub} {addr}'.format(bd = body, sub = subject, addr = addresses))


def get_radar_list():
    radarList = ['ade','adw','bks','cve','cvw','cly','fhe','fhw','gbr',
    'han','hok','hkw','inv','jme','kap','ksr','kod','lyr','pyk','pgr',
    'rkn', 'sas', 'sch', 'sto', 'wal','bpk','dce','fir','hal','ker',
    'mcm','san','sps','sye','sys','tig','unw','zho']
    return radarList

def getTimeString(time):
    day = time // (24 * 3600)
    time = time % (24 * 3600)
    hour = time // 3600
    time %= 3600
    minute = time // 60

    dayString = 'day' if int(day) == 1 else 'days'
    hourString = 'hour' if int(hour) == 1 else 'hours'
    minuteString = 'minute' if int(minute) == 1 else 'minutes'

    return '%d %s, %d %s, %d %s' % (day, dayString, hour, hourString, minute, minuteString)
