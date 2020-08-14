# -*- coding: utf-8 -*-

"""

Created on Sat Jun 13 19:48:06 2020

@author: Devasena

"""

import numpy as np
from netCDF4 import Dataset
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy
import datetime as dt
from scipy import interpolate
from plot_vel import plot_data
from nc_utils import ncread_vars
import pdb


def main():
    in_fname_fmt = "data/sami_ampere_weimer/sami3_tec_may_2014/%m-%d/netcdf/sami3_tec_%m%d.nc"
    time = dt.datetime(2014, 5, 22, 7, 0)

    modData = ncread_vars(time.strftime(in_fname_fmt))
    for k, v in modData.items():
        modData[k] = np.array(v)
    hrs = np.floor(modData['time'])
    mins = (modData['time'] - hrs) * 60
    modTime = []
    for ind, hr in enumerate(hrs):
        modTime.append(dt.datetime(time.year, time.month, time.day, hr, mins[ind]))
    modTime = np.array(modTime)
    titlestr = time.strftime("SAMI/AMPERE TEC @ %H:%M UT %Y/%b/%d")
    plot_data(
        modData['lat0'][:, 0, :], modData['lon0'][:, 0, :], 
        np.squeeze(modData['tec'][modTime == time, :, :]), titlestr,
    )
   

def plot_data(lat, lon, tec, titlestr, axext=[-180, 180, 45, 90]):

    # set up the plot 
    ax = plt.axes(projection=ccrs.Orthographic(-10, 45))

    crs = ccrs.RotatedPole(pole_longitude=0, pole_latitude=70)
    ax.add_feature(cartopy.feature.OCEAN, zorder=0)
    ax.add_feature(cartopy.feature.LAND, zorder=0, edgecolor='black')

    ax.set_global()
    
    # make the plot
    lon[lon > 180] -= 360
    plt.contourf(lon, lat, tec, transform=crs)   
    ax.gridlines()

    plt.suptitle(titlestr)
    plt.show()


if __name__ == '__main__':

    main()







