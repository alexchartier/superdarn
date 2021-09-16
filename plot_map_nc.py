import os
import sys 
import numpy as np
import nvector as nv
import pydarn
import datetime as dt
import aacgmv2
import nc_utils
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

import pdb 

__author__ = "Alex Chartier"
__copyright__ = "Copyright 2021, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

fn = 'output.nc'
axext = [-180, 180, 45, 90]

data = nc_utils.ncread_vars(fn)
times = np.array([dt.datetime.fromtimestamp(t) for t in data['times']])

data['phi'] = np.cos(np.deg2rad(data['gAz'])) * data['vel']
data['theta'] = np.sin(np.deg2rad(data['gAz'])) * data['vel']

#for t in np.unique(times):
tind = times == times[0]

data_t = {}
for k, v in data.items():
    data_t[k] = v[tind]


# set up the plot 
ax = plt.axes(projection=ccrs.EquidistantConic(standard_parallels = (90,90)))
ax.coastlines()
ax.gridlines()
ax.set_extent(axext, ccrs.PlateCarree())


# plot vectors
plt.quiver(
    data_t['gLon'], data_t['gLat'], data_t['phi'], data_t['theta'],
    color = "gray", transform=ccrs.PlateCarree(), width=.002,
)   
plt.show()
    






