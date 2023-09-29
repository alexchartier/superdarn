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
import concurrent.futures
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
    os.makedirs(fitacf_dir, exist_ok=True)

    # Get all rawACF files for the date
    rawacf_bz2_files = glob(f"{os.path.join(rawacf_dir, date_string)}.*rawacf.bz2")

    # Unpack all compressed files
    print("Unpacking compressed rawACF files...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(unpack_bz2_and_remove, rawacf_bz2_files)

    rawacf_files = glob(f"{os.path.join(rawacf_dir, date_string)}.*rawacf")

    # Create a pool of workers for each version
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit the conversion tasks to the pools
        futures = []
        for rawacf_file in rawacf_files:
            rawacf_filename = os.path.basename(rawacf_file)

            # Convert the RAWACF file to FITACF with version 2.5.
            fitacf_filename = rawacf_filename.replace("rawacf", "fitacf2")
            fitacf_file = os.path.join(fitacf_dir, fitacf_filename)
            futures.append(executor.submit(convert_rawacf_to_fitacf, rawacf_file, fitacf_file, 2.5))

            # Convert the RAWACF file to FITACF with version 3.0.
            fitacf_filename = rawacf_filename.replace("rawacf", "fitacf3")
            fitacf_file = os.path.join(fitacf_dir, fitacf_filename)
            futures.append(executor.submit(convert_rawacf_to_fitacf, rawacf_file, fitacf_file, 3.0))

        # Wait for all tasks to complete
        concurrent.futures.wait(futures)

def convert_rawacf_to_fitacf(rawacf_file, fitacf_file, version):
    """
    Converts a rawACF file to a fitACF file.

    Args:
        rawacf_file: The path to the RAWACF file.
        fitacf_file: The path to the FITACF file to be created.
        version:     The fitACF version (2.5 or 3.0)
    """

    fit_version = "-fitacf2" if version == 2.5 else "-fitacf3"    
    command = f"make_fit {fit_version} {rawacf_file} > {fitacf_file}"
    subprocess.run(command, shell=True)

def unpack_bz2_and_remove(input_file):
    """
    Unpacks a .bz2 compressed file and removes the original compressed file.

    Parameters:
    - input_file (str): The path to the input .bz2 compressed file.

    Returns:
    None
    """
    # Check if the file has the .bz2 extension
    if input_file.endswith('.bz2'):
        # Create the output filename by removing the .bz2 extension
        output_file = input_file.replace(".bz2", "")

        # Open the input and output files
        with bz2.BZ2File(input_file, 'rb') as infile, open(output_file, 'wb') as outfile:
            # Read from the compressed file and write to the output file
            outfile.write(infile.read())

        # Remove the original compressed file
        os.remove(input_file)
    else:
        print(f'Error: {input_file} is not a .bz2 file')


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 convert_rawacf_to_fitacf.py YYYYMMDD")
        sys.exit(1)

    # Extract the day argument in 'YYYYMMDD' format
    date_string = sys.argv[1]

    # Check if the day argument is in the correct format
    if not date_string.isdigit() or len(date_string) != 8:
        print("Date argument must be in 'YYYYMMDD' format.")
        sys.exit(1)

    main(date_string)

