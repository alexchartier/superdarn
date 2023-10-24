import numpy as np
import datetime as dt
import glob
import os
import string 
import random
import aacgmv2
import re

def get_radar_params_old(hdw_dat_dir):
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
            ln = line.split()

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

    
def id_hdw_params_t_old(day, hdw_params):
    # return the first hardware params with an end-date after time t
    for enddate, hdw_params_t in hdw_params.items():
        if enddate > day:
            return hdw_params_t

def get_radar_params(hdw_dat_dir):
    # Pull out all the time/beam/radar name info from hdw_dat_dir   
    filenames = glob.glob(os.path.join(hdw_dat_dir, 'hdw.dat*'))
    assert len(filenames) > 0, 'No HDW files found in: %s' % hdw_dat_dir

    parameters = [
        'glat', 'glon', 'alt', 'boresight', 'boresight_offset', 'beamsep', 'velsign',
        'phasesign', 'tdiff_a', 'tdiff_b', 'intoffset_x', 'intoffset_y',
        'intoffset_z', 'risetime', 'atten_step', 'atten', 'maxrg', 'maxbeams',
    ]

    radar_list = {}
    for filename in filenames:
        radar_name = filename.split('.')[-1]

        # Read in text and remove comments
        with open(filename, 'r') as f:
            all_text = f.readlines()
        param_text = []
        for line in all_text:
            line_el = line.split()
            if len(line_el) == 0:
                continue
            if not line.startswith('#'):
                param_text.append(line)

        # Read hardware parameters
        radar_list[radar_name] = {}
        for line in param_text:
            params = [float(vn) if "." in vn else vn if ":" in vn else int(vn) for vn in line.split()]
            date_str = f"{int(params[2])} {params[3]}"  # Combine date and time components
            date_format = "%Y%m%d %H:%M:%S"
            start_date = dt.datetime.strptime(date_str, date_format)
            assert 1980 < start_date.year < 5000, f'Year looks wrong: {start_date.year}'
            
            flv = [float(v) for v in params[4:]]
            hdw_params = dict(zip(parameters, flv))

            assert hdw_params['maxbeams'] < 25, f'maxbeams is > 24 {hdw_params["maxbeams"]}'
            assert hdw_params['beamsep'] < 5, f'beamsep is > 5 {hdw_params["beamsep"]}'
            assert hdw_params['boresight'] < 360, f'boresight is >= 360 {hdw_params["boresight"]}'

            radar_list[radar_name][start_date] = hdw_params

    return radar_list

def id_hdw_params_t(date, hdw_params):
    valid_params = None
    timestamps = sorted(hdw_params.keys())
    
    for i in range(len(timestamps) - 1):
        if timestamps[i] <= date < timestamps[i + 1]:
            valid_params = hdw_params[timestamps[i]]
            break
    
    if date >= timestamps[-1]:
        valid_params = hdw_params[timestamps[-1]]

    return valid_params
        
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



