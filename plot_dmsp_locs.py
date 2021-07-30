import nc_utils
import matplotlib.pyplot as plt 
import numpy as np
import datetime as dt



pot_file = "/Users/chartat1/pymix/data/sami3/sami3_may23_phi.nc"
dmsp_file = 'data/dmsp/dms_20140523_15s1.001.nc'

pot = nc_utils.ncread_vars(pot_file)
dmsp = nc_utils.ncread_vars(dmsp_file)
dmsp['times'] = np.array([dt.datetime.fromtimestamp(ts) for ts in dmsp['timestamps']])

breakpoint()

