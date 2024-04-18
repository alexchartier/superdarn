#!/usr/bin/env python
# coding: utf-8

# # An example to read ICON's Hough Mode Extension (HME) data product (DP4.1)

# ICON data are available on the Berkeley FTP: ftp://icon-science.ssl.berkeley.edu/pub
#
# HME files are ICON data product 4.1. For example, the data from 2020 can be found in the following directory:
#  - Science/LEVEL.4/HME/2020/Data/
#
# As of May 3, 2022, only Version 1 (v01) is available. Version 2 will be coming soon.
# Author: Brian Harding, Berkeley SSL. Edited by ATC (APL)
# See https://nbviewer.org/url/www.ssl.berkeley.edu/~bharding/MIGHTI/HME_Example.ipynb
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
import glob
import numpy as np
from scipy import interpolate
import seaborn as sns
import pandas as pd
import xarray as xr

mpl.rcParams['figure.dpi'] = 120
#  plt.style.use('seaborn')


def main():
    # Specify the HME filename
    fn = '/disks/data/icon/Repository/Archive/LEVEL.4/HME/2020/Data/ICON_L4-1_HME_2020-12-25_v01r000.NC'

    # # Evaluate SW2 only

    # Set up time, lat, lon, alt grids. Here let's do a cut along a constant latitude
    t = pd.to_datetime('2020-12-25 12:00')
    lat = 30.
    Nlon, Nalt = 61, 50
    lon = np.linspace(0, 360, Nlon)
    alt = np.linspace(90, 300, Nalt) * 1e3  # altitude in meters

    # Turn into matrices
    LON, ALT = np.meshgrid(lon, alt, indexing='ij')
    long = LON.ravel()  # turn into a 1D array
    altg = ALT.ravel()  # turn into a 1D array
    latg = lat * np.ones_like(long)  # turn into a 1D array

    # Evaluate SW2
    u, v = eval_hme(fn, 2, 2, latg, long, altg, t.hour)
    # Turn back into matrix
    U = u.reshape((Nlon, Nalt))
    V = v.reshape((Nlon, Nalt))

    # Plot semidiurnal tide
    plt.figure()
    plt.pcolormesh(LON, ALT / 1e3, U, vmin=-60,
                   vmax=60, cmap='RdBu', shading='auto')
    plt.ylabel('Altitude [km]')
    plt.xlabel('Longitude [deg]')
    plt.title('Semidiurnal migrating tide SW2\nLAT = %.0f deg\n%s' %
              (lat, t.strftime('%Y-%m-%d %H:%M')))
    plt.tight_layout()

    # # Evaluate all HME tides together
    u, v = eval_hme_all(fn, latg, long, altg, t.hour)
    # Turn back into matrix
    U = u.reshape((Nlon, Nalt))
    V = v.reshape((Nlon, Nalt))

    # plot full zonal wind
    plt.figure()
    plt.pcolormesh(LON, ALT / 1e3, U, vmin=-60,
                   vmax=60, cmap='RdBu', shading='auto')
    plt.ylabel('Altitude [km]')
    plt.xlabel('Longitude [deg]')
    plt.title('All tides\nLAT = %.0f deg\n%s' %
              (lat, t.strftime('%Y-%m-%d %H:%M')))
    plt.tight_layout()


