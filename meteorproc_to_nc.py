import numpy as np
import datetime as dt
import os
import sys
import glob
from collections import defaultdict
from dateutil.relativedelta import relativedelta
import netCDF4
from sd_utils import get_radar_params, id_hdw_params_t


def convert_winds(
    startTime, endTime, indir, outdir,
    hdw_dat_dir='/project/superdarn/software/rst/tables/superdarn/hdw/',
):
    radar_prm = get_radar_params(hdw_dat_dir)
    step = relativedelta(months=1)

    month = startTime - step
    while month <= endTime:
        month += step

        # Parse monthly file-list
        flist = glob.glob(os.path.join(month.strftime(indir), '*'))
        if len(flist) == 0:
            print(month.strftime('skipping %Y %b - no files'))
            continue

        dates = []
        radars = []
        for fn in flist:
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
                fn_fmt = os.path.join(month.strftime(
                    indir), '.'.join([date, radar, '*%s.txt']))
                out_fname = os.path.join(month.strftime(
                    outdir), '.'.join([date, radar, 'nc']))
                os.makedirs(os.path.dirname(out_fname), exist_ok=True)

                # Grab the file
                merid_wind_fn_glob = fn_fmt % 'm'
                merid_wind_fn_list = glob.glob(merid_wind_fn_glob)
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


def set_header(rootgrp, header_info):
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
    # varnames = 'hour', 'Vm', 'Vx', 'Vy', 'sdev_Vx', 'sdev_Vy'
    varnames = 'hour', 'Vx', 'Vy', 'sdev_Vx', 'sdev_Vy', 'lat', 'long'
    for vn in varnames:
        outvars[vn] = m_vars[vn]
    # outvars['V_merid'] = outvars.pop('Vm')
    # outvars['V_zonal'] = z_vars['Vz']
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
        # 'V_merid': dict({'units': 'm/s', 'long_name': 'Merid. Vel. (+ve Poleward)'}, **stdin_dbl),
        # 'V_zonal': dict({'units': 'm/s', 'long_name': 'Zonal Vel. (+ve East)'}, **stdin_dbl),
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
    args = sys.argv
    assert len(args) == 5, 'Should have 5x args, e.g.:\n' + \
        'python3 meteorproc_to_nc.py ' + \
        '2005,1,1 2020,1,1  ' + \
        '/project/superdarn/alex/meteorwind/%Y/%m/ ' + \
        '/project/superdarn/alex/meteorwindnc/%Y/%m/'

    startTime = dt.datetime.strptime(args[1], '%Y,%m,%d')
    endTime = dt.datetime.strptime(args[2], '%Y,%m,%d')
    indir = args[3]
    outdir = args[4]
    convert_winds(startTime, endTime, indir, outdir)
