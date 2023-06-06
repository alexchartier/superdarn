import numpy as np
import datetime as dt
import glob
import os
import string 
import random
import aacgmv2
import re

def get_radar_params(hdw_dat_dir):
    # Pull out all the time/beam/radar name info from hdw_dat_dir   
    filenames = glob.glob(os.path.join(hdw_dat_dir, '*'))
    assert len(filenames) > 0, 'No HDW files found in: %s' % hdw_dat_dir

    # NOTE: Simon's ICW/ICE hdw.dat files are non-standard format and of unknown provenance -I'm taking them out (ATC)
    filenames_nosimon = []
    for fn in filenames:
        if fn.split('.')[-1] == 'icw':
            continue
        if fn.split('.')[-1] == 'ice':
            continue
        filenames_nosimon.append(fn)
    filenames = filenames_nosimon

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
            ln = line.split()

            # Simon has decided to add a time of day to the hdw.dat - here's a workaround
            #lnclean = []
            #for x in ln:
            #    if not re.search(r':', x):
            #        lnclean.append(x)
            #ln = lnclean

            vals = [float(vn) for vn in ln]
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


def get_random_string(length):
    """Return a random string of lowercase letters"""

    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str


def get_radar_list(in_dir):
    breakpoint()
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
            if 'despeck' in f:
                radarn = items[3]
            else:
                radarn = '.'.join(items[3:5])
        elif len(items) == 8:
            radarn = '.'.join(items[3:5])
        else:
            raise ValueError('filename does not match expectations: %s' % f)
        if radarn not in radar_list:
            radar_list.append(radarn)
            print(radarn)
    return radar_list



