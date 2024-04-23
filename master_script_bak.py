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
import upload_fit_nc_to_zenodo
import upload_grid_nc_to_zenodo

TWO_FIVE = True
THREE_ZERO = True


def main(start_date, end_date):
    date = start_date
    while date >= end_date:

        emailSubject = '"PROCESS ALL STARTING"'
        emailBody = 'Starting to download and process {0} data'.format(
            date.strftime('%Y%m'))
        helper.send_email(emailSubject, emailBody)

        # download_and_process_rawacfs.main(date)
        # download_and_process_fitacf_to_meteor.main(date, TWO_FIVE, THREE_ZERO)
        # download_and_process_fitacfs.main(date, TWO_FIVE, THREE_ZERO)
        # upload_fit_nc_to_zenodo.main(date)
        upload_grid_nc_to_zenodo.main(date)

        date -= relativedelta(months=1)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python3 master_script.py 20220321 20210231')
        sys.exit(1)

    start_date_str = sys.argv[1]
    end_date_str = sys.argv[2]

    try:
        start_date = dt.datetime.strptime(start_date_str, '%Y%m%d')
        end_date = dt.datetime.strptime(end_date_str, '%Y%m%d')
    except ValueError:
        print('Invalid date format. Please use YYYYMMDD.')
        sys.exit(1)

    main(start_date, end_date)