def eval_hme(fn_hme, ntide, stide, glats, glons, alts, thr):
    '''
    Evaluate a particular tide (HME) specified by frequency and zonal wavenumber (n,s) using the 
    given ICON L4.1 data file, at given locations and times. 

    Amplitudes and phases are re-gridded to the specified points, and evaluated at the lons and hour specified, 
    using the tidal equation. All latitudinal modes that are available are combined.

    If the tide doesn't exist in the file, zeros will be returned

    INPUTS:
    * fn_hme - full path to an ICON L4.1 HME data product
    * ntide  - tide's frequency (day^-1)
    * stide  - tide's zonal wavenumber (-4, -2, -1, )
    * glats  - [deg] 1D array of geographic latitudes to evaluate the wind at
    * glons  - [deg] 1D array of geographic longitudes to evaluate the wind at
    * alts   - [m] 1D array of geographic altitudes to evaluate the wind at
    * thr    - [hr] (scalar or 1D array) The UT hour to evaluate the tide at (fractional is ok)

    RETURNS:
    * u      - [m/s] 1D array of zonal winds
    * v      - [m/s] 1D array of meridional winds
    '''

    fn_hme = os.path.abspath(os.path.expanduser(fn_hme))
    assert len(glats) == len(
        glons), "Input arrays glats, glons, alts must be the same length"
    assert len(glats) == len(
        alts), "Input arrays glats, glons, alts must be the same length"
    assert os.path.exists(fn_hme), 'File not found: %s' % fn_hme

    if np.nanmean(alts) < 10e3:
        print('WARNING: Are you sure altitude is specified in meters?')

    ds = xr.open_dataset(fn_hme)

    # Find the variable names of interest
    nstr = {1: 'D',
            2: 'SD'}
    sstr = {-4: 'E4',
            -3: 'E3',
            -2: 'E2',
            -1: 'E1',
            0: 'S0',
            1: 'W1',
            2: 'W2',
            3: 'W3', }

    var_amp_u = '%sAMP_%s_U' % (nstr[ntide], sstr[stide])
    var_amp_v = '%sAMP_%s_V' % (nstr[ntide], sstr[stide])
    var_phase_u = '%sPHASE_%s_U' % (nstr[ntide], sstr[stide])
    var_phase_v = '%sPHASE_%s_V' % (nstr[ntide], sstr[stide])

    if var_amp_u in ds.variables:

        # Create interpolation objects using alt [m] and geog lat [deg].
        # Interpolating amplitude and phase is problematic. Interpolate real and imaginary parts instead.
        phu = -2 * np.pi * ntide / 24. * ds[var_phase_u]
        phv = -2 * np.pi * ntide / 24. * ds[var_phase_v]
        u_re_0 = ds[var_amp_u] * np.cos(phu)
        u_im_0 = ds[var_amp_u] * np.sin(phu)
        v_re_0 = ds[var_amp_v] * np.cos(phv)
        v_im_0 = ds[var_amp_v] * np.sin(phv)

        u_re_i = interpolate.RegularGridInterpolator(
            (1e3 * ds.Altitude.values, ds.Latitude.values), u_re_0.values, method='linear', bounds_error=False, fill_value=np.nan)
        u_im_i = interpolate.RegularGridInterpolator(
            (1e3 * ds.Altitude.values, ds.Latitude.values), u_im_0.values, method='linear', bounds_error=False, fill_value=np.nan)
        v_re_i = interpolate.RegularGridInterpolator(
            (1e3 * ds.Altitude.values, ds.Latitude.values), v_re_0.values, method='linear', bounds_error=False, fill_value=np.nan)
        v_im_i = interpolate.RegularGridInterpolator(
            (1e3 * ds.Altitude.values, ds.Latitude.values), v_im_0.values, method='linear', bounds_error=False, fill_value=np.nan)

        pts = np.vstack((alts, glats)).T
        u_re = u_re_i(pts)
        u_im = u_im_i(pts)
        v_re = v_re_i(pts)
        v_im = v_im_i(pts)

        u_amp = np.sqrt(u_re**2 + u_im**2)
        v_amp = np.sqrt(v_re**2 + v_im**2)
        u_ph_rad = np.arctan2(u_im, u_re)  # phase in radians
        v_ph_rad = np.arctan2(v_im, v_re)
        # phase in hours (analogous to what's in the original HME file)
        u_ph = -24. / (2 * np.pi * ntide) * u_ph_rad
        # phase in hours (analogous to what's in the original HME file)
        v_ph = -24. / (2 * np.pi * ntide) * v_ph_rad

        u = u_amp * np.cos(2 * np.pi * ntide / 24. *
                           (thr - u_ph) + stide * glons * np.pi / 180.)
        v = v_amp * np.cos(2 * np.pi * ntide / 24. *
                           (thr - v_ph) + stide * glons * np.pi / 180.)

    else:
        u = np.zeros(len(glats))
        v = np.zeros(len(glats))

    del ds

    return u, v


def eval_hme_all(fn_hme, glats, glons, alts, thr):
    '''
    Evaluate all HMEs that are available in a given ICON L4.1 data file, at given locations and times. 

    Amplitudes and phases are re-gridded to the specified points, and evaluated at the lons and hour specified, 
    using the tidal equation. All latitudinal modes that are available are combined.

    INPUTS:
    * fn_hme - full path to an ICON L4.1 HME data product
    * glats  - [deg] 1D array of geographic latitudes to evaluate the wind at
    * glons  - [deg] 1D array of geographic longitudes to evaluate the wind at
    * alts   - [m] 1D array of geographic altitudes to evaluate the wind at
    * thr    - [hr] (scalar) The UT hour to evaluate the tide at (fractional is ok)

    RETURNS:
    * u      - [m/s] 1D array of zonal winds
    * v      - [m/s] 1D array of meridional winds
    '''

    u = np.zeros(len(glats))
    v = np.zeros(len(glats))

    for n in range(1, 3):  # diurnal and semi-diurnal
        for s in range(-4, 4):  # E4 to W3 inclusive
            uns, vns = eval_hme(fn_hme, n, s, glats, glons, alts, thr)
            u += uns
            v += vns
    return u, v


def eval_icon_hme(fn_hme, glats_1d, glons_1d, alt_km, thrs):
    """ wrapper for eval_hme_all """
   
    alt = alt_km * 1000 
    if (len(glats_1d) != len(glons_1d)) or (len(glats) != len(alt)):
        glats_3d, glons_3d, alts_3d = np.meshgrid(
            glats_1d, glons_1d, alt, indexing='ij')
    glats = glats_3d.flatten()
    glons = glons_3d.flatten()
    alts = alts_3d.flatten() 

    u_3d = np.ones((len(thrs), glats_3d.shape[0], glats_3d.shape[1])) * np.nan
    v_3d = np.ones_like(u_3d) * np.nan
    for ind, thr in enumerate(thrs):
        u, v = eval_hme_all(fn_hme, glats, glons, alts, thr)
        u_3d[ind, :, :] = np.reshape(u, glats_3d.shape[:2])
        v_3d[ind, :, :] = np.reshape(v, glats_3d.shape[:2])

    plt.contourf(glons_1d, glats_1d, u_3d[0, :, :])
    plt.colorbar()
    plt.title('%i km U @ 0 UT from %s' % (alt_km, os.path.basename(fn_hme)))
    plt.xlabel('GLON')
    plt.ylabel('GLAT')
    plt.show()
    


if __name__ == '__main__':


    main()
