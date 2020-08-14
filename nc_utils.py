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
    for key in fin.variables.keys():
        out[key] = fin.variables[key][...]
    fin.close()
    return out 


def convert_timestrs(varns, timestr,\
         datevarnames=['ICON_L1_FUVA_SWP_Start_Times', 'ICON_L1_FUVA_SWP_Stop_Times', 'ICON_L1_FUVA_SWP_Center_Times']):
    if type(datevarnames) is str:
        datevarnames = [datevarnames]
    for v in datevarnames:
        for (ind), s in np.ndenumerate(varns[v]):
            varns[v][ind] = dt.datetime.strptime(s, timestr)
    return varns


def write_nc(fname, var_defs, out_vars, set_header, dim_defs, overwrite=True):

    if overwrite:
        try:
            os.remove(fname)
        except:
            None
    else:
        assert not os.path.isfile(fname), \
        '%s already exists and overwrite set to False. Stopping...' % fname

    # Create netCDF file
    #rootgrp = Dataset(fn, 'r', format='NETCDF4')
    rootgrp = nc.netcdf_file(fname, mode="w")

    # Define the dimensions
    for k, v in dim_defs.items():
        rootgrp.createDimension(k, v)  
    
    # Write the header stuff
    rootgrp = set_header(rootgrp, out_vars)

    # Define variables 
    ncvars = {}  
    for key, var in var_defs.items():
        vd = [var['dims'],] if type(var['dims']) == str  else var['dims']
        ncvars[key] = rootgrp.createVariable(key, var['type'], vd)
        ncvars[key].units = var['units']
        ncvars[key].long_name = var['long_name']

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
    rootgrp.close()
    print('File written to %s' % fname)



