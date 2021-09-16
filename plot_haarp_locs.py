import numpy as np
from netCDF4 import Dataset
import julian as jd
import matplotlib.pyplot as plt 
import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.colors as colors
from matplotlib.transforms import offset_copy
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
from scipy.interpolate import interp1d
import shapely.geometry as sgeom
import math
import os
import statistics
import filter_radar_data
import nc_utils
import glob
import datetime as dt
from plot_radar_fvel import plot_radar, tindex_data
from radFov import calcFieldPnt
import sys 
import pdb 


def main(
    inDir = 'data/netcdf/%Y/%m/',
    startTime = dt.datetime(2014, 4, 23),
    endTime = dt.datetime(2014, 4, 23, 12, 0),
    timeStep = dt.timedelta(minutes = 1),
    haarpLat=62.3883,
    haarpLon=-145.1505,
    radars = {
        'kod.c': [[500, 1000], 9],
        'cvw': [[2800, 3200], 9],
        'cly': [[3200, 3600], 4],
    },
    ionosondes = ['GAKONA', 'EIELSON', 'IDAHONATIONALLAB'],
    ionoDir = '/Users/chartat1/fusionpp_data/ionosonde/',
    outFnFmt = '/Users/chartat1/superdarn/plots/haarp_backscatter/%Y%m%d_%H%M.jpg',
):
    inDir = startTime.strftime(inDir)
    radarFnames = {}
    for radar in radars.keys():
        radarFnames[radar] = os.path.join(inDir, '%s.%s.nc' % (startTime.strftime('%Y%m%d'), radar)) 
    ionoFnames = {}
    for ionosonde in ionosondes:
        ionoFnames[ionosonde] = os.path.join(ionoDir, '%s_%s.nc' % (ionosonde, startTime.strftime('%Y%m%d'))) 

    # plot_data_locs([haarpLat, haarpLon], radarFnames, ionoFnames)
    tlim = [dt.datetime(2014, 4, 23, 7, 10), dt.datetime(2014, 4, 23, 8, 30)] 
    for radar, rg_bm in radars.items():
        rlim = rg_bm[0]
        bm = rg_bm[1]
        plotBeam(radarFnames[radar], bm, radar) #, tlim, rlim)

    time = startTime
    while time < endTime:
        plot_radars(radars, radarFnames, time, haarpLat, haarpLon, time.strftime(outFnFmt))
        time += timeStep



def plot_radars(radars, radarFnames, time, haarpLat, haarpLon, outFname=None):

    rp = -130, 55
    transform = ccrs.Geodetic()
    ax = plt.axes(projection=ccrs.Orthographic(*rp))
    ax.add_feature(cfeature.LAND)
    ax.add_feature(cfeature.OCEAN)
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.BORDERS, linestyle=':')
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(), draw_labels=True,
        linewidth=0.5, color='gray', linestyle='-',
    )
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER

    style = {'size': 10, 'color': 'gray'}
    gl.xlabel_style = style
    gl.ylabel_style = style
    gl.top_labels = False
    gl.right_labels = False

    ax.set_global()

    for radar, rg_b in radars.items():
        inFname = radarFnames[radar]
        print('plotting %s' % inFname)

        bm = rg_b[1]
        rg = rg_b[0]

        data = nc_utils.ncread_vars(inFname)
        rgi = (data['range'] > rg[0]) & (data['range'] < rg[1])
        for k,v in data.items():
            data[k] = v[rgi]
        if 'kod' in radar:
            data['v'][:] = -1000
        else:
            data['v'][:] = 1000
        hdr = nc_utils.load_nc(inFname)
        ax.plot(
            hdr.lon, hdr.lat,
            color="k", marker="o",transform=transform,
        )
        ax = plot_radar(ax, data, hdr.lat, hdr.lon, time, )

    ax.plot(haarpLon, haarpLat, marker='o', color='red', transform=transform)

    # Plot the radar labels 
    geodetic_transform = ccrs.Geodetic()._as_mpl_transform(ax)
    text_transform = offset_copy(geodetic_transform, units='dots', x=-25) 
    for rn, radar in radars.items(): 
        rn = rn.split('.')[0].upper()
        plt.text(radar['lon'], radar['lat'], rn,
                 verticalalignment='center', horizontalalignment='right',
                 transform=text_transform,
                 bbox=dict(facecolor='sandybrown', boxstyle='round'))

    ax.xaxis.zoom(3)
    ax.yaxis.zoom(3)
    plt.suptitle(time.strftime('%Y %b %d %H:%M'))
    if outFname:
        plt.savefig(outFname)
        print('Saved to %s' % outFname)
    else:
        plt.show()
    plt.close()


