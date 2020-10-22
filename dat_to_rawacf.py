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
    start_time=dt.datetime(1993, 9, 1),
    end_time=dt.datetime(1993, 12, 31),
    run_dir='./run/',
    in_dir='/project/superdarn/data/dat/%Y/%m/',
    out_dir='/project/superdarn/data/rawacf/%Y/%m/',
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
        radar_list = get_radar_list(time.strftime(in_dir))
        for radar in radar_list:
            in_fname_fmt = time.strftime(os.path.join(
                in_dir, '%Y%m%d' + '*%s*.dat.bz2' % radar))
            rawacf_fname = time.strftime(out_dir + '%Y%m%d.' + '%s.rawacf' % radar)
            if os.path.isfile(rawacf_fname):
                print("File exists: %s" % rawacf_fname)
                if clobber:
                    print('overwriting')
                else:
                    print('skipping')
                    continue
            status = proc_radar(radar, in_fname_fmt, rawacf_fname, run_dir)
        time += dt.timedelta(days=1)


def proc_radar(radar, in_fname_fmt, rawacf_fname, run_dir):

    # Clean up the run directory
    os.makedirs(run_dir, exist_ok=True)
    os.chdir(run_dir)
    os.system('rm -rf %s/*' % run_dir)

    # Set up storage directory
    out_dir = os.path.dirname(rawacf_fname)
    os.makedirs(out_dir, exist_ok=True)

    # Make fitacfs for the day
    in_fnames = glob.glob(in_fname_fmt)
    if len(in_fnames) == 0:
        print('No files in %s' % in_fname_fmt)
        return 1

    for in_fname in in_fnames:
        shutil.copy2(in_fname, run_dir)
        in_fname_t = os.path.join(run_dir, os.path.basename(in_fname))
        os.system('bzip2 -d %s' % in_fname_t)

        in_fname_t2 = '.'.join(in_fname_t.split('.')[:-1])
        out_fname = '.'.join(in_fname_t2.split('.')[:-1]) + '.fitacf'
        os.system('make_fit %s > %s' % (in_fname_t2, out_fname))
    os.system('cat *.fitacf > tmp.fitacf')

    # Create a cfit
    os.system('make_rawacf tmp.fitacf > %s' % rawacf_fname)
    fn_inf = os.stat(rawacf_fname)
    if fn_inf.st_size < 1E5:
        os.remove(rawacf_fname)
        print('rawACF %s is too small (%1.1f MB)' %
              (rawacf_fname, fn_inf.st_size / 1E6))
    else:
        print('rawacf created at %s, size %1.1f MB' %
              (rawacf_fname, fn_inf.st_size / 1E6))
    return 0


def get_radar_list(in_dir):
    """"""
    radar_sites = {
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

    print('Getting list of radars in input directory')
    assert os.path.isdir(in_dir), 'Directory not found: %s' % in_dir
    file_list = glob.glob(os.path.join(in_dir, '*.bz2'))

    if len(file_list) == 0:
        print('No files in %s' % in_dir)
    radar_list = []

# 1993101908t.dat.bz2
    for f in file_list:
        items = f.split('.')
        if len(items) == 3:
            # The radar indicator is always the letter after the hour value
            radar_letter = items[0][10]
            radar_name = 
        else:
            raise ValueError('filename does not match expectations: %s' % f)
        if radar_name not in radar_list:
            radar_list.append(radar_name)
            print(radar_name)
    return radar_list


def get_random_string(length):
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str


if __name__ == '__main__':
    args = sys.argv
    assert len(args) >= 5, 'Should have at least 4x args, e.g.:\n' + \
        'python3 dat_to_rawacf.py 1993,1,1 1994,1,1 ' + \
        '/project/superdarn/data/dat/%Y/%m/  ' + \
        '/project/superdarn/data/rawacf/%Y/%m/ \n' + \
        'optionally add clobber flag at the end'

    clobber = False
    if (len(args) > 5) and (args[5] == 'clobber'):
        clobber = True

    start_time = dt.datetime.strptime(args[1], '%Y,%m,%d')
    end_time = dt.datetime.strptime(args[2], '%Y,%m,%d')
    run_dir = './run_%s' % get_random_string(4)
    main(start_time, end_time, run_dir, args[3], args[4], clobber=clobber)
