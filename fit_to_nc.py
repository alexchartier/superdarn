"""
fit_to_nc.py

Turn cfit into netCDF files

Terms:
    iq.dat - raw in-phase and quadrature samples recorded by superdarn radars
    .rawacf - autocorrelation of the iq to the pulse sequence produced by the radar (C binary)
    .fitacf - fitted autocorrelation function containing parameters in local reference frame (range, doppler, azimuth, elevation etc.) (C binary)
              Typically 2-hour files, one per radar
    .cfit - subset of the fitacf (saves on space)  (C binary)
            Typically daily, one per radar
    .nc - netCDF output file (self-describing platform-independent file suitable for sharing with users outside the community)
          Daily, one per radar
    fittotxt - Takes a fitacf or a cfit and prints out specified parameters to ascii text. 
               Importantly, this program also geolocates the data in AACGM/geographic coords
    
    fittotxt output has dimensions: time x returns at time t
    netCDF output has dimension npts, where npts is the total number of returns across all the beams 
    "ideal" format is a sparse matrix, ntimes x nbeams x nranges for each variable

author: A.T. Chartier, 5 February 2020
"""
import os
import sys
import glob
#import bz2
import shutil
sys.path.append('/homes/chartat1/fusionpp/src/nimo/')
import nc_utils
import jdutil
import pdb
import datetime as dt 
import calendar
import numpy as np
from filter_radar_data import flag_data
from run_meteorproc import get_radar_params, id_hdw_params_t
from raw_to_fit import get_random_string
import pysat, pysat_solargeomag


def main(
    starttime=dt.datetime(2005, 12, 1),
    endtime=dt.datetime(2020, 1, 1),
    in_dir_fmt='/project/superdarn/data/cfit/%Y/%m/',
    out_dir_fmt='/project/superdarn/data/netcdf/%Y/%m/',
    run_dir='./run/',
    hdw_dat_dir='../rst/tables/superdarn/hdw/',
    step=1,  # month
    skip_existing=True,
    bzip_output=False,
    fit_ext='*.cfit',
):

    radar_info = get_radar_params(hdw_dat_dir)
    os.makedirs(run_dir, exist_ok=True)

    bzipped = False
    if fit_ext.split('.')[-1] == 'bz2':
        bzipped = True

    # Get the solar/geomagnetic indices
    pysat.utils.set_data_dir('../')
    f107_kp, ap = pysat_solargeomag.get_f107_kp_ap(
        './solar_geo.nc', starttime, endtime,
    )   

    # Loop over fit files in the monthly directories
    time = starttime
    while time <= endtime:

        # Set up directories
        out_dir = time.strftime(out_dir_fmt)
        os.makedirs(out_dir, exist_ok=True)

        # Loop over the files
        fit_fn_fmt = time.strftime(in_dir_fmt)
        fit_fnames = glob.glob(os.path.join(fit_fn_fmt, fit_ext))
        print('Processing %i files on %s' % (len(fit_fnames), time.strftime('%Y/%m/%d')))
        for fit_fn in fit_fnames:
        
            # Check the file is big enough to be worth bothering with
            fn_info = os.stat(fit_fn)
            if fn_info.st_size < 1E5:
                print('\n\n%s %1.1f MB\nFile too small - skipping' % (fit_fn, fn_info.st_size / 1E6))
                continue
            print('\n\nStarting from %s' % fit_fn)

            # Unzip if necessary
            if bzipped:
                shutil.copy2(fit_fn, run_dir)
                new_fn = os.path.join(run_dir, os.path.basename(fit_fn))
                os.system('bzip2 -d %s' % new_fn)
                fit_fn = '.'.join(new_fn.split('.')[:-1])
                
            fn_head = '.'.join(os.path.basename(fit_fn).split('.')[:-1])
            ascii_fn = os.path.join(run_dir, '%s.txt' % fn_head)
            nc_fn = os.path.join(run_dir, '%s.nc' % fn_head)
            out_fn = os.path.join(out_dir, '%s.nc' % fn_head)
            if os.path.isfile(out_fn):
                if skip_existing: 
                    print('%s exists - skipping' % out_fn)
                    continue
                else:
                    print('%s exists - deleting' % out_fn)
                    os.remove(out_fn)

            # Convert the cfit to a netCDF
            radar_code = os.path.basename(fit_fn).split('.')[1]
            radar_info_t = id_hdw_params_t(time, radar_info[radar_code])
            status = fit_to_nc(
                in_fname=fit_fn, 
                ascii_fname=ascii_fn, 
                out_fname=nc_fn, 
                radar_info=radar_info_t,
            )
            if status > 0:
                print('Failed to convert %s' % fit_fn)
                continue

            if bzip_output:
                # bzip to save space
                with open(nc_fn, 'rb') as f:
                    bzdat = bz2.compress(f.read(), 9)
                out_fn += '.bz2'
                with open(out_fn, 'wb') as f:
                    f.write(bzdat)
            else:
                shutil.move(nc_fn, out_fn)
            print('Wrote output to %s' % out_fn)

            # Clear out the run directory
            files = glob.glob(os.path.join(run_dir, '*'))
            for f in files:
                os.remove(f)
            

        time = add_months(time, step)
        # time += dt.timedelta(months=1) 
 

