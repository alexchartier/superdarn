#!/usr/bin/python3
""" Quiver & scatter plot example for grid files
nc_utils from github.com/alexchartier/nc_utils
"""

import numpy as np
import matplotlib.pyplot as plt
import os
import nc_utils


def main(
    fn='~/Downloads/20130117.sto.v3.0.grid.nc',
):
    df = nc_utils.load_nc(fn)
    data = nc_utils.ncread_vars(fn)

    t0 = np.floor(data['mjd_start'][0])  # + 16/24
    t1 = np.floor(data['mjd_start'][0]) + 2 / 60 / 24  # + 16/24
    tidx = np.logical_and(data['mjd_start'] >= t0, data['mjd_start'] <= t1)
    breakpoint()

    for k, v in data.items():
        data[k] = v[tidx]

    rlat = df.lat
    rlon = df.lon
    lats = data['vector.glat']
    lons = data['vector.glon']
    vels = data['vector.vel.median'] * data['vector.vel.dirn']
    brng_deg = data['vector.g_kvect']

    plot_scatter(rlat, rlon, lats, lons, vels, fn)
    plot_quiver(rlat, rlon, lats, lons, vels, brng_deg, fn)


def plot_scatter(rlat, rlon, lats, lons, vels, fname):
    """ scatter plot matching the online plotting """
    plt.plot(rlon, rlat, '.r', markersize=20)
    plt.scatter(lons, lats, c=vels, s=100, cmap='jet_r')
    plt.clim([-200, 200])
    plt.colorbar()
    plt.xlabel('Lon. (deg)')
    plt.ylabel('Lat. (deg)')
    plt.title('ExB drift components from %s' % fname)
    plt.grid()
    plt.show()


def plot_quiver(rlat, rlon, lats, lons, vels, brng_deg, fname):
    """ quiver plot for comparison """
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


if __name__ == "__main__":
    main()
