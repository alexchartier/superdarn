# -*- coding: utf-8 -*-

"""

Created on Sat Jun 13 19:48:06 2020

@author: Devasena

"""

import numpy as np
from netCDF4 import Dataset
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import datetime as dt
from scipy import interpolate
import pdb

def main():
    in_fname_fmt = "data/sami_ampere_weimer/sami3_utheta_uphi_300_%m%d.nc"
    time = dt.datetime(2014, 5, 22, 7, 0)
    radar_fname_fmt = '%Y%m%d.wal.nc'

    modData = load_data(time.strftime(in_fname_fmt), ["lat0", "lon0", "utheta", "uphi", "time"])
    radarData = load_data(time.strftime(radar_fname_fmt), ["vel", "geolon", "geolat", "mjd"])
    interp_model_to_obs(modData, radarData, time)
    
    #plot_data(data, time)

#load data out of netCDF file and into python dictionary
def load_data(in_fname, var_names):

    #extracting the data
    fileHandle = Dataset(in_fname, mode="r+")
    print(fileHandle)
    print(fileHandle.variables)
    
    data = {}

    #putting data into the dictionary
    for var_n in var_names:
        data[var_n] = {
            'units': fileHandle.variables[var_n].units,
            'vals': fileHandle.variables[var_n][...],
        }

    fileHandle.close()

    return data

def plot_data(radarData, nvel, evel, time, axext=[-180, 180, 45, 90]):

    # set up the plot 
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.coastlines()
    ax.gridlines()
    #ax.set_extent(axext, ccrs.PlateCarree())
    
    # make the plot
    plt.quiver(
        radarData["geolon"]["vals"], radarData["geolat"]["vals"], 
        nvel, 
        evel, 
        transform=ccrs.PlateCarree(), regrid_shape=24, width=.005,
    )

    plt.suptitle(time.strftime("SAMI/AMPERE ExB drift vels at %H:%M UT on %d %b %Y"))
    plt.show()
    plt.close()
    
    
def interp_model_to_obs(modData, radarData, time):
    
    hour = time.hour + time.minute / 60
    tdiffs = np.abs(modData["time"]["vals"] - hour)
    hrind = tdiffs == np.min(tdiffs) 

    if len(hrind) == 2:
        hrind == hrind[0]
    
    pdb.set_trace() 
    nvel = interpolate.interp2d(
        modData["lon0"]["vals"], modData["lat0"]["vals"], 
        modData["utheta"]["vals"][hrind,:,:],
    )
    
    evel = interpolate.interp2d(
        modData["lon0"]["vals"], modData["lat0"]["vals"], 
        modData["uphi"]["vals"][hrind,:,:],
    )
   
    pdb.set_trace() 
    zNorth = nvel(radarData["geolon"]["vals"], radarData["geolat"]["vals"])
    eNorth = evel(radarData["geolon"]["vals"], radarData["geolat"]["vals"])
    
    return zNorth, eNorth
    
    

if __name__ == '__main__':

    main()







