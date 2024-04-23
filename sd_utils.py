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
    hdw_dat_dir = os.path.expanduser(hdw_dat_dir)
    filenames = glob.glob(os.path.join(hdw_dat_dir, '*'))
    filenames = [f for f in filenames if not f.endswith('txt')]
    assert len(filenames) > 0, 'No HDW files found in: %s' % hdw_dat_dir

    prm = [
        'glat', 'glon', 'alt', 'boresight', 'offset', 'beamsep', 'velsign',
        'phasesign', 'tdiff1', 'tdiff2', 'intoffset_x', 'intoffset_y',
        'intoffset_z', 'risetime', 'att', 'n', 'maxrg', 'maxbeams',
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

        # Generate list of radar times
        enddates = []
        for line in txt2:
            ln = line.split()
            try:
                time = dt.datetime.strptime(ln[2], '%Y%m%d')
            except:
                breakpoint()
            assert (time > dt.datetime(1980, 1, 1)) & (time < dt.datetime(
                2100, 1, 1)), 'time looks wrong: %s %s' % (time, radar_name)
            enddates.append(time)
        enddates.append(dt.datetime(2100, 1, 1))

        # Read hardware parameters
        radar_list[radar_name] = {}
        for ind, line in enumerate(txt2):
            vals = [float(vn) for vn in ln[4:]]
            enddate = enddates[ind + 1]
            hdw_params = dict(zip(prm, vals))
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
    beam_az += hdw_params['boresight'] - \
        hdw_params['beamsep'] * (center_bm - 1)
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
    print('Calculating list of radars')
    in_dir = os.path.expanduser(in_dir)
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
