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
from pydarn import PyDARNColormaps, build_scan, radar_fov


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
    fit_ext='*.fit',
):

    radar_info = get_radar_params(hdw_dat_dir)
    os.makedirs(run_dir, exist_ok=True)

    bzipped = False
    if fit_ext.split('.')[-1] == 'bz2':
        bzipped = True

    """
    # Get the solar/geomagnetic indices
    pysat.utils.set_data_dir('../')
    f107_kp, ap = pysat_solargeomag.get_f107_kp_ap(
        './solar_geo.nc', starttime, endtime,
    )   

    """
    # Loop over fit files in the monthly directories
    time = starttime
    while time <= endtime:

        # Set up directories
        out_dir = time.strftime(out_dir_fmt)
        os.makedirs(out_dir, exist_ok=True)

        # Loop over the files
        fit_fn_fmt = time.strftime(in_dir_fmt)
        fit_fnames = glob.glob(os.path.join(fit_fn_fmt, fit_ext))
        print('Processing %i %s files in %s on %s' % (len(fit_fnames), fit_ext, fit_fn_fmt, time.strftime('%Y/%m')))
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

            status = fit_to_nc_v2(time, fit_fn, nc_fn, radar_info_t)

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


def fit_to_nc_v2(date, in_fname, out_fname, radar_info):
    # fitACF to netCDF using davitpy FOV calc  - no dependence on fittotxt
    out_vars = convert_fitacf_data(date, in_fname, radar_info)
    var_defs = def_vars()
    dim_defs = {'npts': None} 
    header_info = def_header_info(in_fname, radar_info)

    # Write out the netCDF 
    nc_utils.write_nc(out_fname, var_defs, out_vars, set_header, header_info, dim_defs)

    return 0


def convert_fitacf_data(date, in_fname, radar_info):
    import pydarn
    import radFov
    SDarn_read = pydarn.SuperDARNRead(in_fname)
    data = SDarn_read.read_fitacf()
    bmdata = {
        'rsep': [],
        'frang': [],
    }
    for rec in data:
        for k, v in bmdata.items():
            bmdata[k].append(rec[k])
        if 'slist' in rec.keys():
            if radar_info['maxrg'] < rec['slist'].max():
                radar_info['maxrg'] = rec['slist'].max() + 5
    
    for k, v in bmdata.items():
        val = np.unique(v)
        assert len(val) == 1, "not sure what to do with multiple beam definitions in one file"
        bmdata[k] = int(val)

    fov = radFov.fov(
        frang=bmdata['frang'], rsep=bmdata['rsep'], site=None, nbeams=int(radar_info['maxbeams']),
        ngates=int(radar_info['maxrg']), bmsep=radar_info['beamsep'], recrise=radar_info['risetime'], siteLat=radar_info['glat'],
        siteLon=radar_info['glon'], siteBore=radar_info['boresight'], siteAlt=radar_info['alt'], siteYear=date.year,
        elevation=None, altitude=300., hop=None, model='IS',
        coords='geo', date_time=date, coord_alt=0., fov_dir='front',
    )

    # Set up data storage
    fov_flds = 'mjd', 'beam', 'range', 'lat', 'lon', 
    data_flds = 'pwr0', 'v', 'v_e', 'tfreq', 'gflg', 
    elv_flds = 'elv', 'elv_low', 'elv_high'
    is_elv = False
    for rec in data:
        if 'elv' in rec.keys():
            is_elv = True
    if is_elv:
        data_flds += elv_flds
    out_flds = fov_flds + data_flds
    out = {}
    for fld in out_flds:
        out[fld] = []
   
    # Run through each beam record and store 
    for rec in data:
        # slist is the list of range gates with backscatter
        if 'slist' not in rec.keys():
            continue
        fov_data = {}
        time = dt.datetime(rec['time.yr'], rec['time.mo'], rec['time.dy'], rec['time.hr'], rec['time.mt'], rec['time.sc'])
        one_obj = np.ones(len(rec['slist'])) 
        mjd = one_obj * jdutil.jd_to_mjd(jdutil.datetime_to_jd(time))
        bmnum = one_obj * rec['bmnum']
        fovi = fov.beams == rec['bmnum']
        out['mjd'] += mjd.tolist()
        out['beam'] += bmnum.tolist()
        out['range'] += fov.slantRCenter[fovi, rec['slist']].tolist()
        out['lat'] += fov.latCenter[fovi, rec['slist']].tolist()
        out['lon'] += fov.lonCenter[fovi, rec['slist']].tolist()

        rec['tfreq'] *= one_obj  # convert to an array
        for fld in data_flds:
            out[fld] += rec[fld].tolist()
    
    for k, v in out.items():
        out[k] = np.array(v)
    
    return out


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
    stdin_dbl = {'type': 'f8', 'dims': 'npts'} 
    vars = {
        'mjd': dict({'units': 'days', 'long_name': 'Modified Julian Date'}, **stdin_dbl),
        'beam': dict({'long_name': 'Beam #'}, **stdin_int),
        'range': dict({'units': 'km','long_name': 'Slant range', 'type': 'u2', 'dims': 'npts'}),
        'lat': dict({'units': 'deg.', 'long_name': 'Latitude'}, **stdin_flt),
        'lon': dict({'units': 'deg.', 'long_name': 'Longitude'}, **stdin_flt),
        'pwr0': dict({'units': 'dB', 'long_name': 'Lag zero SNR'}, **stdin_flt),
        'v': dict({'units': 'm/s', 'long_name': 'LOS Vel. (+ve away from radar)'}, **stdin_flt),
        'v_e': dict({'units': 'm/s', 'long_name': 'LOS Vel. error'}, **stdin_flt),
        'tfreq': dict({'units': 'Hz', 'long_name': 'Transmit frequency'}, **stdin_flt),
        'gflg': dict({'long_name': 'Flag (0 F, 1 ground, 2 collisional, 3 other)'}, **stdin_int),
        'elv': dict({'units': 'degrees', 'long_name': 'Elevation angle estimate'}, **stdin_flt),
        'elv_low': dict({'units': 'degrees', 'long_name': 'Lowest elevation angle estimate'}, **stdin_flt),
        'elv_high': dict({'units': 'degrees', 'long_name': 'Highest elevation angle estimate'}, **stdin_flt),
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
        'python3 fit_to_nc.py 2012,2 2012,2 ' + \
        'data/fitacf/%Y/%m/  ' + \
        'data/netcdf/%Y/%m/'

    stime = dt.datetime.strptime(args[1], '%Y,%m')
    etime = dt.datetime.strptime(args[2], '%Y,%m')
    in_dir = args[3]
    out_dir = args[4]
    
    run_dir = './run/run_%s' % get_random_string(4) 
    main(stime, etime, in_dir, out_dir, run_dir)




