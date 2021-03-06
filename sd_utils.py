import numpy as np
import datetime as dt
import glob
import os
import string 
import random

def get_radar_params(hdw_dat_dir):
    # Pull out all the time/beam/radar name info from hdw_dat_dir   
    filenames = glob.glob(os.path.join(hdw_dat_dir, '*'))
    assert len(filenames) > 0, 'No HDW files found in: %s' % hdw_dat_dir

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


def get_random_string(length):
    """Return a random string of lowercase letters"""

    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str
