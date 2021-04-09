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
from plot_radar_fvel import plot_vels_at_time, tindex_data
import sys 
import pdb 


def main(
    inDir = 'data/netcdf/%Y/%m/',
    radarCode = 'kod',
    stime = dt.datetime(2014, 4, 23),
    etime = dt.datetime(2014, 4, 24),
    bm = 9,
    haarpLat=62.4,
    haarpLon=-145.2,
):
    inFname = os.path.join(stime.strftime(inDir), stime.strftime('%Y%m%d') + '.%s.c.nc' % radarCode)
    print('plotting %s' % inFname)
    plotBeam(inFname, bm, radarCode)

    data = nc_utils.ncread_vars(inFname)
    hdr = nc_utils.load_nc(inFname)
    mjd0= jd.to_jd(dt.datetime(2014, 4, 23, 6, 1), fmt='mjd')
    mjd1= jd.to_jd(dt.datetime(2014, 4, 23, 6, 1,2), fmt='mjd')
    mjds= data['mjd_short'][(data['mjd_short'] > mjd0) & (data['mjd_short'] < mjd1)]
    data_t = tindex_data(data, mjds[0])

    ax = plot_vels_at_time(data_t, hdr.lat, hdr.lon, axExtent=[-150, -130, 50, 70])
    plt.plot(haarpLon, haarpLat, marker='.', color='red', transform=ccrs.PlateCarree())
    plt.show()



def plotBeam(inFname, bm, radarCode):

    times, rg, pwr, vel, tfreq, skynoise, rsep, = loadBeam(inFname, bm)
    plt.style.use('dark_background')
    plt.rcParams.update({'font.size': 18})
    fig, (ax1, ax2) = plt.subplots(nrows=2, figsize=(16, 9), gridspec_kw={'height_ratios': [1, 4]})
    plt.suptitle('%s: %s' % (radarCode, times[0].strftime('%d %b %Y')))

    """
    1. narrow frequency plot
    """
    ax1.plot(times, tfreq/1E3)
    ax1.set_xlim([times.min(), times.max()])
    ax1.set_ylim([8, 20])
    ax1.set_ylabel('Tx Freq. (MHz)')
    ax1.xaxis.set_major_formatter(plt.NullFormatter())
    ax1.xaxis.set_ticks_position('none') 

    """ 
    2. Velocity plot, not yet with alpha = power
    """
    # define scale, with white at zero
    colormap = 'PiYG'  #'bwr'
    cmap = plt.get_cmap(colormap)
    norm = plt.Normalize(-1000, 1000)
    vel = np.fliplr(vel).T
    cm = cmap(norm(vel))

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


def loadBeam(inFname, bm,):
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

    times = np.array([jd.from_jd(mjd, fmt="mjd") for mjd in data["mjd_short"]])
    pwr = np.zeros((len(times), len(rg))) * np.nan
    vel = np.zeros((len(times), len(rg))) * np.nan
    for t, mjd in enumerate(data["mjd_short"]):
        ti = bmdata['mjd'] == mjd
        rgi = np.searchsorted(rg, bmdata['range'][ti])
        pwr[t, rgi] = bmdata['p_l'][ti]
        vel[t, rgi] = bmdata['v'][ti]

    return times, rg, pwr, vel, data['tfreq'], data['noise.sky'], rsep




if __name__ == '__main__':
    main()





