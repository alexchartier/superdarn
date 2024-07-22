"""
"""

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2023, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

from datetime import datetime, timedelta
from glob import glob
import sys
import time
import get_rawacfs
import convert_rawacf_to_fitacf
import convert_fitacf_to_netcdf
import convert_fitacf_to_grid_netcdf
import convert_fitacf_to_meteorwind
import os
import helper
import download_and_process_fitacfs
import download_and_process_fitacf_to_meteor
import download_and_process_rawacfs
#import upload_fit_nc_to_zenodo
#import upload_grid_nc_to_zenodo

def main(start_date, end_date):
    """
    Process rawACF files for a range of dates into fitACFs, grids, and meteorwinds

    Args:
        start_date (datetime): The start date of the range.
        end_date (datetime): The end date of the range.

    Returns:
        None
    """
    date = start_date

    while date <= end_date:
        
        start_time = time.time()
        date_string = date.strftime('%Y%m%d')
        get_rawacfs.main(date_string, 'all', False)
        convert_rawacf_to_fitacf.main(date_string)
        convert_fitacf_to_netcdf.main(date_string)
        convert_fitacf_to_grid_netcdf.main(date_string)
        convert_fitacf_to_meteorwind.main(date_string)
        # delete_rawacfs(date_string)
        print("\n================================================================")
        print(f"It took {helper.get_time_string(time.time() - start_time)} to process {date.strftime('%Y-%m-%d')}")
        print("\n================================================================\n\n")

        date += timedelta(days=1)


def delete_rawacfs(date_string):
    """
    Delete rawacfs for the specified day, except for Wallops files

    Args:
        date_string (str): The date dictating which rawacfs will be deleted.

    Returns:
        None
    """
    date = datetime.strptime(date_string, '%Y%m%d')
    raw_dir = date.strftime(helper.RAWACF_DIR_FMT)
    all_files = glob(os.path.join(raw_dir, f"{date_string}*.rawacf*"))
    files_to_remove = [file for file in all_files if '.wal.' not in file]

    for file_path in files_to_remove:
        try:
            os.remove(file_path)
            print(f"Deleted: {file_path}")
        except Exception as e:
            print(f"Error removing {file_path}: {e}")

    print(f"Deletion completed for date: {date_string}")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python3 master_script.py 20210231 20220321')
        sys.exit(1)
    
    start_date_str = sys.argv[1]
    end_date_str = sys.argv[2]
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y%m%d')
        end_date = datetime.strptime(end_date_str, '%Y%m%d')
    except ValueError:
        print('Invalid date format. Please use YYYYMMDD.')
        sys.exit(1)
    
    main(start_date, end_date)
