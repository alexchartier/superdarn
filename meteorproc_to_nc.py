import numpy as np
import datetime as dt
import os
import sys
import glob
from collections import defaultdict
from dateutil.relativedelta import relativedelta
import netCDF4

def convert_winds(
    startTime, endTime, indir, outdir,
):

    month = startTime
    while month <= endTime:
    
        # Parse monthly file-list
        flist = glob.glob(os.path.join(month.strftime(indir), '*'))
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
                fn_fmt = os.path.join(month.strftime(indir), '.'.join([date, radar, '%s.txt']))
                out_fname = os.path.join(month.strftime(outdir), '.'.join([date, radar, 'nc']))
                os.makedirs(os.path.dirname(out_fname), exist_ok=True)
                merid_wind_fn = fn_fmt % 'm' 
                zonal_wind_fn = fn_fmt % 'z'

                try:
                    m_hdr, m_vars = read_winds(merid_wind_fn)
                    z_hdr, z_vars = read_winds(zonal_wind_fn)
                except:
                    print('Unable to find %s' % fn_fmt)
                    continue
                if m_vars['year'] == []:
                    print('Unable to process %s' % fn_fmt)
                    continue
    
                outvars, header_info = format_outvars(m_vars, z_vars)
                dim_defs = {'npts': len(outvars['hour'])}   
                var_defs = def_vars()
                header_info['description'] = \
                    'meridional + zonal winds from %s and %s' % \
                    (merid_wind_fn, zonal_wind_fn)
                header_info['params'] = m_hdr.replace('meridional', 'both')
                header_info['history'] = 'created on %s' % dt.datetime.now()

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
                
        month += relativedelta(months=1)


def set_header(rootgrp, header_info) :
    rootgrp.description = header_info['description']
    rootgrp.header = header_info['params']
    rootgrp.history = header_info['history']
    rootgrp.lat = header_info['lat']
    rootgrp.lon = header_info['lon']
    rootgrp.rsep_km = header_info['rsep']
    rootgrp.maxrangegate = header_info['frang']
    return rootgrp


def format_outvars(m_vars, z_vars):
    outvars = {}
    varnames = 'hour', 'Vm', 'Vx', 'Vy', 'sdev_Vx', 'sdev_Vy'
    for vn in varnames:
        outvars[vn] = m_vars[vn] 
    outvars['V_merid'] = outvars.pop('Vm')
    outvars['V_zonal'] = z_vars['Vz']
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
        'V_merid': dict({'units': 'm/s', 'long_name': 'Merid. Vel. (+ve North)'}, **stdin_dbl),
        'V_zonal': dict({'units': 'm/s', 'long_name': 'Zonal Vel. (+ve East)'}, **stdin_dbl),
        'Vx': dict({'units': 'm/s', 'long_name': 'X Vel. (radar coords?)'}, **stdin_dbl),
        'Vy': dict({'units': 'm/s', 'long_name': 'Y Vel. (radar coords?)'}, **stdin_dbl),
        'sdev_Vx': dict({'units': 'm/s', 'long_name': 'Vel. error'}, **stdin_dbl),
        'sdev_Vy': dict({'units': 'm/s', 'long_name': 'Vel. error'}, **stdin_dbl),
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
            vals.append(np.array(line.split()).astype(np.float))
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
