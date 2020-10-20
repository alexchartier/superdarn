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

def main(
    starttime=dt.datetime(1993, 9, 1),
    endtime=dt.datetime(1993, 12, 31),
    run_dir='./run/',
    in_dir='/project/superdarn/data/dat/%Y/%m/',
    out_dir='/project/superdarn/data/rawacf/%Y/%m/',
    clobber=False,
):

    print('%s\n%s\n%s\n%s\n%s\n' % (
        'Converting files from dat to rawACF',
        'from: %s to %s' % (starttime.strftime('%Y/%m/%d'),
                            endtime.strftime('%Y/%m/%d')),
        'input e.g.: %s' % starttime.strftime(in_dir),
        'output e.g.: %s' % starttime.strftime(out_dir),
        'Run: %s' % run_dir,
    ))



    print('Calculating list of radars')
    assert os.path.isdir(in_dir), 'Directory not found: %s' % in_dir
    flist = glob.glob(os.path.join(in_dir, '*.bz2'))

    if len(flist) == 0:
        print('No files in %s' % in_dir)
    radar_list = []

    for f in flist:
        items = f.split('.')
        if len(items) == 6:
            radarn = items[3]
        elif len(items) == 7:
            radarn = '.'.join(items[3:5])
        else:
            raise ValueError('filename does not match expectations: %s' % f)
        if radarn not in radar_list:
            radar_list.append(radarn)
            print(radarn)
    return radar_list


def get_random_string(length):
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str


if __name__ == '__main__':
    args = sys.argv
    assert len(args) >= 5, 'Should have at least 4x args, e.g.:\n' + \
        'python3 dat_to_raw.py 1993,1,1 1994,1,1 ' + \
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
