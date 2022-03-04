"""
"""

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2021, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

import datetime as dt 
import sys
from dateutil.relativedelta import relativedelta
import os
import helper
import download_and_process_rawacfs
import upload_nc_to_zenodo

START_DATE = dt.datetime(2017, 6, 1)
END_DATE = dt.datetime(2017, 6, 1)

LOG_DIR = '{0}rawACF_to_netCDF_logs'.format(helper.LOG_DIR)

def main():
    date = START_DATE
    while date >= END_DATE:
        logDir = '{0}/{1}'.format(LOG_DIR, date.strftime('%Y'))
        os.makedirs(logDir, exist_ok=True)

        emailSubject = '"PROCESS ALL STARTING"'
        emailBody    = 'Starting to download and process {0} data'.format(date.strftime('%Y%m'))
        helper.send_email(emailSubject, emailBody)

        download_and_process_rawacfs.main(date)
        upload_nc_to_zenodo.main(date)        

        emailSubject = '"PROCESS ALL COMPLETE"'
        emailBody    = 'Finished downloading and processing {0} data'.format(date.strftime('%Y%m'))
        helper.send_email(emailSubject, emailBody)

        date -= relativedelta(months=1)

if __name__ == '__main__':
    main()
