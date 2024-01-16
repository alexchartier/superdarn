
import datetime as dt
import os
import re
import numpy as np
from glob import glob
from sd_utils import get_random_string, get_radar_list, id_beam_north, id_hdw_params_t, get_radar_params
import sys
import netCDF4
import helper

MIN_FITACF_FILE_SIZE = 1E5 # bytes

clobber = False

def main(date_string):
    
    wind_fname_fmt = '/project/superdarn/data/meteorwind/%Y/%m/%Y%b%d'
    meteorproc_exe='/project/superdarn/software/rst/bin/meteorproc'
    cfit_exe='/project/superdarn/software/rst/bin/make_cfit'
    
    print(f'Starting to convert {date_string} fitACFs to Meteorwind netCDF')

    date = dt.strptime(date_string, '%Y%m%d')

    fitacf_dir = date.strftime(helper.FITACF_DIR_FMT)
    meteorwind_dir = date.strftime(helper.METEORWIND_DIR_FMT)
    meteorwind_nc_dir = date.strftime(helper.METEORWIND_NC_DIR_FMT)

    os.makedirs(meteorwind_dir, exist_ok=True)
    os.makedirs(meteorwind_nc_dir, exist_ok=True)

    rstpath = os.getenv('RSTPATH')
    assert rstpath, 'RSTPATH environment variable needs to be set'
    hdw_dat_dir = os.getenv('SD_HDWPATH')
    radar_list = get_radar_params(hdw_dat_dir)

    for radar_name, hdw_params in radar_list.items():

        # get hardware parameters
        hdw_params = id_hdw_params_t(date, hdw_params)

        fitacf_files = glob(os.path.join(fitacf_dir, f"{date_string}.*{radar_name}*.fitacf3"))
        if len(fitacf_files) == 0:
            print(f'Not found: {os.path.join(fitacf_dir, f"{date_string}.*{radar_name}*.fitacf3")}')
            continue

        fitacf_files.sort()

        fit_fname = fitacf_files[0]

        fn_info = os.stat(fit_fname)
        if fn_info.st_size < helper.MIN_FITACF_FILE_SIZE:
            print('\n\n%s %1.1f MB\nFile too small - skipping' % (fit_fname, fn_info.st_size / 1E6))
            continue

        hdw_dat_fname = glob(os.path.join(hdw_dat_dir, '*%s*' % radar_name))[0]

        # loop over meridional and zonal
        for mz_flag in ['m', 'z']:
            # print(mz_flag)
            fitacf_base_filename = os.path.basename(fit_fname)
            
            #TODO: Start here
            # Use regular expression to extract the radar name with mode
            # E.g. get 'inv.a' from 20230901.inv.a.fitacf3
            match = re.search(r'\d{8}\.(.*?)\.fitacf3', fitacf_base_filename)
            if match:
                radar_name_with_mode = match.group(1)
            else:
                print(f'Unable to extract radar name with mode from {fitacf_base_filename}')
                continue

            # specify output filename
            wind_fname = date.strftime(wind_fname_fmt) + '.%s.%s.txt' % (radar_name_with_mode, mz_flag)
            
            if os.path.isfile(wind_fname) and not clobber:
                print('Meteorwind file already exists - skipping')
                continue

            beam_num = 1 # id_beam_north(hdw_params)

            # Convert file to a wind
            convert_fitacf_to_meteorwind(
                date, fit_fname, beam_num, wind_fname, 
                meteorproc_exe, cfit_exe, mz_flag
            )

    convert_meteorwind_to_netcdf(date, radar_list)

def convert_fitacf_to_meteorwind(
        day, fit_fname, beam_num, wind_fname, meteorproc_exe, cfit_exe, 
        mz_flag='m', cfit_fname='tmp.cfit',
):
    
    # Convert fit to cfit
    os.system('%s %s > %s' % (cfit_exe, fit_fname, cfit_fname))

    # Convert cfit to  wind
    os.makedirs(os.path.dirname(wind_fname), exist_ok=True)
    cmd = '%s -mz %s %s > %s' % \
        (meteorproc_exe, mz_flag, cfit_fname, wind_fname)
    print(cmd)
    os.system(cmd)
    print('Written to %s' % wind_fname)
    

