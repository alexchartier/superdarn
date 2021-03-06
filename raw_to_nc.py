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
import netCDF4
import jdutil
import datetime as dt 
from dateutil.relativedelta import relativedelta
import calendar
import numpy as np
from sd_utils import get_radar_params, id_hdw_params_t, get_random_string
import pydarn
import radFov
import pdb


def main(
    starttime=dt.datetime(2005, 12, 1),
    endtime=dt.datetime(2020, 1, 1),
    in_dir_fmt='/project/superdarn/data/rawacf/%Y/%m/',
    fit_dir_fmt='/project/superdarn/data/fitacf/%Y/%m/',
    out_dir_fmt='/project/superdarn/data/netcdf/%Y/%m/',
    step=1,  # month
    skip_existing=True,
    fit_ext='*.fit',
):

    rstpath = os.getenv('RSTPATH')
    assert rstpath, 'RSTPATH environment variable needs to be set'
    hdw_dat_dir = os.path.join(rstpath, 'tables/superdarn/hdw/')
    
    # Running raw to NC
    radar_info = get_radar_params(hdw_dat_dir)
    run_dir = './run/%s' % get_random_string(4)
    if in_dir_fmt:
        raw_to_fit(starttime, endtime, run_dir, in_dir_fmt, fit_dir_fmt)

    # Loop over fit files in the monthly directories
    time = starttime
    while time <= endtime:

        # Set up directories
        out_dir = time.strftime(out_dir_fmt)
        print('Trying to make %s' % out_dir)
        os.makedirs(out_dir, exist_ok=True)

        # Loop over the files
        #fit_fn_fmt = time.strftime(os.path.join(fit_dir_fmt, '%Y%m%d'))
        fit_fn_fmt = time.strftime(fit_dir_fmt)
        temp = f'fit_fn_fmt: {fit_fn_fmt}'
        print(temp)
        print(os.path.join(fit_fn_fmt, fit_ext))
        fit_fnames = glob.glob(os.path.join(fit_fn_fmt, fit_ext))
        print('Processing %i %s files in %s on %s' % (len(fit_fnames), fit_ext, fit_fn_fmt, time.strftime('%Y/%m')))
        for fit_fn in fit_fnames:
        
            # Check the file is big enough to be worth bothering with
            fn_info = os.stat(fit_fn)
            if fn_info.st_size < 1E5:
                print('\n\n%s %1.1f MB\nFile too small - skipping' % (fit_fn, fn_info.st_size / 1E6))
                continue
            print('\n\nStarting from %s' % fit_fn)

            fn_head = '.'.join(os.path.basename(fit_fn).split('.')[:-1])
            out_fn = os.path.join(out_dir, '%s.nc' % fn_head)
            if os.path.isfile(out_fn):
                if skip_existing: 
                    print('%s exists - skipping' % out_fn)
                    continue
                else:
                    print('%s exists - deleting' % out_fn)
                    os.remove(out_fn)

            # Convert the fitACF to a netCDF
            radar_code = os.path.basename(fit_fn).split('.')[1]
            radar_info_t = id_hdw_params_t(time, radar_info[radar_code])

            status = fit_to_nc(time, fit_fn, out_fn, radar_info_t)

            if status > 0:
                print('Failed to convert %s' % fit_fn)
                continue

            print('Wrote output to %s' % out_fn)
            
        time = add_months(time, step)  # time += dt.timedelta(months=1) doesn't exist


def fit_to_nc(date, in_fname, out_fname, radar_info):
    # fitACF to netCDF using davitpy FOV calc  - no dependence on fittotxt
    out_vars, hdr_vals = convert_fitacf_data(date, in_fname, radar_info)
    var_defs = def_vars()
    dim_defs = {
        'npts': out_vars['mjd'].shape[0], 
    } 
    header_info = def_header_info(in_fname, hdr_vals)
    
    # Write out the netCDF 
    with netCDF4.Dataset(out_fname, 'w') as nc: 
        set_header(nc, header_info)
        for k, v in dim_defs.items():
            nc.createDimension(k, size=v)
        for k, v in out_vars.items():
            defs= var_defs[k]
            var = nc.createVariable(k, defs['type'], defs['dims'])
            var[:] = v
            var.units = defs['units']
            var.long_name = defs['long_name']

    return 0


