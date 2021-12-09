"""
run_meteorproc.py

Loop through all the days and radars, processing the bzipped fitACFs into meteor winds
Use hardware.dat files to identify the beam configurations

"""

import numpy as np
import datetime as dt
import os
import glob
# import bz2
from sd_utils import get_random_string, get_radar_list, id_beam_north, id_hdw_params_t, get_radar_params
import sys
import pdb


def meteorproc(
        starttime=dt.datetime(2016, 1, 1), 
        endtime=dt.datetime(2020, 11, 1), 
        fit_fname_fmt='/project/superdarn/data/fit/%Y/%m/%Y%m%d',
        wind_fname_fmt='/project/superdarn/data/meteorwind/%Y/%m/%Y%b%d',
        run_dir='./run_mw/',
        meteorproc_exe='/project/superdarn/software/rst/bin/meteorproc',
        cfit_exe='/project/superdarn/software/rst/bin/make_cfit',
        hdw_dat_dir='/project/superdarn/software/rst/tables/superdarn/hdw/',
        skip_existing=False,
):
    time = starttime
    radar_list = get_radar_params(hdw_dat_dir)
    while time < endtime:
        for radar_name, hdw_params in radar_list.items():
            print(radar_name)
            # get hardware parameters
            hdw_params = id_hdw_params_t(time, hdw_params)

            # specify input filenames
            fit_fname_regex = time.strftime(fit_fname_fmt) + '.%s.*.fit' % radar_name 
            fit_flist = glob.glob(fit_fname_regex)

            # Skip nonexistent files
            if len(fit_flist) == 0:
                print('Not found: %s' % fit_fname_regex)
                continue
            fit_flist.sort()

            fit_fname = fit_flist[0]

            hdw_dat_fname = glob.glob(os.path.join(hdw_dat_dir, '*%s*' % radar_name))[0]

            # loop over meridional and zonal
            for mz_flag in ['m', 'z']:
                print(mz_flag)

                # specify output filename
                wind_fname = time.strftime(wind_fname_fmt) + '.%s.%s.txt' % (radar_name, mz_flag)

                if (os.path.isfile(wind_fname) & skip_existing):
                    print('wind file already exists')
                    continue

                # beam_num = id_beam_north(hdw_params)
                # find_middle_beam
                beam_num = int(hdw_params['maxbeams'] / 2)

                # skip radars with no good beam
                if np.isnan(beam_num):  
                    print('No valid beam')
                    continue


                # Convert file to a wind
                fit_to_wind(
                    time, fit_fname, beam_num, wind_fname, meteorproc_exe, 
                    cfit_exe, mz_flag,
                )

        time += dt.timedelta(days=1)


def fit_to_wind(
        day, fit_fname, beam_num, wind_fname, meteorproc_exe, cfit_exe, 
        mz_flag='m', cfit_fname='tmp.cfit',
):
    
    # Convert fit to cfit
    os.system('%s %s > %s' % (cfit_exe, fit_fname, cfit_fname))

    # Convert cfit to  wind
    os.makedirs(os.path.dirname(wind_fname), exist_ok=True)
    cmd = '%s -bm %i -mz %s %s > %s' % \
        (meteorproc_exe, beam_num, mz_flag, cfit_fname, wind_fname)
    print(cmd)
    os.system(cmd)
    print('written to %s' % wind_fname)


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
    args = sys.argv
    assert len(args) == 5, 'Should have 4x args, e.g.:\n' + \
        'python3 run_meteorproc.py 2016,1,1 2017,1,1 ' + \
        '/project/superdarn/data/fitacf/%Y/%m/%Y%m%d  ' + \
        '/project/superdarn/data/meteorwind/%Y/%m/%Y%b%d \n'

    clobber = False
    if (len(args) > 5) and (args[5] == 'clobber'):
        clobber = True

    stime = dt.datetime.strptime(args[1], '%Y,%m,%d')
    etime = dt.datetime.strptime(args[2], '%Y,%m,%d')
    run_dir = './run/%s' % get_random_string(4) 

    meteorproc(
        starttime=stime, 
        endtime=etime, 
        fit_fname_fmt=args[3], 
        wind_fname_fmt=args[4],
    )


