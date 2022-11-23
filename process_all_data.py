"""
"""

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2022, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

import datetime as dt 
import sys
from dateutil.relativedelta import relativedelta
import os
import helper
import download_and_process_fitacfs
import download_and_process_fitacf_to_meteor
import download_and_process_rawacfs
import upload_nc_to_zenodo

START_DATE = dt.datetime(2015, 12, 1)
END_DATE = dt.datetime(1993, 9, 1)

TWO_FIVE = True
THREE_ZERO = True

def main():
    date = START_DATE
    while date >= END_DATE:

        emailSubject = '"PROCESS ALL STARTING"'
        emailBody    = 'Starting to download and process {0} data'.format(date.strftime('%Y%m'))
        helper.send_email(emailSubject, emailBody)
        
        download_and_process_fitacf_to_meteor.main(date, False, True)
#        upload_nc_to_zenodo.main(date)        

        emailSubject = '"PROCESS ALL COMPLETE"'
        emailBody    = 'Finished downloading and processing {0} data'.format(date.strftime('%Y%m'))
#        helper.send_email(emailSubject, emailBody)

        date -= relativedelta(months=1)

if __name__ == '__main__':
    main()