def convert_fitacf_data(date, in_fname, radar_info):
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

    # Define FOV
    fov = radFov.fov(
        frang=bmdata['frang'], rsep=bmdata['rsep'], site=None, nbeams=int(radar_info['maxbeams']),
        ngates=int(radar_info['maxrg']), bmsep=radar_info['beamsep'], recrise=radar_info['risetime'], siteLat=radar_info['glat'],
        siteLon=radar_info['glon'], siteBore=radar_info['boresight'], siteAlt=radar_info['alt'], siteYear=date.year,
        elevation=None, altitude=300., hop=None, model='IS',
        coords='geo', date_time=date, coord_alt=0., fov_dir='front',
    )

    # Define fields 
    short_flds = 'tfreq', 'noise.sky', 'cp',
    fov_flds = 'mjd', 'beam', 'range', 'lat', 'lon', 
    data_flds = 'p_l', 'v', 'v_e', 'gflg', 
    elv_flds = 'elv', 'elv_low', 'elv_high',

    # Figure out if we have elevation information
    is_elv = False
    for rec in data:
        if 'elv' in rec.keys():
            is_elv = True
    if is_elv:
        data_flds += elv_flds

    # Set up data storage
    out = {}
    for fld in (fov_flds + data_flds + short_flds):
        out[fld] = []
   
    # Run through each beam record and store 
    for rec in data:
        # slist is the list of range gates with backscatter
        if 'slist' not in rec.keys():
            continue
        fov_data = {}
        time = dt.datetime(rec['time.yr'], rec['time.mo'], rec['time.dy'], rec['time.hr'], rec['time.mt'], rec['time.sc'])
        one_obj = np.ones(len(rec['slist'])) 
        mjd = jdutil.jd_to_mjd(jdutil.datetime_to_jd(time))
        bmnum = one_obj * rec['bmnum']
        fovi = fov.beams == rec['bmnum']
        out['mjd'] += (one_obj * mjd).tolist()
        out['beam'] += bmnum.tolist()
        out['range'] += fov.slantRCenter[fovi, rec['slist']].tolist()
        out['lat'] += fov.latCenter[fovi, rec['slist']].tolist()
        out['lon'] += fov.lonCenter[fovi, rec['slist']].tolist()

        for fld in data_flds:
            out[fld] += rec[fld].tolist()
        for fld in short_flds:  # expand out to size
            out[fld] += (one_obj * rec[fld]).tolist()

    # Convert to numpy arrays 
    for k, v in out.items():
        out[k] = np.array(v)

    # Calculate beam azimuths assuming 20 degrees elevation
    beam_off = radar_info['beamsep'] * (fov.beams - (radar_info['maxbeams'] - 1) / 2.0)
    el = 15.
    brng = np.zeros(beam_off.shape)
    for ind, beam_off_elzero in enumerate(beam_off):
        brng[ind] = radFov.calcAzOffBore(el, beam_off_elzero, fov_dir=fov.fov_dir) +radar_info['boresight']

    hdr = {
        'lat': radar_info['glat'],
        'lon': radar_info['glon'],
        'alt': radar_info['alt'],
        'rsep': bmdata['rsep'],
        'maxrg': radar_info['maxrg'],
        'bmsep': radar_info['beamsep'],
        'boresight': radar_info['boresight'],
        'beams': fov.beams,
        'brng_at_15deg_el': brng,
    }

    return out, hdr


def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year,month)[1])
    return dt.datetime(year, month, day, sourcedate.hour, sourcedate.minute, sourcedate.second)


def def_vars():
    # netCDF writer expects a series of variable definitions - here they are
    stdin_int = {'units': 'none', 'type': 'u1', 'dims': 'npts'} 
    stdin_int2 = {'units': 'none', 'type': 'u2', 'dims': 'npts'} 
    stdin_flt = {'type': 'f4', 'dims': 'npts'} 
    stdin_dbl = {'type': 'f8', 'dims': 'npts'} 
    vars = {
        'mjd': dict({'units': 'days', 'long_name': 'Modified Julian Date'}, **stdin_dbl),
        'beam': dict({'long_name': 'Beam #'}, **stdin_int),
        'range': dict({'units': 'km','long_name': 'Slant range'}, **stdin_int2),
        'lat': dict({'units': 'deg.', 'long_name': 'Latitude'}, **stdin_flt),
        'lon': dict({'units': 'deg.', 'long_name': 'Longitude'}, **stdin_flt),
        'p_l': dict({'units': 'dB', 'long_name': 'Lambda fit SNR'}, **stdin_flt),
        'v': dict({'units': 'm/s', 'long_name': 'LOS Vel. (+ve away from radar)'}, **stdin_flt),
        'v_e': dict({'units': 'm/s', 'long_name': 'LOS Vel. error'}, **stdin_flt),
        'gflg': dict({'long_name': 'Flag (0 F, 1 ground, 2 collisional, 3 other)'}, **stdin_int),
        'elv': dict({'units': 'degrees', 'long_name': 'Elevation angle estimate'}, **stdin_flt),
        'elv_low': dict({'units': 'degrees', 'long_name': 'Lowest elevation angle estimate'}, **stdin_flt),
        'elv_high': dict({'units': 'degrees', 'long_name': 'Highest elevation angle estimate'}, **stdin_flt),
        'tfreq': dict({'units': 'kHz','long_name': 'Transmit freq'}, **stdin_int2),
        'noise.sky': dict({'units': 'none','long_name': 'Sky noise'}, **stdin_flt),
        'cp': dict({'units': 'none','long_name': 'Control program ID'}, **stdin_int2),
    }   

    return vars


