import nvector as nv
import numpy as np
import nc_utils
import os
import sys
import matplotlib.pyplot as plt
import datetime as dt
import jdutil
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib

font = {'size'   : 18}

matplotlib.rc('font', **font)

"""
Demonstrate velocity vector bearing calculation using nvector
Plots the fitACF-level nc files
"""

wgs84 = nv.FrameE(name='WGS84')
depth = 0  # nvector uses depths in m


def main(
    fname=os.path.expanduser('~/Downloads/20031029.han.v3.0.despeckled.nc'),
):
    sd_data, sdrad = nc_utils.ncread_vars(fname), nc_utils.load_nc(fname)
    for bmnum in range(16):
        plot_rti(sd_data, sdrad, bmnum)
        plt.savefig(f'plots/beam_{bmnum}.png')

    rlat, rlon, lats, lons, vels = load_example_data(fname)
    brng_deg = calc_bearings(rlat, rlon, lats, lons)
    # plot_quiver(rlat, rlon, lats, lons, vels, brng_deg, fname)


def plot_rti(sd_data, sdrad, bmnum=0):

    bmidx = sd_data['beam'] == bmnum
    #tidx = sd_data['mjd'] == dt_to_mjd(time)
    idx = bmidx #np.logical_and(bmidx, tidx)


    ranges = np.linspace(0, int(sdrad.rsep_km * sdrad.maxrangegate), 
        int(sdrad.maxrangegate) +1)
    times = np.arange(0, 60 * 24) 
    sdtime = np.round( (sd_data['mjd'] - np.floor(sd_data['mjd'])) * 60 * 24)

    pwr = np.zeros((len(times), len(ranges))) * np.nan
    vel = np.zeros((len(times), len(ranges))) * np.nan
    for ind, val in enumerate(sd_data['p_l'][idx]):
        pwr[times == sdtime[idx][ind], ranges == sd_data['range'][idx][ind]] = val 
        vel[times == sdtime[idx][ind], ranges == sd_data['range'][idx][ind]] = sd_data['v'][idx][ind]

    fig, ax = plt.subplots(2)
    fig.set_figheight(6)
    fig.set_figwidth(12)
    plt.suptitle(f"Beam {bmnum}: {sdrad.brng_at_15deg_el[bmnum]:,.1f} degrees East of North")
    im0 = ax[0].pcolor(times / 60, ranges, vel.T, vmin=-200, vmax=200, cmap='bwr')
    im1 = ax[1].pcolor(times / 60, ranges, pwr.T)
    ax[1].set_xlabel('Hour (UT)')

    for pn in range(2):
        ax[pn].set_ylabel('Range (km)')
        ax[pn].grid(which='major', color='k', linewidth=0.1)
        ax[pn].grid(which='minor', color='k', linewidth=0.02)
        ax[pn].minorticks_on()

    divider = make_axes_locatable(ax[0])
    cax = divider.append_axes('right', size='3%', pad=0.05)
    cbar = fig.colorbar(im0, cax=cax, orientation='vertical')
    cbar.set_label('Vel. (m/s)')
    divider = make_axes_locatable(ax[1])
    cax = divider.append_axes('right', size='3%', pad=0.05)
    cbar = fig.colorbar(im1, cax=cax, orientation='vertical')
    cbar.set_label('SNR (dB)')


def load_example_data(fname):
    # load the reference ellipsoid and the data
    sd_data = nc_utils.ncread_vars(fname)
    sdrad = nc_utils.load_nc(fname)

    # get the radar location
    rlat = sdrad.lat
    rlon = sdrad.lon

    # just take the first 100 observations to demonstrate
    lats = sd_data['lat'][:100]
    lons = sd_data['lon'][:100]
    vels = sd_data['v'][:100]

    [_, unique_ind_lat] = np.unique(lats, return_index=True)
    [_, unique_ind_lon] = np.unique(lons, return_index=True)
    unique_ind = unique_ind_lat[np.logical_and(unique_ind_lat, unique_ind_lon)]
    lats = lats[unique_ind]
    lons = lons[unique_ind]
    vels = vels[unique_ind]

    return rlat, rlon, lats, lons, vels


def calc_bearings(rlat, rlon, lats, lons):
    brng_deg = np.zeros(len(lats)) * np.nan
    pointB = wgs84.GeoPoint(
        latitude=rlat, longitude=rlon, z=depth, degrees=True)
    for ind, lat in enumerate(lats):
        lon = lons[ind]
        pointA = wgs84.GeoPoint(
            latitude=lat, longitude=lon, z=depth, degrees=True)
        p_AB_N = pointA.delta_to(pointB)  # note we want the bearing at point A
        brng_deg[ind] = p_AB_N.azimuth_deg - 180  # ... but away from the radar

    return brng_deg


def plot_quiver(rlat, rlon, lats, lons, vels, brng_deg, fname):
    brng_rad = np.deg2rad(brng_deg)
    plt.plot(lons, lats, '.k', markersize=5)
    plt.plot(rlon, rlat, '.r', markersize=20)
    plt.quiver(lons, lats, np.sin(brng_rad) * vels /
               100, np.cos(brng_rad) * vels / 100)
    plt.xlabel('Lon. (deg)')
    plt.ylabel('Lat. (deg)')
    plt.title('ExB drift components from %s' % fname)
    plt.grid()
    plt.show()


def dt_to_mjd(dt):
    mjd = jdutil.jd_to_mjd(jdutil.datetime_to_jd(dt) )
    return mjd


def mjd_to_dt(mjd):
    dt = jdutil.jd_to_datetime(jdutil.mjd_to_jd(mjd))
    return dt


if __name__ == '__main__':
    assert len(sys.argv) > 1, 'Provide a superdarn netCDF filename'
    fname = sys.argv[-1]

    main(fname)
