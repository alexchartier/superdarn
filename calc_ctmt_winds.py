"""
Calculate winds from the CTMT - Climatological Tidal Model of the Thermosphere
Aim to do SuperDARN winds analysis against it

"""
from line_profiler import LineProfiler

import nc_utils   # available from github.com/alexchartier/nc_utils
import numpy as np
from scipy.interpolate import CubicSpline
import matplotlib.pyplot as plt

from cartopy import config
import cartopy.crs as ccrs



def main(
    # diurnal and semidiurnal tidal filenames
    in_fn_sd = '~/data/ctmt/ctmt_semidiurnal_2002_2008.nc', 
    in_fn_d = '~/data/ctmt/ctmt_diurnal_2002_2008.nc', 

    # Location
    lats = np.arange(-90, 95, 5),
    lons = np.arange(0, 375, 15),
    alt = 100, 
    hour = 15, 
    month = 9, 
):
    model_coeffs = load_wind_coeffs(in_fn_d, in_fn_sd)

    calc_full_wind(lats, lons, alt, model_coeffs)

    # Load the files
    comps = table_of_components()

    # generate the Oberheide figure
    lsts = [0, 6, 12, 18]
    wind_dirs = {'u': 'Zonal', 'v': 'Meridional'}
    for dirn, wind_str in wind_dirs.items():
        wind = []
        for lst in lsts:
            wind.append(calc_wind_component(lats, lons, alt, month, model_coeffs, comps, lst=lst, dirn=dirn))

        fig, ax = plt.subplots(1, 4, subplot_kw={'projection': ccrs.PlateCarree()})
        fig.set_figheight(4)
        fig.set_figwidth(16)
        plt.set_cmap('jet')
        for ind, lst in enumerate(lsts):
            im = ax[ind].contourf(lons, lats, wind[ind], np.linspace(-57, 57, 11))
            ax[ind].coastlines()

        fig.subplots_adjust(right=0.8)
        cbar_ax = fig.add_axes([0.15, 0.2, 0.6, 0.05])
        cbar = fig.colorbar(im, cax=cbar_ax, orientation='horizontal')
        cbar.set_label('%s wind (m/s)' % wind_str)

        plt.show()


    wind = summed_wind_components_at_ut(lats, lons, alt, hour, month, model_coeffs, comps)
    fig, ax = plt.subplots(2, 1)
    ct = 0
    axc = []
    cbar = []
    for dirn, wind_str in wind_dirs.items():
        axc.append(ax[ct].contourf(lons, lats, wind[dirn]))
        cbar.append(fig.colorbar(axc[ct]))
        cbar[ct].set_label('\n%s wind (m/s)' % wind_str, rotation=90)
        ct += 1
    plt.show()


def load_wind_coeffs(in_fn_d, in_fn_sd):
    """ load CTMT coefficients """
    return {'d':nc_utils.ncread_vars(in_fn_d), 's':nc_utils.ncread_vars(in_fn_sd)}


def profile_calc_full_wind(month, lats, lons, alt, model_coeffs):
    """ wrapper just to support line profiling """
    lp = LineProfiler()
    lp.add_function(calc_wind)
    lp_wrapper = lp(calc_full_wind)
    model = lp_wrapper(month, lats, lons, alt, model_coeffs)
    lp.print_stats(output_unit=1)
    return model


def calc_full_wind(month, lats, lons, alt, model_coeffs):
    """ returns a u+v lst/lat/lon distribution of model winds at specified alt and month """ 
    lsts = np.arange(0, 25) 

    comps = table_of_components()
    dirns = 'u', 'v'

    wind_array = np.zeros((len(dirns), len(lsts), len(lats), len(lons)))
    for il, lst in enumerate(lsts):
        for idn, dirn in enumerate(dirns):
            wind_component = calc_wind_component(lats, lons, alt, month, model_coeffs, comps, lst=lst, dirn=dirn)
            wind_array[idn, il, :, :] = wind_component

    wind = {
        'wind': wind_array, 
        'lsts': lsts, 
        'dirns': dirns, 
        'lats': lats, 
        'lons': lons, 
        'alt': alt,
    }

    return wind


