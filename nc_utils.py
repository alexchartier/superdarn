"""
nc_utils.py
Some basic netCDF manipulation routines used by icon conversion code

Author: Alex T. Chartier, 20 December 2017
"""
import os
import datetime as dt
import numpy as np
import pdb 
import errno


def load_nc(fname):
    fn = os.path.expanduser(fname)
    if not os.path.isfile(fn):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), fn)
    try:
        from netCDF4 import Dataset
        return Dataset(fn, 'r', format='NETCDF4')
    except:
        import scipy.io.netcdf as nc
        return nc.netcdf_file(fn, 'r', version=2)


def ncread_vars(fname):
    if isinstance(fname, str):
        fin = load_nc(fname)
    else:
        fin = fname
    out = {}
    if fin.groups:
        for key in fin.groups.keys():
            out[key] = {}
            for k in fin.groups[key].variables.keys():
                out[key][k] = fin.groups[key].variables[k][...]
    else:
        for key in fin.variables.keys():
            out[key] = fin.variables[key][...]
    fin.close()
    return out 


def write_nc(
        fname, var_defs, out_vars, set_header, header_info, dim_defs, 
        overwrite=True, atts=None,
):
    fn = os.path.expanduser(fname)
    if overwrite:
        try:
            os.remove(fn)
        except:
            None
    else:
        assert not os.path.isfile(fn), \
        '%s already exists and overwrite set to False. Stopping...' % fn

    # Create netCDF file
    try:
        from netCDF4 import Dataset
        print('writing with netCDF4')
        rootgrp = Dataset(fn, 'w', format='NETCDF4')
    except:
        import scipy.io.netcdf as nc
        print('writing with scipy')
        rootgrp = nc.netcdf_file(fn, mode="w")

    if atts:
        rootgrp.setncatts(atts)


    write_grp(rootgrp, dim_defs, set_header, header_info, var_defs, out_vars)
    rootgrp.set_auto_mask(False)
    rootgrp.close()
    print('File written to %s' % fn)


def write_grp(grp, dim_defs, set_header, header_info, var_defs, out_vars):
    # write all the dimensions, variable definitions and variables into a group
    # (could be nested or overall group)

    # Define the dimensions 
    for k, v in dim_defs.items():
        grp.createDimension(k, v)  
    
    # Write the header stuff
    grp = set_header(grp, header_info)

    # Define variables 
    ncvars = {}  
    for key, var in var_defs.items():
        vd = [var['dims'],] if type(var['dims']) == str else var['dims']
        ncvars[key] = grp.createVariable(key, var['type'], vd)
        ncvars[key].units = var['units']
        ncvars[key].long_name = var['long_name']
        ncvars[key].set_auto_mask(False)
    grp.set_auto_mask(False)

    # Write to variables
    for key, var in out_vars.items():
        if (len(var.shape) == 0) or (len(var.shape) == 1): 
            ncvars[key][:] = var 
        elif len(var.shape) == 2:
            ncvars[key][:, :] = var 
        elif len(var.shape) == 3:
            ncvars[key][:, :, :] = var 
        elif len(var.shape) == 4:
            ncvars[key][:, :, :, :] = var 


def example_write_nc():
    def def_vars():
        stdin = {'dims':['npts', 'npts'], 'type': 'float'} 
        return {
            'testarr': dict({'units': 'none', 'long_name': 'test array to demonstrate code'}, **stdin),
        }   

    def set_header(rootgrp, out_vars):
        rootgrp.description = 'test nc for numpy array writing'
        return rootgrp

    out_fn = 'test.nc'
    out_vars = {'testarr': np.ones((10, 10)).asarray()}
    dim_defs = {'npts': len(out_vars['testarr'])}
    var_defs = def_vars()
    write_nc(out_fn, var_defs, out_vars, set_header, dim_defs, overwrite=True)


if __name__ == '__main__':
    print('writing example netCDF file to demonstrate code')




