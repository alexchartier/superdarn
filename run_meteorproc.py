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
    
    
def get_radar_params(hdw_dat_dir):
    # Pull out all the time/beam/radar name info from hdw_dat_dir   
    filenames = glob.glob(os.path.join(hdw_dat_dir, '*'))

    prm = [
        'glat', 'glon', 'alt', 'boresight', 'beamsep', 'velsign',
         'rxstep', 'tdiff', 'phasesign', 'intoffset_x', 'intoffset_y',
         'intoffset_z', 'risetime', 'atten', 'maxrg', 'maxbeams',
    ]
    radar_list = {}
    for fn in filenames:
        radar_name = fn.split('.')[-1]

        # Read in text and remove comments
        with open(fn, 'r') as f:
            txt = f.readlines()
        txt2 = []
        for line in txt:
            line_el = line.split()
            if len(line_el) == 0:
                continue
            if not line.startswith('#'):
                txt2.append(line)

        # Read hardware parameters
        radar_list[radar_name] = {}
        for line in txt2:
            vals = [float(ln) for ln in line.split()]
            yr = int(vals[1])
            tot_sec = int(vals[2])
            assert (yr < 5000) & (yr > 1980), 'year looks wrong: %i' % yr
            assert (tot_sec < 34300000) & (tot_sec >= 0), 'tot_sec looks wrong: %i' % tot_sec
            enddate = dt.datetime(yr, 1, 1) + dt.timedelta(seconds=tot_sec)
            flv = [float(v) for v in vals[3:]]
            hdw_params = dict(zip(prm, flv))
         
            assert hdw_params['maxbeams'] < 25, 'maxbeams is > 24 %f' % hdw_params['maxbeams']
            assert hdw_params['beamsep'] < 5, 'beamsep is > 5 %f' % hdw_params['beamsep']
            assert hdw_params['boresight'] < 360, 'boresight is >= 360 %f' % hdw_params['boresight']

            radar_list[radar_name][enddate] = hdw_params

    return radar_list

    
def id_hdw_params_t(day, hdw_params):
    # return the first hardware params with an end-date after time t
    for enddate, hdw_params_t in hdw_params.items():
        if enddate > day:
            return hdw_params_t


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



if __name__ == '__main__':
    meteorproc()