def calc_wind_component(lats, lons, alt, month, model_coeffs, comps, lst=18, dirn='u'):
    """
    compare against https://agupubs.onlinelibrary.wiley.com/doi/epdf/10.1029/2011JA016784

    lats: list of latitudes (deg)
    lons: list of longitudes (deg)
    alt: reference altitude (km)
    month: 1-12 
    model_coeffs: Jens' netCDFs loaded into a dict
    comps: dict of wave components (diurnal and semidiurnal - see table_of_components())
    lst: local solar time
    dirn: 'u' or 'v' (zonal/meridional)
    """

    # Calculate the wind
    wind = np.zeros((len(lats), len(lons)))
    hours = lst - lons / 360 * 24
    for ds, comp_list in comps.items():
        for comp in comp_list:
            wind_comp, phase, amp = calc_wind(model_coeffs[ds], lats, lons, alt, hours, month, comp, dirn, ds)
            wind += np.squeeze(wind_comp)

    return wind


def calc_wind(model_coeffs, lat, lon, alt, hour, month, component, direction, diurnal_semidiurnal='d'):
    """ 
    model_coeffs: loaded diurnal or semidiurnal file
    lat: scalar or vector latitude (must be subset of model_coeffs['lat'])
    lon: scalar or vector longitudes
    alt: scalar in km
    hour: scalar UT in decimal hours
    month: scalar
    component: 'e', 'w', 's' for east, west or stationary propagation + 0 - 4 for wavenumber
    direction: 'u' or 'v' (zonal or meridional, aka east or north)
    diurnal_semidiurnal: either 'd' or 's'

    """
   
    [lon2, _] = np.meshgrid(lon, lat) 
    # check all requested lat within model_coeffs['lat']
    # assert np.all(np.in1d(lat, model_coeffs['lat'])), "requested lat must be subset of model_coeffs['lat']"

    # Get the dimensional indexes 
    mi = model_coeffs['month'] == month
    ai = model_coeffs['lev'] == alt
    li = np.isin(lat, model_coeffs['lat']).ravel()

    #  amplitude (m/s) (east/west/north/up, depending on component)
    amp = model_coeffs['amp_%s_%s' % (component, direction)][mi, ai, li].ravel()

    # phase (UT of MAX at 0 deg lon)
    phase = model_coeffs['phase_%s_%s' % (component, direction)][mi, ai, li].ravel()
   
    # propagation direction multiplier used to determine phase at specified longitude
    if component[0] == 'e': # eastward
        dirn_multiplier = 1  
    elif component[0] == 'w': # westward
        dirn_multiplier = -1 
    elif component[0] == 's': # stationary
        dirn_multiplier = 0 
    else:
        raise Exception("Only 'e'/'w'/'s' components supported")

    # diurnal/semidiurnal multiplier 
    if diurnal_semidiurnal == 'd':
        ds_multiplier = 1
    elif diurnal_semidiurnal == 's':
        ds_multiplier = 2
    else:
        raise Exception("Only 'd'/'s' diurnal/semidiurnal values supported")

    # wavenumber 
    s = int(component[1])
    assert np.abs(s) < 5, 'wavenumbers <= 4 supported'

    # Wind values at the requested locations
    [_, amp2] = np.meshgrid(lon, amp)
    [_, phase2] = np.meshgrid(lon, phase)
    wind = amp2 * np.cos(ds_multiplier * np.pi / 12. * hour - dirn_multiplier * s * lon2 * np.pi / 180. - phase2 * ds_multiplier * np.pi / 12)

    return wind, phase2, amp2


def summed_wind_components_at_ut(lats, lons, alt, hour, month, model_coeffs, comps):
    # Calculate the wind
    zeros = np.zeros((len(lats), len(lons)))
    wind = {'u': zeros.copy(), 'v': zeros.copy()}  
    for ds, comp_list in comps.items():
        for comp in comp_list:
            for dirn in wind.keys():
                wind_comp, phase, amp = calc_wind(model_coeffs[ds], lats, lons, alt, hour, month, comp, dirn, ds)
                wind[dirn] += wind_comp

    return wind


def table_of_components():
    diurnal = ['w2', 'w1', 's0', 'e1', 'e2', 'e3',] 
    semidiurnal = ['w4', 'w3',] + diurnal
    
    return {'d':diurnal, 's':semidiurnal}


if __name__ == '__main__':
    main()

