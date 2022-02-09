#!/usr/bin/env python
"""
Helper functions for SuperDARN processing scripts
"""
import os

EMAIL_ADDRESSES = 'jordan.wiker@jhuapl.edu'#,Alex.Chartier@jhuapl.edu'

# TODO: Update this once 2019 data is allowed to be released publically
LATEST_PUBLIC_DATA = 2018

# Directories
BAS_SERVER = 'bslsuperdarnb.nerc-bas.ac.uk'
BAS_RAWACF_DIR_FMT = '/sddata/raw/%Y/%m/'   
BAS_DAT_DIR_FMT = '/sddata/dat/%Y/%m/'
GLOBUS_RAWACF_DIR_FMT = '/chroot/sddata/dat/%Y/%m/'
GLOBUS_DAT_DIR_FMT = '/chroot/sddata/dat/%Y/%m/'
RAWACF_DIR_FMT = '/project/superdarn/data/rawacf/%Y/%m/'
FITACF_DIR_FMT = '/project/superdarn/data/fitacf/%Y/%m/'
NETCDF_DIR_FMT = '/project/superdarn/data/netcdf/%Y/%m/'
LOG_DIR = '/project/superdarn/logs/'
FIT_NET_LOG_DIR = '/homes/superdarn/logs/rawACF_to_netCDF_logs/%Y/fitACF_to_netCDF_logs/'
GLOBUS_PATH = '/homes/superdarn/globusconnectpersonal-3.1.6/globusconnectpersonal'

DEPOSIT_URL = 'https://zenodo.org/api/deposit/depositions'
SANDBOX_DEPOSIT_URL = 'https://sandbox.zenodo.org/api/deposit/depositions'

ZENODO_TOKEN = 'RT4wr3kTsZkEgwWC4r99VTytmGqzULUzloRqn8nVirg2e5nGBYxw4Ohy5FUf'
ZENODO_SANDBOX_TOKEN = '9FWXXWi1NYeEo6c7zarVtOEOzUkPwiwgVNJ6FD2Wyzecf3PNrs1HKKnrDjYS'

GLOBUS_SUPERDARN_ENDPOINT = 'c02cb494-1515-11e9-9f9f-0a06afd4a22e'

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


def getDOI(year):
    """Get the DOI for a given year of SuperDARN data stored on FRDR"""

    DOIs = {
        1993: 'https://doi.org/10.20383/102.0471',
        1994: 'https://doi.org/10.20383/102.0470',
        1995: 'https://doi.org/10.20383/102.0469',
        1996: 'https://doi.org/10.20383/102.0468',
        1997: 'https://doi.org/10.20383/102.0467',
        1998: 'https://doi.org/10.20383/102.0466',
        1999: 'https://doi.org/10.20383/102.0465',
        2000: 'https://doi.org/10.20383/102.0464',
        2001: 'https://doi.org/10.20383/102.0463',
        2002: 'https://doi.org/10.20383/102.0462',
        2003: 'https://doi.org/10.20383/102.0461',
        2004: 'https://doi.org/10.20383/102.0460',
        2005: 'https://doi.org/10.20383/102.0457',
        2006: 'https://doi.org/10.20383/102.0456',
        2007: 'https://doi.org/10.20383/102.0455',
        2008: 'https://doi.org/10.20383/102.0454',
        2009: 'https://doi.org/10.20383/102.0453',
        2010: 'https://doi.org/10.20383/102.0452',
        2011: 'https://doi.org/10.20383/102.0451',
        2012: 'https://doi.org/10.20383/102.0450',
        2013: 'https://doi.org/10.20383/102.0449',
        2014: 'https://doi.org/10.20383/102.0448',
        2015: 'https://doi.org/10.20383/102.0447',
        2016: 'https://doi.org/10.20383/102.0446',
        2017: 'https://doi.org/10.20383/101.0289',
        2018: 'https://doi.org/10.20383/101.0290'
    }

    return DOIs[year]

def get_three_letter_radar_id(radar_letter):
    """Convert a single-letter radar ID to a three-letter ID"""

    # Original dat file naming format was YYYYMMDDHHS.dat
    # (year, month, day, hour, station identifier). We switched to three-letter
    # identifiers as the number of radar sites grew
    radar_ids = {
        "g": "gbr",
        "s": "sch",
        "k": "kap",
        "h": "hal",
        "t": "sas",
        "b": "pgr",
        "a": "kod",
        "w": "sto",
        "e": "pyk",
        "f": "han",
        "d": "san",
        "j": "sys",
        "n": "sye",
        "r": "tig",
        "p": "ker",
        "c": "ksr",
        "u": "unw",
        "m": "mcm",
        "q": "fir" 
    }

    return radar_ids[radar_letter]