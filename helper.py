#!/usr/bin/env python
"""
Helper functions for SuperDARN processing scripts
"""
import os
import time
import re
from datetime import datetime
from glob import glob

EMAIL_ADDRESSES = 'jordan.wiker@jhuapl.edu'#,Alex.Chartier@jhuapl.edu'

LATEST_PUBLIC_DATA = 2022

# Directories
BAS_SERVER = 'bslsuperdarnb.nerc-bas.ac.uk'
WAL_SERVER = 'radar@38.124.149.234'
BAS_RAWACF_DIR_FMT = '/sddata/raw/%Y/%m'   
BAS_DAT_DIR_FMT = '/sddata/dat/%Y/%m'
GLOBUS_RAWACF_DIR_FMT = '/chroot/sddata/dat/%Y/%m'
GLOBUS_DAT_DIR_FMT = '/chroot/sddata/dat/%Y/%m/'
RAWACF_DIR_FMT = '/project/superdarn/data/rawacf/%Y/%m'
FITACF_DIR_FMT = '/project/superdarn/data/fitacf/%Y/%m'
FIT_NC_DIR_FMT = '/project/superdarn/data/netcdf/%Y/%m'
METEORWIND_DIR_FMT = '/project/superdarn/data/meteorwind/%Y/%m'
METEORWIND_DIR_TEST_FMT = '/project/superdarn/data/meteorwind_test/%Y/%m'
METEORWIND_NC_DIR_FMT = '/project/superdarn/data/meteorwindnc/%Y/%m'
GRID_DIR_FMT = '/project/superdarn/data/grid/%Y/%m'
GRID_NC_DIR_FMT = '/project/superdarn/data/grid_nc/%Y/%m'
LOG_DIR = '/project/superdarn/logs'
PROCESSING_ISSUE_DIR = '/project/superdarn/processing_issues/%Y/%m'
FIT_NET_LOG_DIR = '/project/superdarn/logs/fitACF_to_netCDF_logs/%Y'
GLOBUS_PATH = '/homes/superdarn/globusconnectpersonal-3.2.2/globusconnectpersonal'
BAS_FILE_LIST_DIR = '/project/superdarn/data/data_status/BAS_files'
GLOBUS_FILE_LIST_DIR = '/project/superdarn/data/data_status/Globus_files'
ZENODO_FILE_LIST_DIR = '/project/superdarn/data/data_status/zenodo_files'
MIRROR_FILE_LIST_DIR = '/project/superdarn/data/data_status/mirror_files'
DATA_STATUS_DIR = '/project/superdarn/data/data_status'
HDW_DAT_DIR = '/project/superdarn/software/rst/tables/superdarn/hdw'
METEORPROC_EXE = '/project/superdarn/software/apl_rst/bin/meteorproc'
CFIT_EXE = '/project/superdarn/software/apl_rst/bin/make_cfit'

MIN_FITACF_FILE_SIZE = 1E5 # bytes

DEPOSIT_URL = 'https://zenodo.org/api/deposit/depositions'
SANDBOX_DEPOSIT_URL = 'https://sandbox.zenodo.org/api/deposit/depositions'

ZENODO_TOKEN = 'RT4wr3kTsZkEgwWC4r99VTytmGqzULUzloRqn8nVirg2e5nGBYxw4Ohy5FUf'
ZENODO_SANDBOX_TOKEN = '9FWXXWi1NYeEo6c7zarVtOEOzUkPwiwgVNJ6FD2Wyzecf3PNrs1HKKnrDjYS'

GLOBUS_SUPERDARN_ENDPOINT = '8e844226-2eea-479c-b5e4-bac908b725bc'

def send_email(subject, body, addresses = EMAIL_ADDRESSES):
    os.system('echo {bd} | mail -s {sub} {addr}'.format(bd = body, sub = subject, addr = addresses))


def get_radar_list():
    radarList = ['ade','adw','bks','cve','cvw','cly','fhe','fhw','gbr',
    'han','hok','hkw','inv','jme','kap','ksr','kod','lyr','pyk','pgr',
    'rkn', 'sas', 'sch', 'sto', 'wal','bpk','dce','dcn','fir','hal','ker',
    'mcm','san','sps','sye','sys','tig','unw','zho']
    return radarList

def get_time_string(time):
    """Returns a string describing the duration in a human-readable format.

    Args:
        time: The duration in seconds.

    Returns:
        A string describing the duration in a human-readable format.
    """
    days = int(time // (24 * 3600))
    time = time % (24 * 3600)
    hours = int(time // 3600)
    time %= 3600
    minutes = int(time // 60)
    seconds = int(time % 60)

    time_components = []
    if days > 0:
        time_components.append(f"{days} {'day' if days == 1 else 'days'}")
    if hours > 0:
        time_components.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes > 0:
        time_components.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    if seconds > 0:
        time_components.append(f"{seconds} {'second' if seconds == 1 else 'seconds'}")

    return ", ".join(time_components)

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
        2018: 'https://doi.org/10.20383/101.0290',
        2019: 'https://doi.org/10.20383/102.0558',
        2020: 'https://doi.org/10.20383/103.0573',
        2021: 'https://doi.org/10.20383/102.0677',
        2022: 'https://doi.org/10.20383/103.0893'
    }

    return DOIs[year]

def get_three_letter_radar_id(radar_letter):
    """Convert a single-letter radar ID to a three-letter ID"""

    # Original dat file naming format was YYYYMMDDHHS.dat
    # (year, month, day, hour, station identifier). We switched to three-letter
    # identifiers as the number of radar sites grew
    radar_ids = {
        "x": "tst",
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
        "q": "fir",
        "i": "wal"
    }

    return radar_ids[radar_letter]

def check_remaining_zenodo_requests(response):
    rate_limit_remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
    rate_limit_reset = int(response.headers.get("X-RateLimit-Reset", 0))

    # Check to see if we've used up our alloted requests
    if rate_limit_remaining == 1:
        current_time = int(time.time())
        sleep_time = rate_limit_reset - current_time
        print("Rate limit about to be exhausted. Waiting for {} seconds...".format(sleep_time))
        time.sleep(sleep_time)

def get_rawacf_radar_sites_for_date(date_string):
    """
    Get a list of radar sites for a given date in a specified directory.

    Args:
        date_string (str): The date in 'YYYYMMDD' format.
        directory (str): The directory path where the files are located.

    Returns:
        List[str]: A list of unique radar sites found in the directory for the given date.
    """
    date = datetime.strptime(date_string, '%Y%m%d')
    raw_dir = date.strftime(RAWACF_DIR_FMT)
    files = glob(os.path.join(raw_dir, f"{date_string}*rawacf"))    

    radar_sites = []
    for file in files:
        match = re.search(r'\.([a-z]+(?:\.[a-z]+)*)\.', file)
        if match:
            radar_sites.append(match.group(1))

    # Remove duplicates from the list.
    return list(set(radar_sites))
