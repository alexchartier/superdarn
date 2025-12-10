#!/usr/bin/env python
"""Automate the conversion of SuperDARN dat files to rawacf files"""

import pdb
import sys
import string
import random
import numpy as np
import datetime
sys.path.append('/homes/chartat1/fusionpp/src/nimo/')
import jdutil
import shutil
import nc_utils
from sd_utils import get_random_string
import os
import glob
import helper
import bz2

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2020, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

date = None

def main(dateString, radar='all'):
    """Convert dat files to rawacf files for the given date and radar
    """
    global date
    date = datetime.datetime.strptime(dateString, '%Y%m%d')

    run_dir = os.path.abspath(run_dir)
    
    # Loop over time
    time = start_time
    while time <= end_time:
        rawDir = date.strftime(helper.RAWACF_DIR_FMT)
        datDir = date.strftime(helper.DAT_DIR_FMT)

        # Get all radar sites for the current hour
        radar_list = get_single_letter_radar_list(time.strftime(datDir))

        for radar in radar_list:
            in_fname_format = time.strftime(os.path.join(datDir, '%Y%m%d%H' + '*%s*.dat.bz2' % radar))
            three_letter_radar = helper.get_three_letter_radar_id(radar)
            raw_filename = time.strftime(rawDir + '%Y%m%d%H.' + '%s.rawacf' % three_letter_radar)
            out_compressed_fname = raw_filename + ".bz2"
            
            if os.path.isfile(raw_filename):
                print("File exists: %s" % out_compressed_fname)
                if clobber:
                    print('overwriting')
                else:
                    print('skipping')
                    continue
            convert_file(in_fname_format, raw_filename, run_dir)
        time += dt.timedelta(hours=1)


def convert_file(in_fname_format, raw_filename, run_dir):
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
    rawDir = os.path.dirname(raw_filename)
    os.makedirs(rawDir, exist_ok=True)

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
    os.system('dattorawacf combined.dat > %s' % (raw_filename))

    # Verify that the converted rawacf file is large enough to be viable
    fn_inf = os.stat(raw_filename)
    if fn_inf.st_size < 1E5:
        os.remove(raw_filename)
        print('rawacf %s is too small, size %1.1f MB' % (raw_filename, fn_inf.st_size / 1E6))
    else:
        print('rawacf created at %s, size %1.1f MB' % (raw_filename, fn_inf.st_size / 1E6))
    
        # Compress the new rawacf file
        os.system('bzip2 -z %s' % raw_filename)


def get_single_letter_radar_list(datDir):
    """Determine all radar stations represented in the input directory"""

    print('\nRadars in current directory')
    print('------------')
    assert os.path.isdir(datDir), 'Directory not found: %s' % datDir
    file_list = glob.glob(os.path.join(datDir, '*.bz2'))

    if len(file_list) == 0:
        print('No files in %s' % datDir)
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
    run_dir = './run_rawacf/%s' % get_random_string(4)
    main(start_time, end_time, run_dir, args[3], args[4], clobber=clobber)