def plot_data_locs(haarpLoc, radarFnames, ionoFnames, axExtent=[-180, 180, 40, 90]):

    slant_range = 4000
    # Load the radar locations
    radars = {}
    for r, fn in radarFnames.items():
        radar = nc_utils.load_nc(fn)
        fovpts = np.ones((len(radar.brng_at_15deg_el), 2))
        for ind, brng in enumerate(radar.brng_at_15deg_el):
            beam_off = brng - radar.boresight
            fovpts[ind, :] = calcFieldPnt(
                radar.lat, radar.lon, radar.alt, radar.boresight, beam_off, slant_range, 
                hop=2, adjusted_sr=False, altitude=300,
            )
        radars[r] = {
            'lon': radar.lon,
            'lat': radar.lat,
            'alt': radar.alt,
            'fovpts': fovpts, 
        }

    ionosondes = {}
    # Load the ionosondes
    for io, fn in ionoFnames.items():
        iono = nc_utils.load_nc(fn)
        lon = iono.lon
        if lon > 180:
            lon -= 360
        ionosondes[io] = [iono.lat, lon]

    # Plot the data locations on a map
    rp = -130, 55
    ax = plt.axes(projection=ccrs.Orthographic(*rp))
    data_crs = ccrs.Geodetic()
    ax.add_feature(cfeature.OCEAN, zorder=0)
    ax.add_feature(cfeature.LAND, zorder=0, edgecolor='black')
    ax.add_feature(cfeature.BORDERS, linestyle=':')

    ax.set_global()
    # ax.gridlines()

    # Plot the radars and FOVs
    for rn, radar in radars.items(): 
        ax.plot(radar['lon'], radar['lat'], marker='.', color='k', markersize=5, transform=data_crs)
        for ind, brng in enumerate(radar['fovpts'][:, 0]):
            ax.plot(
                [radar['lon'], radar['fovpts'][ind, 1]], [radar['lat'],radar['fovpts'][ind, 0]],
                color='k', transform=data_crs, linewidth=0.3, 
            )
    ax.plot(haarpLoc[1], haarpLoc[0], marker='.', color='red', markersize=15, transform=data_crs)
  
    # Plot the radar labels 
    geodetic_transform = ccrs.Geodetic()._as_mpl_transform(ax)
    text_transform = offset_copy(geodetic_transform, units='dots', x=-25) 
    for rn, radar in radars.items(): 
        rn = rn.split('.')[0].upper()
        plt.text(radar['lon'], radar['lat'], rn,
                 verticalalignment='center', horizontalalignment='right',
                 transform=text_transform,
                 bbox=dict(facecolor='sandybrown', boxstyle='round'))
        
    # Plot the ionosondes
    for rn, iono in ionosondes.items(): 
        
        ax.plot(iono[1], iono[0], marker='.', color='b', markersize=7, transform=data_crs)
        if rn == 'GAKONA':
            plt.text(iono[1] + 3, iono[0], 'HAARP',
                     verticalalignment='center', horizontalalignment='left',
                     transform=text_transform,
                     bbox=dict(facecolor='red', boxstyle='round'))
        elif rn == 'EIELSON':
            plt.text(iono[1], iono[0], 'Eielson',
                     verticalalignment='center', horizontalalignment='right',
                     transform=text_transform,
                     bbox=dict(facecolor='lightblue', boxstyle='round'))
        elif rn == 'IDAHONATIONALLAB':
            plt.text(iono[1] + 3, iono[0], 'Idaho National Lab',
                     verticalalignment='center', horizontalalignment='left',
                     transform=text_transform,
                     bbox=dict(facecolor='lightblue', boxstyle='round'))

    plt.show()
     


