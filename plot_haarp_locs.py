import numpy as np
from netCDF4 import Dataset
import julian as jd
import matplotlib.pyplot as plt 
import matplotlib as mpl
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
from plot_radar_fvel import plot_radar, tindex_data
import sys 
import pdb 


def main(
    inDir = 'data/netcdf/%Y/%m/',
    time = dt.datetime(2014, 4, 23, 8, 1),
    haarpLat=62.3883,
    haarpLon=-145.1505,
    radars = {
        'kod.d': [500, 1000], 
        'cvw': [2800, 3200],
        'cly': [3200, 3600],
    },
    ionosondes = ['GAKONA', 'EIELSON', 'IDAHONATIONALLAB'],
    ionoDir = '/Users/chartat1/fusionpp_data/ionosonde/',
):
    inDir = time.strftime(inDir)
    radarFnames = {}
    for radar in radars.keys():
        radarFnames[radar] = os.path.join(inDir, '%s.%s.nc' % (time.strftime('%Y%m%d'), radar)) 
    ionoFnames = {}
    for ionosonde in ionosondes:
        ionoFnames[ionosonde] = os.path.join(inDir, '%s.%s.nc' % (time.strftime('%Y%m%d'), radar)) 

    plot_data_locs([haarpLat, haarpLon], radarFnames, ionoFnames)
    """
    for radar, rg in radars.items():
        inFname = radarFnames[radar]
        print('plotting %s' % inFname)

        # bm = 8,
        #plotBeam(inFname, bm, radar)

        data = nc_utils.ncread_vars(inFname)
        rgi = (data['range'] > rg[0]) & (data['range'] < rg[1])
        # for k,v in data.items():
        #     data[k] = v[rgi]
        if 'kod' in radar:
            data['v'][:] = -1000
        else:
            data['v'][:] = 1000
        hdr = nc_utils.load_nc(inFname)

        time = dt.datetime(2014, 4, 23, 8, 1)

        axExtent=[-150, -120, 40, 70]
        #beams = 5, 6, 7, 8, 9, 10, 11, 12

        plot_radar(data, hdr.lat, hdr.lon, axExtent, time,) #beams)
        plt.plot(haarpLon, haarpLat, marker='.', color='red', transform=ccrs.PlateCarree())

    plt.show()
    """

def plot_data_locs(haarpLoc, radarFnames, ionoFnames, axExtent=[-180, 180, 40, 90]):


    # Load the radar locations
    radars = {}
    for r, fn in radarFnames.items():
        data = nc_utils.load_nc(fn)
        pdb.set_trace()
        # radars[r] = 
        

    # Plot the data locations on a map
    rp = -130, 55
    ax = plt.axes(projection=ccrs.Orthographic(*rp))
    data_crs = ccrs.PlateCarree()
    ax.add_feature(cfeature.OCEAN, zorder=0)
    ax.add_feature(cfeature.LAND, zorder=0, edgecolor='black')
    ax.add_feature(cfeature.BORDERS, linestyle=':')

    ax.set_global()
    ax.gridlines()
    ax.plot(haarpLoc[1], haarpLoc[0], marker='.', color='red', markersize=15, transform=data_crs)
    plt.show()
     


def plotBeam(inFname, bm, radarCode):

    plt.style.use('dark_background')
    plt.rcParams.update({'font.size': 18})
    fig, (ax1, ax2) = plt.subplots(nrows=2, figsize=(16, 9), gridspec_kw={'height_ratios': [1, 4]})
    plt.suptitle('Beam %i, %s: %s' % (bm, radarCode, times[0].strftime('%d %b %Y')))

    """
    1. narrow frequency plot
    """
    ax1.plot(times, tfreq/1E3, '.')
    ax1.set_xlim([times.min(), times.max()])
    ax1.set_ylim([8, 20])
    ax1.set_ylabel('Tx Freq. (MHz)')
    ax1.xaxis.set_major_formatter(plt.NullFormatter())
    ax1.xaxis.set_ticks_position('none') 

    """ 
    2. Velocity plot, not yet with alpha = power
    """
    # define scale, with white at zero
    colormap = 'bwr'  #'bwr'
    cmap = plt.get_cmap(colormap)
    norm = plt.Normalize(-1000, 1000)
    vel = np.fliplr(vel).T
    gflg = np.fliplr(gflg).T 
    gflg[np.flip(rg) < 1000, :] *= np.nan
    cm = cmap(norm(vel))
    cm[gflg==1, 0] = 0
    cm[gflg==1, 1] = 1
    cm[gflg==1, 2] = 0

    # set alpha values of pixels - couldn't make it do anything
    pmax = 20
    pwr = np.fliplr(pwr).T
    al = plt.Normalize(0, 20, clip=True)(pwr)
    
    # Plot the scatter
    img = ax2.imshow(cm, aspect='auto', extent=[0, 24, rg.min(), rg.max()], cmap=colormap)
    pos = ax2.get_position()
    cbaxes = fig.add_axes([0.85, 0.12, 0.02, 0.53]) 
    cb = mpl.colorbar.ColorbarBase(cbaxes, cmap=cmap, norm=norm, label='Velocity (m/s)')
    ax2.set_xlabel('Hour (UT)')
    ax2.set_ylabel('Virt. Range (km)')
    ax2.grid(which='both')

    # Resize ax2
    pos2 = [pos.x0, pos.y0, pos.width * 0.9, pos.height]
    ax2.set_position(pos2)

    # Resize ax1
    pos = ax1.get_position()
    pos2 = [pos.x0, pos.y0, pos.width * 0.9, pos.height]
    ax1.set_position(pos2)

    plt.show()


def loadBeam(inFname, bm):
    data = nc_utils.ncread_vars(inFname)
    hdr = nc_utils.load_nc(inFname)
   
    rsep = hdr.rsep
    rmax = hdr.maxrg
    radarLat = hdr.lat
    radarLon = hdr.lon
    bmInd = data['beam'] == bm
    bmdata = {}
    flds = 'p_l', 'v', 'mjd', 'lat', 'lon', 'range', 'gflg'
    for fld in flds:
        bmdata[fld] = data[fld][bmInd]

    rg_idx = np.arange(rmax) 
    rg = (np.arange(rmax + 1) * rsep + data['range'].min()).astype('int')

    mjds = np.unique(bmdata["mjd"])
    pwr = np.zeros((len(mjds), len(rg))) * np.nan
    vel = np.zeros((len(mjds), len(rg))) * np.nan
    gflg = np.zeros((len(mjds), len(rg))) * np.nan
    for t, mjd in enumerate(mjds):
        ti = bmdata['mjd'] == mjd
        rgi = np.searchsorted(rg, bmdata['range'][ti])
        pwr[t, rgi] = bmdata['p_l'][ti]
        vel[t, rgi] = bmdata['v'][ti]
        gflg[t, rgi] = bmdata['gflg'][ti]

    times = np.array([jd.from_jd(mjd, fmt="mjd") for mjd in data['mjd_unique']])
    return times, rg, pwr, vel, data['tfreq'], data['noise.sky'], rsep, gflg




if __name__ == '__main__':
    main()





