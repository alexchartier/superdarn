#!/usr/bin/env python
"""Automate the conversion of a series of SuperDARN dat files to rawacf files"""

import pdb
import sys
import string
import random
import numpy as np
import datetime as dt
sys.path.append('/homes/chartat1/fusionpp/src/nimo/')
import jdutil
import shutil
import nc_utils
import os
import glob
import bz2

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2020, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"


def main(
    start_time=dt.datetime(1993, 9, 29, 14),
    end_time=dt.datetime(1993, 12, 31, 23),
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
        'from: %s to %s' % (start_time.strftime('%Y/%m/%d/%H'),
                            end_time.strftime('%Y/%m/%d/%H')),
        'Input directory:   %s' % start_time.strftime(in_dir),
        'Output directory.: %s' % start_time.strftime(out_dir),
        'Run directory:     %s' % run_dir,
    ))

    run_dir = os.path.abspath(run_dir)
    
    # Loop over time
    time = start_time
    while time <= end_time:
        # Get all radar sites for the current hour
        radar_list = get_single_letter_radar_list(time.strftime(in_dir))

        for radar in radar_list:
            in_fname_format = time.strftime(os.path.join(in_dir, '%Y%m%d%H' + '*%s*.dat.bz2' % radar))
            three_letter_radar = get_three_letter_radar_id(radar)
            out_fname = time.strftime(out_dir + '%Y%m%d%H.' + '%s.rawacf' % three_letter_radar)
            out_compressed_fname = out_fname + ".bz2"
            
            if os.path.isfile(out_fname):
                print("File exists: %s" % out_compressed_fname)
                if clobber:
                    print('overwriting')
                else:
                    print('skipping')
                    continue
            convert_file(in_fname_format, out_fname, run_dir)
        time += dt.timedelta(hours=1)


def convert_file(in_fname_format, out_fname, run_dir):
    """
    Convert all dat files that match the specified format to rawacf

    If there are multiple files for the same hour, combine them into a single
    file before converting to rawacf
    """

    in_fnames = glob.glob(in_fname_format)

    if len(in_fnames) == 0:
        print('No files in %s' % in_fname_format)
        return 1

    # Clean up the run directory
    os.makedirs(run_dir, exist_ok=True)
    os.chdir(run_dir)
    os.system('rm -rf %s/*' % run_dir)

    # Set up storage directory
    out_dir = os.path.dirname(out_fname)
    os.makedirs(out_dir, exist_ok=True)

    # Copy the input file from the input directory to the run directory and
    # attempt to preserve metadata (i.e. copy2 instead of copy)
    for in_fname in in_fnames:
        shutil.copy2(in_fname, run_dir)
        in_fname_compressed = os.path.join(run_dir, os.path.basename(in_fname))
         # Decrompress the file
        os.system('bzip2 -d %s' % in_fname_compressed)


    # Combine multiple dat files if there are more than one for the same hour
    os.system('cat *.dat > combined.dat')

    # Convert the dat file to rawacf
    os.system('dattorawacf combined.dat > %s' % (out_fname))

    # Verify that the converted rawacf file is large enough to be viable
    fn_inf = os.stat(out_fname)
    if fn_inf.st_size < 1E5:
        os.remove(out_fname)
        print('rawacf %s is too small, size %1.1f MB' % (out_fname, fn_inf.st_size / 1E6))
    else:
        print('rawacf created at %s, size %1.1f MB' % (out_fname, fn_inf.st_size / 1E6))
    
    # Compress the new rawacf file
    os.system('bzip2 -z %s' % out_fname)


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

        items = os.path.basename(f).split('.')
        if len(items) == 3:
            # The radar indicator is always the letter after the hour value
            radar_letter = items[0][10]
        else:
            raise ValueError('filename does not match expectations: %s' % f)

        if radar_letter not in radar_list:
            radar_list.append(radar_letter)
            print('%02d: %s' % (i, radar_letter))
            i += 1
    print('\n')
    return radar_list

def get_three_letter_radar_id(radar_letter):
    """Convert a single-letter radar ID to a three-letter ID"""

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
    """Return a random string of lowercase letters"""

    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str

if __name__ == '__main__':
    args = sys.argv
    assert len(args) >= 5, 'Should have at least 4x args, e.g.:\n' + \
       'python3 dat_to_rawacf.py 1993,1,1,0 1994,1,1,23 ' + \
       '/project/superdarn/data/dat/%Y/%m/  ' + \
       '/project/superdarn/data/rawacf/%Y/%m/ \n' + \
       'optionally add clobber flag at the end'

    clobber = False
    if (len(args) > 5) and (args[5] == 'clobber'):
       clobber = True

    start_time = dt.datetime.strptime(args[1], '%Y,%m,%d,%H')
    end_time = dt.datetime.strptime(args[2], '%Y,%m,%d,%H')
    run_dir = './run/%s' % get_random_string(4)
    main(start_time, end_time, run_dir, args[3], args[4], clobber=clobber)