def plotBeam(inFname, bm, radarCode, tlim=None, rlim=None):

    times, rg, pwr, vel, tfreq, rsep, gflg = loadBeam(inFname, bm)
    if not tlim:
        tlim = [times.min(), times.max()]

    plt.style.use('dark_background')
    plt.rcParams.update({'font.size': 18})
    fig, (ax1, ax2) = plt.subplots(nrows=2, figsize=(16, 9), gridspec_kw={'height_ratios': [1, 4]})
    plt.suptitle('%s Beam %i' % (radarCode.split('.')[0].upper(), bm))

    """
    1. narrow frequency plot
    """
    ax1.plot(times, tfreq/1E3, '.')
    ax1.set_xlim(tlim)
    ax1.set_ylim([8, 20])
    ax1.set_ylabel('Tx Freq. (MHz)')
    ax1.xaxis.set_major_formatter(plt.NullFormatter())
    ax1.xaxis.set_ticks_position('none') 

    """ 
    2. Velocity plot, not yet with alpha = power
    """

    locator = mdates.AutoDateLocator(minticks=3, maxticks=7)
    formatter = mdates.ConciseDateFormatter(locator)
    ax2.xaxis.set_major_locator(locator)
    ax2.xaxis.set_major_formatter(formatter)

    # define limits
    if not rlim:
        rlim = [rg.min(), rg.max()]
    tlim_hr = [dn_to_dechr(tlim[0]), dn_to_dechr(tlim[1])]

    # define scale, with white at zero
    colormap = 'bwr'  #'bwr'
    cmap = plt.get_cmap(colormap)
    norm = plt.Normalize(-1000, 1000)
    vel = vel.T
    gflg = gflg.T 
   
    #  regrid the data 
    times_bnd = []
    t = tlim[0]
    while t <= tlim[1]:
        times_bnd.append(t)
        t += dt.timedelta(seconds=5)
    times_bnd = np.array(times_bnd)
    vel_gridded = np.ones((len(times_bnd)-1, len(rg)))
    gflg_gridded = np.ones((len(times_bnd)-1, len(rg)))
    fn = interp1d(to_float(times, times[0]), vel[0, :])
    for ind in range(len(rg)):
        fn.y = vel[ind, :]
        vel_gridded[:, ind] = fn(to_float(times_bnd[:-1], times[0]))
        fn.y = gflg[ind, :]
        gflg_gridded[:, ind] = fn(to_float(times_bnd[:-1], times[0]))

    gflg_gridded[gflg_gridded == 0] *= np.nan
    # gflg_gridded[:, rg<1000] *= np.nan

    rg_step = np.unique(np.diff(rg))[0]
    rg_bnd = np.arange(rg[0] - rg_step / 2, rg[-1] + rg_step, rg_step)
    
    # Plot the scatter
    cMap = colors.ListedColormap(['g'])
    ax2.pcolormesh(times_bnd, rg_bnd, vel_gridded.T, vmin=-1000, vmax=1000, cmap=colormap)
    ax2.pcolormesh(times_bnd, rg_bnd, gflg_gridded.T, cmap=cMap)
    pos = ax2.get_position()
    cbaxes = fig.add_axes([0.85, 0.12, 0.02, 0.53]) 
    cb = mpl.colorbar.ColorbarBase(cbaxes, cmap=cmap, norm=norm, label='Velocity (m/s)')
    ax2.set_xlim(tlim)
    ax2.set_ylim(rlim)
    ax2.set_xlabel('Hour (UT)')
    ax2.set_ylabel('Virtual Range (km)')
    ax2.grid(which='both')

    # Resize ax2
    pos2 = [pos.x0, pos.y0, pos.width * 0.9, pos.height]
    ax2.set_position(pos2)

    # Resize ax1
    pos = ax1.get_position()
    pos2 = [pos.x0, pos.y0, pos.width * 0.9, pos.height]
    ax1.set_position(pos2)

    plt.show()

def dn_to_dechr(dn):
    return dn.hour + dn.minute / 60 + dn.second / 3600
    

def loadBeam(inFname, bm):
    data = nc_utils.ncread_vars(inFname)
    hdr = nc_utils.load_nc(inFname)
   
    rsep = hdr.rsep_km
    rmax = hdr.maxrangegate
    radarLat = hdr.lat
    radarLon = hdr.lon
    bmInd = data['beam'] == bm
    bmdata = {}
    flds = 'p_l', 'v', 'mjd', 'lat', 'lon', 'range', 'gflg', 'tfreq'
    for fld in flds:
        bmdata[fld] = data[fld][bmInd]

    rg_idx = np.arange(rmax) 
    rg = (np.arange(rmax + 1) * rsep + data['range'].min()).astype('int')

    mjds = np.unique(bmdata["mjd"])
    pwr = np.zeros((len(mjds), len(rg))) * np.nan
    vel = np.zeros((len(mjds), len(rg))) * np.nan
    gflg = np.zeros((len(mjds), len(rg))) * np.nan
    tfreq = np.zeros((len(mjds), 1)) * np.nan
    for t, mjd in enumerate(mjds):
        ti = bmdata['mjd'] == mjd
        rgi = np.searchsorted(rg, bmdata['range'][ti])
        pwr[t, rgi] = bmdata['p_l'][ti]
        vel[t, rgi] = bmdata['v'][ti]
        gflg[t, rgi] = bmdata['gflg'][ti]
        tfreq[t] = bmdata['tfreq'][ti][0]

    times = np.array([jd.from_jd(mjd, fmt="mjd") for mjd in mjds])
    return times, rg, pwr, vel, tfreq, rsep, gflg

def to_float(dlist, epoch):
    return [(d - epoch).total_seconds() for d in dlist]


if __name__ == '__main__':
    main()