def fit_to_nc(
    in_fname='20180126_sas.cfit',
    ascii_fname='test.txt',
    out_fname='radar.nc',
    radar_info=None,
):

    """
    NOTE: Do not change - text output order does not follow the order they are passed in
        bm: beam
        km: rangegate
        geolat: geographic latitude
        geolon: geographic longitude
        geoazm: azimuth (off north) of the vector at the geo lat/lon
        aacgm: altitude-adjusted corrected geomagnetic coordinates (as above)
        gs: ground-scatter flag (0, 1) - based on observed velocity and other information
        pwr: backscattered power observed (imperfectly)
        vel: velocity (towards or away?) from radar 
        wdt: Spectral width observed - may indicate degree of plasma turbulence or goodness of fit
        # geovelne: Interpret the observed velocity in terms of North and East components
    """
    fittotxt_arg = '-bm -km -freq -geolat -geolon -geoazm -aacgmlat -aacgmlon -aacgmazm -gs -pwr -vel -wdt -cfit'    

    if os.path.isfile(ascii_fname):  # remove existing file if necessary
        os.system('rm %s' % ascii_fname)

    # Convert cfit to ascii
    cmd = 'fittotxt %s %s > %s' % (fittotxt_arg, in_fname, ascii_fname)
    print('Executing %s' % cmd)
    os.system(cmd)
    if os.stat(ascii_fname).st_size > 0:
        print('Converted %s to %s' % (in_fname, ascii_fname))
    else:
        print('Unable to process %s' % in_fname)
        return 1

    # Pull out the ascii values
    headers = [h.strip() for h in fittotxt_arg.split('-')]
    headers = [h for h in headers if h != '']
    headers = headers[:-1] 
   
    # Define the netCDF variables and dimensions 
    out_vars = read_fittotxt_ascii(ascii_fname, headers)
    # out_vars = flag_data(out_vars)
    var_defs = def_vars()
    dim_defs = {'npts': None} 
    header_info = def_header_info(in_fname, radar_info)

    # Write out the netCDF 
    nc_utils.write_nc(out_fname, var_defs, out_vars, set_header, header_info, dim_defs)

    return 0


def read_fittotxt_ascii(in_fname, headers, nbeams=16):
    # Read ASCII file
    with open(in_fname, 'r') as f:
        txt = f.readlines()

    # Set up data structure
    data = {}
    for hd in headers:
        data[hd] = []
    data['mjd'] = []

    # Convert ascii to a numpy array
    for line in txt:
        vals = np.array([float(l) for l in line.split()])

        # Check if this is a time-definition line. DARN/SuperDARN, Greenwald et al. 1995
        if vals[0] >= 1993:  
            time = dt.datetime(*vals.astype(int)[:6])

            # Modified Julian Date is an efficient means of storing time information
            mjd = jdutil.jd_to_mjd(jdutil.datetime_to_jd(time))  
            
        else:  # This is a data-containing line
            assert len(vals) == len(headers), 'Line does not look right\n%s\n%s' % (headers, line)
            for ind, v in enumerate(headers):
                data[v].append(vals[ind])
            data['mjd'].append(mjd)

    # Convert variables to efficient types
    for k, v in data.items():
        if (k == 'gs') or (k == 'bm'):
            data[k] = np.array(v, dtype=np.uint8)
        if (k == 'km'):
            data[k] = np.array(v, dtype=np.uint16)
        else:
            data[k] = np.array(v, dtype=np.float32)

    # The flags are as follows: 0 - F, 1 - ground, 2 - coll, 3 - other
    data['gs'][data['km'] <= 400] = 2  # (coll <= 400 km, see Hibbins et al. 2018)  

    return data


