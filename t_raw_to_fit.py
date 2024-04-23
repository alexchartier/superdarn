import pdb
import numpy as np
import datetime as dt
import jdutil
import shutil
import nc_utils
import os
import sys
import glob
import bz2
sys.path.append('/homes/chartat1/fusionpp/src/nimo/')


def main(
    starttime=dt.datetime(2005, 6, 10),
    endtime=dt.datetime(2005, 6, 30),
    run_dir='./run311/',
    in_dir='/project/superdarn/data/rawacf/%Y/%Y%m%d/',
    out_dir='/project/superdarn/jordan/cfit/%Y/%m/',
):

    run_dir = os.path.abspath(run_dir)
    # Loop over time
    time = starttime
    while time <= endtime:
        # radar_list = get_old_radar_list(time.strftime(in_dir))
        radar_list = get_radar_list(time.strftime(in_dir))
        for radar in radar_list:
            # indirn = os.path.join(in_dir, radar)  # for old setup
            # in_fname_fmt = time.strftime(os.path.join(indirn, '%Y%m%d' + '*%s*.rawacf.bz2' % radar))
            in_fname_fmt = time.strftime(os.path.join(
                in_dir, '%Y%m%d' + '*%s*.rawacf.bz2' % radar))
            cfit_fname = time.strftime(out_dir + '%Y%m%d.' + '%s.cfit' % radar)
            if os.path.isfile(cfit_fname):
                print("File exists - skipping %s" % cfit_fname)
            else:
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
        print('cfit %s too small, size %1.1f MB' %
              (cfit_fname, fn_inf.st_size / 1E6))
    else:
        print('cfit created at %s, size %1.1f MB' %
              (cfit_fname, fn_inf.st_size / 1E6))
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


if __name__ == '__main__':
    main()
