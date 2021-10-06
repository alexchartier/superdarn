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

def send_email(subject, body, addresses = EMAIL_ADDRESSES):
    os.system('echo {bd} | mail -s {sub} {addr}'.format(bd = body, sub = subject, addr = addresses))


def get_radar_list():
    radarList = ['ade','adw','bks','cve','cvw','cly','fhe','fhw','gbr',
    'han','hok','hkw','inv','jme','kap','ksr','kod','lyr','pyk','pgr',
    'rkn', 'sas', 'sch', 'sto', 'wal','bpk','dce','fir','hal','ker',
    'mcm','san','sps','sye','sys','tig','unw','zho']
    return radarList