#!/usr/bin/env python3
# coding: utf-8
"""
Converts rawACF files to fitACF files
"""
import os
import sys
from glob import glob
from datetime import datetime
import bz2
import multiprocessing
import subprocess
import helper

# Global date variable
date = None

def main(date_string):
    global date
    date = datetime.strptime(date_string, '%Y%m%d')

    print(f'Starting to convert {date_string} rawACF files to fitACF')

    rawacf_dir = date.strftime(helper.RAWACF_DIR_FMT)
    fitacf_dir = date.strftime(helper.FITACF_DIR_FMT)

    # Get all rawACF files for the date
    rawacf_files = glob(f"{os.path.join(rawacf_dir, date_string)}.*")

    # Create a pool of workers for each version
    pool_25 = multiprocessing.Pool()
    pool_30 = multiprocessing.Pool()

    # Submit the conversion tasks to the pools
    for rawacf_file in rawacf_files:
        rawacf_filename = os.path.basename(rawacf_file)

        # Convert the RAWACF file to FITACF with version 2.5.
        fitacf_suffix = f"v2.5.fitacf"
        fitacf_filename = rawacf_filename.replace(".rawacf.bz2", fitacf_suffix)
        fitacf_file = os.path.join(fitacf_dir, fitacf_filename)
        pool_25.apply_async(convert_rawacf_to_fitacf, args=(rawacf_file, fitacf_file, 2.5))

        # Convert the RAWACF file to FITACF with version 3.0.
        fitacf_suffix = f"v3.0.fitacf"
        fitacf_filename = rawacf_filename.replace(".rawacf.bz2", fitacf_suffix)
        fitacf_file = os.path.join(fitacf_dir, fitacf_filename)
        pool_30.apply_async(convert_rawacf_to_fitacf, args=(rawacf_file, fitacf_file, 3.0))

    # Close the pools and wait for all of the tasks to finish.
    pool_25.close()
    pool_25.join()
    pool_30.close()
    pool_30.join()

def convert_rawacf_to_fitacf(rawacf_file, fitacf_file, version):
    """
    Converts a rawACF file to a fitACF file.

    Args:
        rawacf_file: The path to the RAWACF file.
        fitacf_file: The path to the FITACF file to be created.
        version:     The fitACF version (2.5 or 3.0)
    """

    command = f"make_fit -fitacf-version {version} {rawacf_file} > {fitacf_file}"
    subprocess.run(command)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py YYYYMMDD")
        sys.exit(1)

    # Extract the day argument in 'YYYYMMDD' format
    date_string = sys.argv[1]

    # Check if the day argument is in the correct format
    if not date_string.isdigit() or len(date_string) != 8:
        print("Date argument must be in 'YYYYMMDD' format.")
        sys.exit(1)

    main(date_string)