#!/usr/bin/env python3
import os
import glob
from datetime import datetime
import helper
import sd_utils

def convert_fitacf_to_meteorwind(date_string):
    """
    Convert fitACF files to meteorwind files for a given date.

    Args:
        date_string (str): Date string in the format 'YYYYMMDD'.
    """
    print(f"Converting fitACF to meteorwind for date: {date_string}")
    date = datetime.strptime(date_string, '%Y%m%d')
    fitacf_dir = date.strftime(helper.FITACF_DIR_FMT)
    meteorwind_dir = date.strftime(helper.METEORWIND_DIR_FMT)

    # Create the meteorwind directory if it doesn't exist
    os.makedirs(meteorwind_dir, exist_ok=True)

    rstpath = os.getenv('RSTPATH')
    assert rstpath, 'RSTPATH environment variable needs to be set'
    hdw_dat_dir = os.getenv('SD_HDWPATH')
    radar_list = sd_utils.get_radar_params(hdw_dat_dir)

    for radar_name in radar_list:
        print(f"Processing radar: {radar_name}")
        fitacf_files = glob.glob(os.path.join(fitacf_dir, f"{date_string}.{radar_name}.fitacf3"))
        print(f"\nfitACF Files: {fitacf_files}")

        for fitacf_file in fitacf_files:
            file_size = os.path.getsize(fitacf_file)
            if file_size < helper.MIN_FITACF_FILE_SIZE:
                print(f"{fitacf_file} is too small ({file_size/(1024 * 1024):.2f} MB) - skipping.")
                continue

            for mz_flag in ['m', 'z']:
                print(f"Processing {mz_flag} component for {fitacf_file}")
                radar_name_with_mode = '.'.join(os.path.basename(fitacf_file).split('.')[1:-1])
                wind_fname_fmt = '%Y%b%d.' + radar_name_with_mode + '.%s.txt'
                wind_fname = os.path.join(meteorwind_dir, date.strftime('%Y%b%d') + f'.{radar_name_with_mode}.{mz_flag}.txt')

                if os.path.isfile(wind_fname):
                    # Check if the existing file contains data
                    with open(wind_fname, 'r') as file:
                        lines = file.readlines()

                    data_lines = [line for line in lines if not line.startswith('#')]
                    if not data_lines:
                        print(f"{os.path.basename(wind_fname)} already exists, but has no data - proceeding to create new file")
                        os.remove(wind_fname)
                    else:
                        print(f"{os.path.basename(wind_fname)} already exists and has data - skipping.")
                        continue

                beam_num = 1
                cfit_fname = 'tmp.cfit'

                # Convert fitacf to cfit
                print(f"Converting fitacf to cfit: {fitacf_file}")
                os.system(f"{helper.CFIT_EXE} {fitacf_file} > {cfit_fname}")

                # Convert cfit to wind
                print(f"Converting cfit to wind: {cfit_fname}")
                cmd = f"{helper.METEORPROC_EXE} -mz {mz_flag} {cfit_fname} > {wind_fname}"
                print(cmd)
                os.system(cmd)
                print(f"Written to {wind_fname}")

                # Check if the created file contains data
                with open(wind_fname, 'r') as file:
                    lines = file.readlines()

                data_lines = [line for line in lines if not line.startswith('#')]
                if not data_lines:
                    print(f"No data found in the created file: {os.path.basename(wind_fname)}. Deleting the file.")
                    os.remove(wind_fname)

                # Clean up temporary cfit file
                os.remove(cfit_fname)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 convert_fitacf_to_meteorwind.py <YYYYMMDD>")
        sys.exit(1)
    date_string = sys.argv[1]
    convert_fitacf_to_meteorwind(date_string)