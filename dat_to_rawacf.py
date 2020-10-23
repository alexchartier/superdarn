#!/usr/bin/env python
"""Automate the conversion of a series of SuperDARN dat files to rawacf files"""

import pdb
import string
import random
import numpy as np
import datetime as dt
import jdutil
import shutil
import nc_utils
import os
import sys
import glob
import bz2

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2020, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"


def main(
    start_time=dt.datetime(1993, 9, 29),
    end_time=dt.datetime(1993, 9, 30),
    run_dir='./run/',
    in_dir='/project/superdarn/data/dat/%Y/%m/',
    out_dir='/project/superdarn/jordan/rawacf/%Y/%m/',
    clobber=False,
):
    """Convert dat files to rawacf files
    
    Iterate over the specified interval and convert the dat files in the 
    input directory to rawacf files and save them in the output directory. 
    If a file already exists in the output directory, only overwrite it if 
    clobber is True. Otherwise, skip it.
    """

    print('%s\n%s\n%s\n%s\n%s\n' % (
        'Converting files from dat to rawACF',
        'from: %s to %s' % (start_time.strftime('%Y/%m/%d'),
                            end_time.strftime('%Y/%m/%d')),
        'Input directory:   %s' % start_time.strftime(in_dir),
        'Output directory.: %s' % start_time.strftime(out_dir),
        'Run directory:     %s' % run_dir,
    ))

    run_dir = os.path.abspath(run_dir)
    
    # Loop over time
    time = start_time
    while time <= end_time:
        # Get all file names for the current day
        in_fname_format = time.strftime(os.path.join(in_dir, '%Y%m%d**.' + 'dat.bz2'))
        in_fnames = glob.glob(in_fname_format)

        # The extra letter that's appended to some files (e.g. 
        # 1993092915ta.dat.bz2, 1993092915tb.dat.bz2, 1993092915t.dat.bz2) causes
        # a problem because it'll look at the 't' to create one rawacf for that time,
        # and then when it sees another one it will skip it because a corresponding 
        # rawacf already exists. So try:
        # Search in_fnames for files that are duplicate for the first 11 characters,
        # then decompress and combine them using cat
        # to make sure it's in the right order, add all of them to a python list
        # using glob.glob, then sort the list, then do 
        #   cat list > rawacf
        # 

        for in_fname in in_fnames:
            in_fname_decompressed = '.'.join(in_fname.split('.')[:-1])
            out_fname = generate_output_filename(in_fname_decompressed, time.strftime(out_dir))

            if os.path.isfile(out_fname):
                print("File exists: %s" % out_fname)
                if clobber:
                    print('overwriting')
                else:
                    print('skipping')
                    continue
            convert_file(in_fname, out_fname, run_dir)

        time += dt.timedelta(days=1)


def convert_file(in_fname, out_fname, run_dir):

    # Clean up the run directory
    os.makedirs(run_dir, exist_ok=True)
    os.chdir(run_dir)
    os.system('rm -rf %s/*' % run_dir)

    # Set up storage directory
    out_dir = os.path.dirname(out_fname)
    os.makedirs(out_dir, exist_ok=True)

    # Copy the input file from the input directory to the run directory and
    # attempt to preserve metadata (i.e. copy2 instead of copy)
    shutil.copy2(in_fname, run_dir)

    # Rename the file using the run directory instead of input directory
    in_fname_compressed = os.path.join(run_dir, os.path.basename(in_fname))
    
    # Decrompress the file
    os.system('bzip2 -d %s' % in_fname_compressed)

    # Set the decompressed file name
    in_fname_decompressed = '.'.join(in_fname_compressed.split('.')[:-1])
    
    # Convert the dat to rawacf
    os.system('dattorawacf %s > %s' % (in_fname_decompressed, out_fname))
    
    # Compress the newly created rawacf file
    os.system('bzip2 -z %s' % out_fname)


def generate_output_filename(input_filename, out_dir):
    # Input filename should be of the form `YYYYMMDDHHS.dat`
    in_fname = os.path.basename(input_filename)
    components = in_fname.split('.')
    if len(components) == 2:
        time = components[0][:10]

        # The radar indicator is always the letter after the hour value
        radar_letter = components[0][10]
    else:
        raise ValueError('filename does not match expectations: %s' % f)

    out_fname = '.'.join([time, get_three_letter_radar_id(radar_letter), 'rawacf'])
    out_name_full = os.path.join(out_dir, out_fname)

    return out_name_full



def get_single_letter_radar_list(in_dir):
    """Determine all radar stations represented in the input directory"""

    print('\nRadars in current directory')
    print('------------')
    assert os.path.isdir(in_dir), 'Directory not found: %s' % in_dir
    file_list = glob.glob(os.path.join(in_dir, '*.bz2'))

    if len(file_list) == 0:
        print('No files in %s' % in_dir)
    radar_list = []

    i = 1
    for f in file_list:
        items = f.split('.')
        if len(items) == 3:
            # The radar indicator is always the letter after the hour value
            radar_letter = items[0][10]
        else:
            raise ValueError('filename does not match expectations: %s' % f)

        if radar_name not in radar_list:
            radar_list.append(radar_letter)
            print('%02d: %s' % (i, radarn))
            i += 1
        print('\n')
    return radar_list

def get_three_letter_radar_id(radar_letter):
    # Original dat file naming format was YYYYMMDDHHS.dat
    # (year, month, day, hour, station identifier). We switched to three-letter
    # identifiers as the number of radar sites grew
    radar_ids = {
        "g": "gbr",
        "s": "sch",
        "k": "kap",
        "h": "hal",
        "t": "sas",
        "b": "pgr",
        "a": "kod",
        "w": "sto",
        "e": "pyk",
        "f": "han",
        "d": "san",
        "j": "sys",
        "n": "sye",
        "r": "tig",
        "p": "ker",
        "c": "ksr",
        "u": "unw",
        "m": "mcm",
        "q": "fir" 
    }

    return radar_ids[radar_letter]


def get_random_string(length):
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str


if __name__ == '__main__':
    # args = sys.argv
    # assert len(args) >= 5, 'Should have at least 4x args, e.g.:\n' + \
    #     'python3 dat_to_rawacf.py 1993,1,1 1994,1,1 ' + \
    #     '/project/superdarn/data/dat/%Y/%m/  ' + \
    #     '/project/superdarn/data/rawacf/%Y/%m/ \n' + \
    #     'optionally add clobber flag at the end'

    # clobber = False
    # if (len(args) > 5) and (args[5] == 'clobber'):
    #     clobber = True

    # start_time = dt.datetime.strptime(args[1], '%Y,%m,%d')
    # end_time = dt.datetime.strptime(args[2], '%Y,%m,%d')
    # run_dir = './run_%s' % get_random_string(4)
    # main(start_time, end_time, run_dir, args[3], args[4], clobber=clobber)
    main()