def set_header(rootgrp, header_info) :
    rootgrp.description = header_info['description']
    rootgrp.source = header_info['source']
    rootgrp.history = header_info['history']
    rootgrp.lat = header_info['lat']
    rootgrp.lon = header_info['lon']
    rootgrp.alt = header_info['alt']
    rootgrp.rsep_km = header_info['rsep']
    rootgrp.maxrangegate = header_info['maxrg']
    rootgrp.bmsep = header_info['bmsep']
    rootgrp.boresight = header_info['boresight']
    rootgrp.beams = header_info['beams']
    rootgrp.brng_at_15deg_el = header_info['brng_at_15deg_el']
    return rootgrp


def def_header_info(in_fname, hdr_vals):
    hdr = {
        **{
        'description': 'Geolocated line-of-sight velocities and related parameters from SuperDARN fitACF v2.5',
        'source': 'in_fname',
        'history': 'Created on %s' % dt.datetime.now(),
        }, 
        **hdr_vals,
    }

    return hdr


def raw_to_fit(
    starttime = dt.datetime(2016, 1, 1),
    endtime = dt.datetime(2017, 1, 1),
    run_dir = './run/',
    in_dir='/project/superdarn/data/rawacf/%Y/%m/',
    out_dir='/project/superdarn/alex/fitacf/%Y/%m/',
    clobber=False,
):

    print('%s\n%s\n%s\n%s\n%s\n' % (
        'Converting files from rawACF to fitACF',
        'from: %s to %s' % (starttime.strftime('%Y/%m/%d'), endtime.strftime('%Y/%m/%d')),
        'input e.g.: %s' % starttime.strftime(in_dir),
        'output e.g.: %s' % starttime.strftime(out_dir),
        'Run: %s' % run_dir,
    ))

    run_dir = os.path.abspath(run_dir)
    # Loop over time
    ct = 0
    time = starttime
    while time <= endtime:
        in_dir_t = time.strftime(in_dir)
        if not os.path.isdir(in_dir_t):
            time += relativedelta(months=1)
            print('%s not found - skipping' % in_dir_t)
            continue
        radar_list = get_radar_list(in_dir_t)
        for radar in radar_list:
            indirn = os.path.join(in_dir, radar)  # for old setup
            in_fname_fmt = time.strftime(os.path.join(in_dir, '%Y%m%d' + '*%s*.rawacf.bz2' % radar))
            fit_fname = time.strftime(out_dir + '%Y%m%d.' + '%s.fit' % radar)
            if os.path.isfile(fit_fname):
                print("File exists: %s" % fit_fname)
                if clobber:
                    print('overwriting')
                else:
                    print('skipping')
                    continue
            status = proc_radar(radar, in_fname_fmt, fit_fname, run_dir)
        time += dt.timedelta(days=1)



def proc_radar(radar, in_fname_fmt, out_fname, run_dir):

    # Clean up the run directory
    os.makedirs(run_dir, exist_ok=True)
    os.chdir(run_dir)
    os.system('rm -rf %s/*' % run_dir)

    # Set up storage directory
    out_dir = os.path.dirname(out_fname)
    os.makedirs(out_dir, exist_ok=True)

    # Make fitacfs for the day
    in_fnames = glob.glob(in_fname_fmt)
    if len(in_fnames) == 0:
        print('No files in %s' % in_fname_fmt)
        return 1

    for in_fname in in_fnames:
        shutil.copy2(in_fname, run_dir)
        in_fname_t = os.path.join(run_dir, os.path.basename(in_fname))
        os.system('bzip2 -d %s' % in_fname_t)

        in_fname_t2 = '.'.join(in_fname_t.split('.')[:-1])
        tmp_fname = '.'.join(in_fname_t2.split('.')[:-1]) + '.fitacf'
        os.system('make_fit %s > %s' % (in_fname_t2, tmp_fname))
    os.system('cat *.fitacf > tmp.fitacf')

    # Create a single fitACF at output location
    # os.system('make_cfit tmp.fitacf > %s' % out_fname)
    fn_inf = os.stat('tmp.fitacf')
    if fn_inf.st_size > 1E5:
        shutil.move('tmp.fitacf', out_fname)
        print('file created at %s, size %1.1f MB' % (out_fname, fn_inf.st_size / 1E6))
    else:
        print('file %s too small, size %1.1f MB' % (out_fname, fn_inf.st_size / 1E6))
    return 0


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

    assert len(args) >= 5, 'Should have 5x args, e.g.:\n' + \
        'python3 raw_to_nc.py 2014,4,23 2014,4,24 ' + \
        '/project/superdarn/data/rawacf/%Y/%m/  ' + \
        '/project/superdarn/data/fitacf/%Y/%m/  ' + \
        '/project/superdarn/data/netcdf/%Y/%m/'

    stime = dt.datetime.strptime(args[1], '%Y,%m,%d')
    etime = dt.datetime.strptime(args[2], '%Y,%m,%d')
    if len(args) == 6:

        in_dir = args[3]
        fit_dir = args[4]
        out_dir = args[5]
    elif len(args) == 5:
        in_dir = None
        fit_dir = args[3]
        out_dir = args[4]
    run_dir = './run/run_%s' % get_random_string(4) 

    
    main(stime, etime, in_dir, fit_dir, out_dir)