def convert_meteorwind_to_netcdf(date, radar_prm):

    meteorwind_dir = date.strftime(helper.METEORWIND_DIR_FMT)
    meteorwind_nc_dir = date.strftime(helper.METEORWIND_NC_DIR_FMT)
    
    # month = startTime - step
    # while month <= endTime:
    #     month += step
    date_string = date.strftime("%Y%b%d")
    # Parse monthly file-list
    meteorwind_files = glob(os.path.join(meteorwind_dir, f"{date_string}.*"))
    if len(meteorwind_files) == 0: 
        print(date.strftime('skipping %Y %b - no files'))
        return

    dates = []
    radars = []
    for fn in meteorwind_files:
        date, radar = fn.split('.')[:2]
        dates.append(os.path.basename(date))
        radars.append(radar)

    dates = np.unique(dates)
    radars = np.unique(radars)

    # Loop over dates and radars, process into netCDFs
    for date in dates:
        time = dt.datetime.strptime(date, '%Y%b%d') 
        for radar in radars:
            print(radar)
            fn_fmt = os.path.join(date.strftime(meteorwind_dir), '.'.join([date, radar, '*%s.txt']))
            out_fname = os.path.join(date.strftime(meteorwind_nc_dir), '.'.join([date, radar, 'nc']))
            os.makedirs(os.path.dirname(out_fname), exist_ok=True)
            
            # Grab the file
            merid_wind_fn_glob = fn_fmt % 'm' 
            merid_wind_fn_list = glob(merid_wind_fn_glob)
            if len(merid_wind_fn_list) < 1:
                print('Unable to find %s' % merid_wind_fn_glob)
                continue
            merid_wind_fn = merid_wind_fn_list[0]
            if os.stat(merid_wind_fn).st_size == 0:
                print('Empty file: %s' % merid_wind_fn)
                continue
            hdw_params = radar_prm[radar]
            hdw_dat_t = id_hdw_params_t(time, hdw_params)
            boresight = hdw_dat_t['boresight']

            # try to load
            try:
                m_hdr, m_vars = read_winds(merid_wind_fn)
            except:
                print('Unable to process %s' % fn_fmt)
                continue
            if m_vars['year'] == []:
                print('Unable to process %s' % fn_fmt)
                continue
            
            # Define output variables 
            outvars, header_info = format_outvars(m_vars)
            dim_defs = {'npts': len(outvars['hour'])}   
            var_defs = def_vars()
            header_info['description'] = \
                'SuperDARN winds from %s' % \
                (merid_wind_fn)
            header_info['params'] = m_hdr.replace('meridional', 'both')
            header_info['history'] = 'created on %s' % dt.datetime.now()
            header_info['boresight'] = '%1.2f degrees East of North' % boresight

            # Write out the netCDF 
            with netCDF4.Dataset(out_fname, 'w') as nc: 
                set_header(nc, header_info)
                for k, v in dim_defs.items():
                    nc.createDimension(k, size=v)
                for k, v in outvars.items():
                    defs = var_defs[k]
                    var = nc.createVariable(k, defs['type'], defs['dims'])
                    var[:] = v 
                    var.units = defs['units']
                    var.long_name = defs['long_name']
            print('Wrote to %s' % out_fname)
                

def set_header(rootgrp, header_info) :
    rootgrp.description = header_info['description']
    rootgrp.header = header_info['params']
    rootgrp.history = header_info['history']
    rootgrp.lat = header_info['lat']
    rootgrp.lon = header_info['lon']
    rootgrp.rsep_km = header_info['rsep']
    rootgrp.frang = header_info['frang']
    rootgrp.boresight = header_info['boresight']
    return rootgrp


def format_outvars(m_vars):
    outvars = {}
    varnames = 'hour',  'Vx', 'Vy', 'sdev_Vx', 'sdev_Vy', 'lat', 'long'
    for vn in varnames:
        outvars[vn] = m_vars[vn] 
    #outvars['V_merid'] = outvars.pop('Vm')
    #outvars['V_zonal'] = z_vars['Vz']
    params = {
        'day': dt.datetime(int(m_vars['year'][0]), int(m_vars['month'][0]), int(m_vars['day'][0])),
        'lat': m_vars['lat'][0],
        'lon': m_vars['long'][0],
        'rsep': m_vars['rsep'][0],
        'frang': m_vars['frang'][0],
    }
    
    return outvars, params


def def_vars():
    # netCDF writer expects a series of variable definitions - here they are
    stdin_dbl = {'type': 'f8', 'dims': 'npts'} 
    var_defs = { 
        'hour': dict({'units': 'hours', 'long_name': 'Hour (UT)'}, **stdin_dbl),
        'Vx': dict({'units': 'm/s', 'long_name': 'Radar Boresight Vel.'}, **stdin_dbl),
        'Vy': dict({'units': 'm/s', 'long_name': 'Perp. Radar Boresight Vel. (90deg right)'}, **stdin_dbl),
        'sdev_Vx': dict({'units': 'm/s', 'long_name': 'Vel. error'}, **stdin_dbl),
        'sdev_Vy': dict({'units': 'm/s', 'long_name': 'Vel. error'}, **stdin_dbl),
        'lat': dict({'units': 'deg', 'long_name': 'Latitude'}, **stdin_dbl),
        'long': dict({'units': 'deg', 'long_name': 'Longitude'}, **stdin_dbl),
    }   
    return var_defs


def read_winds(wind_fn):
    # Turn the text files into dict data
    with open(wind_fn, 'r') as f:
        txt = f.readlines()
    hdr = []
    vals = []
    for line in txt:
        if line[0] == '#':
            hdr.append(line)
        else:
            vals.append(np.array(line.split()).astype(float))
    varnames = hdr[-1].split()[1:]
    outvars = {v: [] for v in varnames}
    for val_list in vals:
        outvar_l = dict(zip(varnames, val_list))
        for k, v in outvar_l.items():
            outvars[k].append(v)

    hdr = ', '.join([ln.replace('#', '').strip() for ln in hdr[:-1]])

    return hdr, outvars

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 convert_fitacf_to_meteorwind_netcdf.py YYYYMMDD")
        sys.exit(1)

    # Extract the day argument in 'YYYYMMDD' format
    date_string = sys.argv[1]

    # Check if the day argument is in the correct format
    if not date_string.isdigit() or len(date_string) != 8:
        print("Date argument must be in 'YYYYMMDD' format.")
        sys.exit(1)

    main(date_string)

