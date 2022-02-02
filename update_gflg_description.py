"""
update_gflg_description.py

Update the gflg description to only include 0 or 1
"""  

import netCDF4 as nc
import sys, os
import datetime as dt
from dateutil.relativedelta import relativedelta
import helper
import glob

START_DATE = dt.datetime(2021, 11, 1)
END_DATE = dt.datetime(2019, 6, 1)

def main():
    date = START_DATE
    while date >= END_DATE:

        emailSubject = '"Starting to update netCDF gflg descriptions"'
        emailBody    = 'Starting to update netCDF gflg descriptions for {0}'.format(date.strftime('%Y%m'))
        helper.send_email(emailSubject, emailBody)

        netcdfDir = date.strftime(helper.NETCDF_DIR_FMT)
        fileList = glob.glob(os.path.join(netcdfDir, '*.nc'))
        gflgDescription = 'Ground scatter flag for ACF, 1 - ground scatter, 0 - other scatter'

        for file in fileList:
            fh = nc.Dataset(file, mode='r+')
            fh.variables['gflg'].long_name = gflgDescription
            fh.close()

        emailSubject = '"Finished updated netCDF gflg descriptions"'
        emailBody    = 'Finished updated netCDF gflg descriptions for {0}'.format(date.strftime('%Y%m'))
        helper.send_email(emailSubject, emailBody)

        date -= relativedelta(months=1)


if __name__ == '__main__':
    main()
