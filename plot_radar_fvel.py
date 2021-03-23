# -*- coding: utf-8 -*-

"""
Created on Sat Jun 13 19:48:06 2020

@author: Devasena & Alex
"""

import numpy as np
from netCDF4 import Dataset
import julian as jd
import matplotlib.pyplot as plt
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import math
import os
import statistics
import filter_radar_data
import nc_utils
import glob
import datetime as dt
from run_meteorproc import get_radar_params, id_hdw_params_t
import sys
import pdb


def main(
    time, radarCode, inDir,
    outDir=None,
    hdwDatDir='../rst/tables/superdarn/hdw/',
):
    radarInfo = get_radar_params(hdwDatDir)
   
    inFname = os.path.join(time.strftime(inDir), time.strftime('%Y%m%d') + '.%s.nc' % radarCode)
    if outDir:
        outDir = os.path.join(outDir, radarCode)
        print('Writing to %s' % outDir)
        plot_one_radar(inFname, radarInfo, outDir)
    else:
        plot_one_radar(inFname, radarInfo)


    # inFnameFmt = 'data/sd_netcdf/%Y/%m/%Y%m%d*.nc'
    # plot_all_radars(time, inFnameFmt, radarInfo)


def plot_all_radars(time, inFnameFmt, radarInfo):
    """ 
    Loop through the files for a given day and plot them all on the same map
    """
    inFnames = glob.glob(time.strftime(inFnameFmt))
    axExtent = [-180, 180, 30, 90]
    for inFname in inFnames:
        radarCode = inFname.split('.')[1]
        print("Processing %s" % radarCode)
        data = nc_utils.ncread_vars(inFname)
        # data = filter_radar_data.filter_sd_file(inFname)
        
        # Find the closest MJD time to the requested time
        radarTimes = np.array([jd.from_jd(mjd, fmt="mjd") for mjd in data["mjd"]])
        timeIndex = np.argmin(np.abs(radarTimes - time))
        if np.abs(radarTimes - time).min() > dt.timedelta(seconds=60):
            continue
        mjdTime = data['mjd'][timeIndex]
        radarInfo_t = id_hdw_params_t(time, radarInfo[radarCode])
        plot_vels_at_time(data, mjdTime, radarCode, radarInfo_t, axExtent)
    
    clb = plt.colorbar()
    clb.ax.set_title("Velocity")
    clb.set_label("m/s", rotation=270)
    plt.suptitle("All F Scatter\n%s" % (radarCode, time.strftime('%Y%b%d_%H%M')))

    plt.show()


def plot_one_radar(inFname, radarInfo, outDir=None, axExtent=[-180, 180, 30, 90]):
    """ 
    plot F region scatter on a map - does a whole day's worth of files
    """
    
    radarCode = inFname.split('.')[1]

    # data = nc_utils.ncread_vars(inFname)  # go to this once the filtering is in the netCDFs
    print('Filtering %s' % inFname)
    data = filter_radar_data.filter_sd_file(inFname)
    day = jd.from_jd(data["mjd"][0], fmt="mjd")
    if outDir:
        os.makedirs(outDir, exist_ok=True)

    uniqueTimes = np.unique(data["mjd"])
    for mjdTime in uniqueTimes:
        print(mjdTime)
        time = jd.from_jd(mjdTime, fmt="mjd")
        radarInfo_t = id_hdw_params_t(time, radarInfo[radarCode])
        plot_vels_at_time(data, mjdTime, radarCode, radarInfo_t, axExtent)
    
        clb = plt.colorbar()
        clb.ax.set_title("Velocity")
        clb.set_label("m/s", rotation=270)
        timeStr = time.strftime('%Y%b%d_%H%M')
        plt.suptitle("%s - F Scatter\n%s" % (radarCode, timeStr))

        if outDir:
            outFname = os.path.join(outDir, "%s.png" % timeStr)
            print('Writing to %s' % outFname)
            plt.savefig(outFname, dpi=300)
            plt.close()
        else:
            plt.show()


def plot_vels_at_time(data, mjdTime, radarCode, radarInfo, axExtent):
    # Plot the radar velocities on a map
    # Flags: 0- F 1- gnd 2 coll, 3 other 

    variables = ["geolon", "geolat", "mjd", "vel", "bm", "km"]
    fsFlag = data["gs"] == 0

    # Select the F scatter at the relevant time
    timeIndex = data["mjd"] == mjdTime
    time = jd.from_jd(mjdTime, fmt="mjd")
    idx = timeIndex & fsFlag
    fsLatTimed = data["geolat"][idx]
    fsLonTimed = data["geolon"][idx]
    fsVelTimed = data["vel"][idx]

    ax = plt.axes(projection=ccrs.NorthPolarStereo())
    ax.add_feature(cfeature.LAND)
    ax.add_feature(cfeature.OCEAN)
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.BORDERS, linestyle=':')
    ax.add_feature(cfeature.LAKES, alpha=0.5)
    ax.add_feature(cfeature.RIVERS)


    ax.set_extent(axExtent, ccrs.PlateCarree())
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(), draw_labels=True,
        linewidth=2, color='gray', alpha=0.5, linestyle='-',
    )

    plt.scatter(
        fsLonTimed, fsLatTimed, s=0.2,  
        c=fsVelTimed, cmap="Spectral_r",  
        vmin=-1000, vmax=1000, transform=ccrs.PlateCarree(),
    )

    plt.plot(
        radarInfo['glon'], radarInfo['glat'], 
        color="red", marker="x", transform=ccrs.PlateCarree(),
    )

    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER

    style = {'size': 10, 'color': 'gray'}
    gl.xlabel_style = style 
    gl.ylabel_style = style
    gl.top_labels = False
    gl.right_labels = False  


if __name__ == '__main__':
    args = sys.argv
    assert len(args) >= 4, 'Should have 3-4x args, e.g.:\n' + \
        'python3 plot_radar_fvel.py 2020,1,1 sas ' + \
        'data/netcdf/%Y/%m/ data/plots/ '

    time = dt.datetime.strptime(args[1], '%Y,%m,%d')

    argv = [time,] + args[2:] 
    main(*argv)
    





