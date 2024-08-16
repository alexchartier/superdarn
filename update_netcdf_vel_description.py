#!/usr/bin/env python3
# coding: utf-8
import os
import sys
from glob import glob
import netCDF4
from datetime import datetime
import helper

def main(date_string):

    date = datetime.strptime(date_string, '%Y%m%d')
    fitacf_nc_dir = date.strftime(helper.FIT_NC_DIR_FMT)
    fitacf_nc_files = glob(f"{os.path.join(fitacf_nc_dir, date_string)}.*")

    for netcdf_file in fitacf_nc_files:
        # Open the NetCDF file in append mode
        dataset = netCDF4.Dataset(netcdf_file, 'a')

        print(f"File: {os.path.basename(netcdf_file)}")

        # Access the variable you want to update
        var = dataset.variables['v']

        print(f"Old value: {var.long_name}")

        # Update the value
        new_value = "Line of Sight Velocity (+v = towards the radar)"
        var.long_name = new_value
        print(f"New value: {var.long_name}")

        # Close the file
        dataset.close()

        old_file_path = netcdf_file

        # Skip directories and only process files
        if os.path.isfile(old_file_path):
            # Check and replace 'v2.5' with 'fitacf2'
            if 'v2.5' in old_file_path:
                new_file_path = old_file_path.replace('v2.5', 'fitacf2')
            # Check and replace 'v3.0.despeckled' with 'despeck.fitacf3'
            elif 'v3.0.despeckled' in old_file_path:
                new_file_path = old_file_path.replace('v3.0.despeckled', 'despeck.fitacf3')
            else:
                # If no pattern matches, skip the file
                continue

            # Rename the file
            os.rename(old_file_path, new_file_path)
            print(f"New filename: {os.path.basename(new_file_path)}")


if __name__ == '__main__':

    if len(sys.argv) < 2:
        print("Usage: python3 update_netcdf_vel_description.py YYYYMMDD")
        sys.exit(1)

    # Extract the day argument in 'YYYYMMDD' format
    date_string = sys.argv[1]

    # Check if the day argument is in the correct format
    if not date_string.isdigit() or len(date_string) != 8:
        print("Date argument must be in 'YYYYMMDD' format.")
        sys.exit(1)

    main(date_string)
