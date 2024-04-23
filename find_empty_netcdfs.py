"""
"""

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2022, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

# import datetime as dt
# import sys
# from dateutil.relativedelta import relativedelta
import os
import netCDF4 as nc
import helper
import subprocess
# import upload_nc_to_zenodo

# START_DATE = dt.datetime.now()
# END_DATE = dt.datetime(1993, 1, 1)


def main():
    # date = START_DATE
    # while date >= END_DATE:

    netcdfDir = '/project/superdarn/data/netcdf'
    logDir = helper.LOG_DIR + 'netCDF_check'
    emptynetcdfLogFile = logDir + '/empty_netCDFs.log'
    summaryLogFile = logDir + '/empty_netCDFs_summary.log'
    numEmptyNetCDFs = 0

#    with open(emptynetcdfLogFile, "a+") as fp:
#        fp.write('Empty NetCDFs\n')

    with open(summaryLogFile, "a+") as fp:
        fp.write('Month                                   Num Empty NetCDFs\n')

    for path, currentDirectory, files in os.walk(netcdfDir):
        print('Current Dir: {0}'.format(path))
        numEmptyNetCDFs = 0
        for file in files:
            # Disregard any non-netCDF files
            if os.path.splitext(file)[-1] == '.nc':
                try:
                    ds = nc.Dataset(os.path.join(path, file))
                except:
                    # If it doesn't open (e.g. "NetCDF: HDF error"), add it to the list of bad files
                    numEmptyNetCDFs += 1
                    with open(emptynetcdfLogFile, "a+") as fp:
                        fp.write(file + ' (HDF error)\n')
                    continue

                numDataPoints = ds.dimensions['npts'].size
                if numDataPoints == 0:
                    numEmptyNetCDFs += 1
                    with open(emptynetcdfLogFile, "a+") as fp:
                        fp.write(file + '\n')

        # if numEmptyNetCDFs != 0:
        # Get 'YYYY-MM' month format
        month = path.split('/')[-2] + '-' + path.split('/')[-1]
        logText = '{0}: {1}\n'.format(month, numEmptyNetCDFs)
        with open(summaryLogFile, "a+") as fp:
            fp.write(logText)

    subprocess.call(
        'sort {0} -o {1}'.format(summaryLogFile, summaryLogFile), shell=True)
    subprocess.call(
        'sort {0} -o {1}'.format(emptynetcdfLogFile, emptynetcdfLogFile), shell=True)


if __name__ == '__main__':
    main()
