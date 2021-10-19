#!/usr/bin/env python
"""
"""

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2021, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

import datetime as dt 
from dateutil.relativedelta import relativedelta
import sys
import os
import helper
import download_and_process_rawacfs

START_DATE = dt.datetime(2019,2, 1)#dt.datetime.now()
END_DATE = dt.datetime(2018,10, 1)
# END_DATE = dt.datetime(2006,8, 1) # Earlier than this there's a mix of dat and raw, or only dat

LOG_DIR = '{0}rawACF_to_netCDF_logs'.format(helper.LOG_DIR)

def main():
    date = START_DATE
    while date >= END_DATE:
        logDir = '{0}/{1}'.format(LOG_DIR, date.strftime('%Y'))
        logFile = '{0}/download_and_process_{1}'.format(logDir, date.strftime('%Y%m'))
        os.makedirs(logDir, exist_ok=True)

        emailSubject = '"Downloading and Processing {0} Data"'.format(date.strftime('%Y%m'))
        emailBody    = 'Starting to download and process {0} data'.format(date.strftime('%Y%m'))
        helper.send_email(emailSubject, emailBody)

        original_stdout = sys.stdout
        f = open(logFile, 'w')
        sys.stdout = f

        download_and_process_rawacfs.main(date)

        sys.stdout = original_stdout 

        emailSubject = '"Finished Downloading and Processing {0} Data"'.format(date.strftime('%Y%m'))
        emailBody    = 'Finished downloading and processing {0} data'.format(date.strftime('%Y%m'))
        helper.send_email(emailSubject, emailBody)

        date -= relativedelta(months=1)

if __name__ == '__main__':
    main()