""" 
Compare SD against CTMT winds
"""

import nc_utils   # available from github.com/alexchartier/nc_utils
import numpy as np
from scipy.interpolate import RegularGridInterpolator
import matplotlib.pyplot as plt 
import datetime as dt
from cartopy import config
import cartopy.crs as ccrs
import pickle
import calc_ctmt_winds
import sd_utils

def main(

    # Model params
    time = dt.datetime(2020, 1, 1),
    alt = 90,
    lats = np.arange(-90, 95, 5),
    lons = np.arange(0, 375, 15),

    # SuperDARN meteor wind data
    in_fn_wind = '~/data/superdarn/meteorwindnc/%Y/%m/%Y%b%d.{}.nc',

    # SD hdw.dat dir
    hdw_dat_dir = '~/rst/tables/superdarn/hdw/',

    # CTMT diurnal/semidiurnal
    in_fn_semidiurnal = '~/data/ctmt/ctmt_semidiurnal_2002_2008.nc',
    in_fn_diurnal = '~/data/ctmt/ctmt_diurnal_2002_2008.nc',

):

    """ setup model """
    # load the model wind (in local solar time)
    pkl_fn = 'temp.pkl'
    try:
        model = nc_utils.unpickle(pkl_fn)
    except:
        model = calc_ctmt_winds.calc_full_wind(
            lats, lons, alt, in_fn_diurnal, in_fn_semidiurnal)
        nc_utils.pickle(model, pkl_fn)

    # Setup interpolators
    interp_fn_U = RegularGridInterpolator(
        (model['lsts'], model['lats'], model['lons']), 
        np.squeeze(model['wind'][model['months']==time.month, :, 0, :, :]),
    )
    interp_fn_V = RegularGridInterpolator(
        (model['lsts'], model['lats'], model['lons']), 
        np.squeeze(model['wind'][model['months']==time.month, :, 1, :, :]),
    )

    """ Get the model wind at the radar locs """
    radar_list = sd_utils.get_radar_params(hdw_dat_dir)
    for radarcode in radar_list:

        breakpoint()
        # Load the SuperDARN wind
        sd = nc_utils.load_nc(time.strftime(in_fn_wind.format(radarcode)))


        """ get the model and observed winds into a structure """
        wind = calc_boresight_wind(sd, interp_fn_U, interp_fn_V)



    # TODO monthly mean?



def calc_boresight_wind(sd, interp_fn_U, interp_fn_V):
    # Get SuperDARN params
    boresight = np.rad2deg(float(sd.boresight.split()[0]))
    lst = np.arange(0, 24) + sd.lon / 360. * 24.
    lst[lst < 0] += 24
    lst[lst >= 24] -= 24
    sd_lon = np.array([sd.lon,])
    sd_lon[sd.lon < 0] += 360.

    """ Interpolate """
    # Get the model U/V at the radar location, for the specified month
    U = interp_fn_U(np.squeeze(np.array([lst, np.ones(lst.shape) * sd.lat, np.ones(lst.shape) * sd_lon]).T))
    V = interp_fn_V(np.squeeze(np.array([lst, np.ones(lst.shape) * sd.lat, np.ones(lst.shape) * sd_lon]).T))
    model_boresight_wind = np.sin(boresight) * U + np.cos(boresight) * V

    """ setup output variables """
    out = {}
    out['model'] = model_boresight_wind
    out['sd'] = sd.variables['Vx'][:]
    out['lat'] = sd.lat
    out['lon'] = sd.lon
    out['hour'] = sd.variables['hour'][:]

    return out


if __name__ == '__main__':
    main()

















