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
from sd_utils import get_random_string, get_radar_list, id_beam_north, id_hdw_params_t
import sys
import pdb


def meteorproc(
        starttime=dt.datetime(2016, 1, 1), 
        endtime=dt.datetime(2020, 11, 1), 
        cfit_fname_fmt='/project/superdarn/data/cfit/%Y/%m/%Y%m%d',
        wind_fname_fmt='/project/superdarn/data/meteorwind/%Y/%m/%Y%b%d',
        run_dir='./run_mw/',
        meteorproc_exe='../rst/bin/meteorproc',
        hdw_dat_dir='../rst/tables/superdarn/hdw/',
        skip_existing=False,
):
    time = starttime
    radar_list = get_radar_params(hdw_dat_dir)
    while time < endtime:
        for radar_name, hdw_params in radar_list.items():
            print(radar_name)
            # specify filenames
            cfit_fname = time.strftime(cfit_fname_fmt) + '.%s.cfit' % radar_name 
            wind_fname = time.strftime(wind_fname_fmt) + '.%s.txt' % radar_name
            hdw_dat_fname = glob.glob(os.path.join(hdw_dat_dir, '*%s*' % radar_name))[0]
            if (os.path.isfile(wind_fname) & skip_existing):
                print('wind file already exists')
                continue

            # get hardware parameters
            hdw_params = id_hdw_params_t(time, hdw_params)
            if hdw_params['glat'] < 0:  # skip SH
                print('SH')
                continue
            beam_num = id_beam_north(hdw_params)

            # skip radars with no beam close to North
            if np.isnan(beam_num):  
                print('No North beam')
                continue

            # Skip nonexistent files
            if not os.path.isfile(cfit_fname):
                print('Not found: %s' % cfit_fname)
                continue

            # Convert file to a wind
            cfit_to_wind(time, cfit_fname, beam_num, wind_fname, meteorproc_exe)
        time += dt.timedelta(days=1)


def cfit_to_wind(day, cfit_fname, beam_num, wind_fname, meteorproc_exe):
    # Convert cfit to a meridional wind
    os.makedirs(os.path.dirname(wind_fname), exist_ok=True)
    cmd = '%s -bm %i -mz m %s > %s' % \
        (meteorproc_exe, beam_num, cfit_fname, wind_fname)
    print(cmd)
    os.system(cmd)
    print('written to %s' % wind_fname)



if __name__ == '__main__':
    args = sys.argv
    assert len(args) == 5, 'Should have 4x args, e.g.:\n' + \
        'python3 run_meteorproc.py 2016,1,1 2017,1,1 ' + \
        '/project/superdarn/alex/cfit/%Y/%m/%Y%m%d  ' + \
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
        cfit_fname_fmt=args[3], 
        wind_fname_fmt=args[4],
    )