def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year,month)[1])
    return dt.datetime(year, month, day, sourcedate.hour, sourcedate.minute, sourcedate.second)


def def_vars():
    # netCDF writer expects a series of variable definitions - here they are
    stdin_int = {'units': 'none', 'type': 'u1', 'dims': 'npts'} 
    stdin_flt = {'type': 'f4', 'dims': 'npts'} 
    vars = {
        'mjd': dict({'units': 'days', 'long_name': 'Modified Julian Date'}, **stdin_flt),
        'bm': dict({'long_name': 'Beam #'}, **stdin_int),
        'km': dict({'units': 'km','long_name': 'Range', 'type': 'u2', 'dims': 'npts'}),
        'geolat': dict({'units': 'deg.', 'long_name': 'Latitude'}, **stdin_flt),
        'geolon': dict({'units': 'deg.', 'long_name': 'Longitude'}, **stdin_flt),
        'geoazm': dict({'units': 'deg.', 'long_name': 'Azimuth'}, **stdin_flt),
        'aacgmlat': dict({'units': 'deg.', 'long_name': 'AACGM Lat.'}, **stdin_flt),
        'aacgmlon': dict({'units': 'deg.', 'long_name': 'AACGM Lon.'}, **stdin_flt),
        'aacgmazm': dict({'units': 'deg.', 'long_name': 'AACGM Azimuth'}, **stdin_flt),
        'gs': dict({'long_name': 'Flag (0 F, 1 ground, 2 collisional, 3 other)'}, **stdin_int),
        'pwr': dict({'units': 'dB', 'long_name': 'Backscattered Power'}, **stdin_flt),
        'vel': dict({'units': 'm/s', 'long_name': 'LOS Vel. (+ve away from radar)'}, **stdin_flt),
        'wdt': dict({'units': 'm/s', 'long_name': 'Spectral Width'}, **stdin_flt),
        'freq': dict({'units': 'Hz', 'long_name': 'Transmit frequency'}, **stdin_flt),
        'vel_n': dict({'units': 'm/s', 'long_name': 'Geographic N component of velocity'}, **stdin_flt),
        'vel_e': dict({'units': 'm/s', 'long_name': 'Geographic E component of velocity'}, **stdin_flt),
    }   

    return vars
        

def set_header(rootgrp, header_info):
    rootgrp.description = header_info['description']
    rootgrp.source = header_info['source']
    rootgrp.history = header_info['history']
    rootgrp.hdw_dat = header_info['hdw_dat']
    return rootgrp


def def_header_info(in_fname, radar_info):
    hdw_dat_str = ''
    for k, v in radar_info.items():
        hdw_dat_str += '%s: %s, ' % (k, v)
    hdr = {
        'description': 'Geolocated line-of-sight velocities and related parameters from SuperDARN fitACF v2.5',
        'source': 'in_fname',
        'history': 'Created on %s' % dt.datetime.now(),
        'hdw_dat': hdw_dat_str, 
    }
    return {**hdr, **radar_info}



if __name__ == '__main__':

    args = sys.argv
    assert len(args) == 5, 'Should have 4x args, e.g.:\n' + \
        'python3 fit_to_nc.py 2016,1 2017,1 ' + \
        '/project/superdarn/data/cfit/%Y/%m/  ' + \
        '/project/superdarn/data/netcdf/%Y/%m/'

    stime = dt.datetime.strptime(args[1], '%Y,%m')
    etime = dt.datetime.strptime(args[2], '%Y,%m')
    in_dir = args[3]
    out_dir = args[4]
    
    run_dir = './run_%s' % get_random_string(4) 
    main(stime, etime, in_dir, out_dir, run_dir)




