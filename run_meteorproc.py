"""
run_meteorproc.py

Loop through all the days and radars, processing the bzipped fitACFs into meteor winds
Use hardware.dat files to identify the beam configurations

"""

import numpy as np
import datetime as dt
import os
import glob
import bz2
import pdb


def meteorproc(
        starttime=dt.datetime(2009, 1, 1), 
        endtime=dt.datetime(2009, 2, 1), 
        run_dir='./run_mw/',
        meteorproc_exe='../rst/bin/meteorproc',
        hdw_dat_dir='../rst/tables/superdarn/hdw/',
        cfit_fname_fmt='/project/superdarn/alex/cfit/%Y/%m/%Y%m%d',
        wind_fname_fmt='/project/superdarn/alex/meteorwind/%Y/%m/%Y%b%d',
        skip_existing=False,
):
    time = starttime
    radar_list = get_radar_list(hdw_dat_dir)
    while time < endtime:
        for radar in radar_list:
            print(radar)
            # specify filenames
            cfit_fname = time.strftime(cfit_fname_fmt) + '.%s.cfit' % radar 
            wind_fname = time.strftime(wind_fname_fmt) + '.%s.txt' % radar
            hdw_dat_fname = glob.glob(os.path.join(hdw_dat_dir, '*%s*' % radar))[0]
            if (os.path.isfile(wind_fname) & skip_existing):
                print('wind file already exists')
                continue

            # get hardware parameters
            hdw_params = read_hdw_dat(time, hdw_dat_fname)
            if hdw_params['glat'] < 0:  # skip SH
                print('SH')
                continue
            beam_num = id_beam_north(hdw_params)

            # skip radars with no beam close to North
            if np.isnan(beam_num):  
                print('No North beam')
                continue

            # Skip nonexistent files
            if not os.path.isfile(cfit_fname)
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
    
    
def get_radar_list(hdw_dat_dir):
    # Pull out all the time/beam/radar name info from hdw_dat_dir   
    files = glob.glob(os.path.join(hdw_dat_dir, '*'))
    radar_list = [f.split('.')[-1] for f in files]
    return radar_list

    
def id_beam_north(hdw_params, center_bm=8, maxdev=10):
    # Find the most northward-pointing beam (if any close to north)
    beam_az = np.arange(hdw_params['maxbeams']) * hdw_params['beamsep'] 
    beam_az += hdw_params['boresight'] - hdw_params['beamsep'] * (center_bm - 1)
    beam_az[beam_az > 180] -= 360
    closest_north = min(abs(beam_az))
    if closest_north < maxdev:
        beamn = np.arange(1, hdw_params['maxbeams'] + 1)
        return beamn[abs(beam_az) == closest_north]
    else:
        return np.nan


def read_hdw_dat(day, hdw_dat_fname):
    # Pull the radar-specific parameters out of hdw.dat files
    with open(hdw_dat_fname, 'r') as f:
        txt = f.readlines()
    for line in txt:
        if line[0] is '#':  # skip comment lines
            continue
        vals = line.split()
        yr = int(vals[1])
        tot_sec = int(vals[2])
        assert (yr < 5000) & (yr > 1980), 'year looks wrong: %i' % yr
        assert (tot_sec < 34300000) & (tot_sec >= 0), 'tot_sec looks wrong: %i' % tot_sec
        td = (day - dt.datetime(yr, 1, 1)).total_seconds() - tot_sec
        if td > 0:  # This line of the file is for earlier times
            continue
        flv = [float(v) for v in vals[3:]]
        prm = ['glat', 'glon', 'alt', 'boresight', 'beamsep', 'velsign',\
             'rxstep', 'tdiff', 'phasesign', 'intoffset_x', 'intoffset_y',\
             'intoffset_z', 'risetime', 'atten', 'maxrg', 'maxbeams']
        hdw_params = {}
        for ind, p in enumerate(prm):
            hdw_params[p] = flv[ind]
        assert hdw_params['maxbeams'] < 25, 'maxbeams is > 24 %f' % hdw_params['maxbeams']
        assert hdw_params['beamsep'] < 5, 'beamsep is > 5 %f' % hdw_params['beamsep']
        assert hdw_params['boresight'] < 360, 'boresight is >= 360 %f' % hdw_params['boresight']

        return hdw_params


if __name__ == '__main__':
    meteorproc()
