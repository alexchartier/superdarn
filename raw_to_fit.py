import os
import sys
import glob
import bz2 
sys.path.append('/homes/chartat1/fusionpp/src/nimo/')
import nc_utils
import shutil
import jdutil
import pdb 
import datetime as dt
import numpy as np
import random
import string


def main(
    starttime = dt.datetime(2016, 1, 1),
    endtime = dt.datetime(2017, 1, 1),
    run_dir = './run10/',
    in_dir='/project/superdarn/data/rawacf/%Y/%m/',
    out_dir='/project/superdarn/alex/cfit/%Y/%m/',
    clobber=False,
):

    print('%s\n%s\n%s\n%s\n%s\n' % (
        'Converting files from rawACF to cFIT',
        'from: %s to %s' % (starttime.strftime('%Y/%m/%d'), endtime.strftime('%Y/%m/%d')),
        'input e.g.: %s' % starttime.strftime(in_dir), 
        'output e.g.: %s' % starttime.strftime(out_dir), 
        'Run: %s' % run_dir, 
    ))
         
    run_dir = os.path.abspath(run_dir)
    # Loop over time
    time = starttime
    while time <= endtime:
        # radar_list = get_old_radar_list(time.strftime(in_dir))
        radar_list = get_radar_list(time.strftime(in_dir))
        for radar in radar_list:
            indirn = os.path.join(in_dir, radar)  # for old setup
            # in_fname_fmt = time.strftime(os.path.join(indirn, '%Y%m%d' + '*%s*.rawacf.bz2' % radar))
            in_fname_fmt = time.strftime(os.path.join(in_dir, '%Y%m%d' + '*%s*.rawacf.bz2' % radar))
            cfit_fname = time.strftime(out_dir + '%Y%m%d.' + '%s.cfit' % radar)
            if os.path.isfile(cfit_fname):
                print("File exists: %s" % cfit_fname)
                if clobber:
                    print('overwriting')
                else: 
                    print('skipping')
                    continue 
            status = proc_radar(radar, in_fname_fmt, cfit_fname, run_dir)
        time += dt.timedelta(days=1)


def proc_radar(radar, in_fname_fmt, cfit_fname, run_dir):

    # Clean up the run directory
    os.makedirs(run_dir, exist_ok=True)
    os.chdir(run_dir)
    os.system('rm -rf %s/*' % run_dir)

    # Set up storage directory
    out_dir = os.path.dirname(cfit_fname)
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
    os.system('make_cfit tmp.fitacf > %s' % cfit_fname)
    fn_inf = os.stat(cfit_fname)
    if fn_inf.st_size < 1E5:
        os.remove(cfit_fname)
        print('cfit %s too small, size %1.1f MB' % (cfit_fname, fn_inf.st_size / 1E6))
    else:
        print('cfit created at %s, size %1.1f MB' % (cfit_fname, fn_inf.st_size / 1E6))
    return 0


def get_old_radar_list(in_dir):
    print('Calculating list of radars')
    flist = os.listdir(in_dir)   # Rob has the radars packaged individually 
    return flist
    

def get_radar_list(in_dir):
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
        'python3 raw_to_fit.py 2016,1,1 2017,1,1 ' + \
        '/project/superdarn/data/rawacf/%Y/%m/  ' + \
        '/project/superdarn/alex/cfit/%Y/%m/ \n' + \
        'optionally add clobber flag at the end'

    clobber = False
    if (len(args) > 5) and (args[5] == 'clobber'):
        clobber = True

    stime = dt.datetime.strptime(args[1], '%Y,%m,%d')
    etime = dt.datetime.strptime(args[2], '%Y,%m,%d')
    run_dir = './run_%s' % get_random_string(4) 
    main(stime, etime, run_dir, args[3], args[4], clobber=clobber)






