"""
Calculate winds from the CTMT - Climatological Tidal Model of the Thermosphere
Aim to do SuperDARN winds analysis against it

"""
from line_profiler import LineProfiler

import nc_utils   # available from github.com/alexchartier/nc_utils
import numpy as np
from scipy.interpolate import CubicSpline
import matplotlib.pyplot as plt
import time
from cartopy import config
import cartopy.crs as ccrs
from pymsis import msis
import xarray as xr
import scipy as sp

def main(
    # diurnal and semidiurnal tidal filenames
    in_fn_sd='~/data/ctmt/ctmt_semidiurnal_2002_2008.nc',
    in_fn_d='~/data/ctmt/ctmt_diurnal_2002_2008.nc',

    # Location
    lats=np.arange(-90, 95, 5),
    lons=np.arange(0, 375, 15),
    alt=100,
    hour=15,
    month=9,
):
    model_coeffs = load_wind_coeffs(in_fn_d, in_fn_sd)
    calc_full_wind(month, lats, lons, alt, model_coeffs)

    # Load the files
    comps = table_of_components()

    # generate the Oberheide figure
    lsts = [0, 6, 12, 18]
    wind_dirs = {'u': 'Zonal', 'v': 'Meridional'}
    for dirn, wind_str in wind_dirs.items():
        wind = []
        for lst in lsts:
            wind.append(calc_wind_component(
                lats, lons, alt, month, model_coeffs, comps, lst=lst, dirn=dirn,
            ))

        fig, ax = plt.subplots(
            1, 4, subplot_kw={'projection': ccrs.PlateCarree()})
        fig.set_figheight(4)
        fig.set_figwidth(16)
        plt.set_cmap('jet')
        for ind, lst in enumerate(lsts):
            im = ax[ind].contourf(lons, lats, wind[ind],
                                  np.linspace(-57, 57, 11))
            ax[ind].coastlines()

        fig.subplots_adjust(right=0.8)
        cbar_ax = fig.add_axes([0.15, 0.2, 0.6, 0.05])
        cbar = fig.colorbar(im, cax=cbar_ax, orientation='horizontal')
        cbar.set_label('%s wind (m/s)' % wind_str)

        plt.show()

    wind = summed_wind_components_at_ut(
        lats, lons, alt, hour, month, model_coeffs, comps)
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
    return {'d': nc_utils.ncread_vars(in_fn_d), 's': nc_utils.ncread_vars(in_fn_sd)}


def profile_calc_full_wind(month, lats, lons, alt, model_coeffs):
    """ wrapper just to support line profiling """
    lp = LineProfiler()
    lp.add_function(calc_wind)
    lp_wrapper = lp(calc_full_wind)
    model = lp_wrapper(month, lats, lons, alt, model_coeffs)
    lp.print_stats(output_unit=1)
    return model


def calc_full_wind_at_pressure_level(time, lats, lons, pressure, model_coeffs, plot=False):
    """ returns a u+v lst/lat/lon distribution of model winds at specified alt and month """
    month = time.month
    hours = np.arange(0, 25)

    comps = table_of_components()
    dirns = 'u', 'v'

    # Load the winds in LST 
    wind_array_lst = np.zeros((len(dirns), len(hours), len(lats), len(lons)))
    for il, lst in enumerate(hours):
        for idn, dirn in enumerate(dirns):
            for lati, lat in enumerate(lats):
                for loni, lon in enumerate(lons):
                    alt = calc_alt_at_pressure(time, lat, lon, pressure)
                    print(f'{lat} °N, {lon} °E, {alt:.1f} km')
                    
                    wind_component = calc_wind_component(
                        lat, lon, alt, month, model_coeffs, comps, lst=lst, dirn=dirn)
                    wind_array_lst[idn, il, lati, loni] = wind_component
   
    # Convert to UT 
    wind_array_ut = np.zeros_like(wind_array_lst)

    for ilst, lst in enumerate(hours):
        UTs = lst - lons * 24 / 360 
        UTs[UTs < 0] += 24
        for iut, ut in enumerate(hours):
            lonidx = np.where(np.in1d(UTs, ut))[0]
            wind_array_ut[:, iut, :, lonidx] = wind_array_lst[:, ilst, :, lonidx]
    wind_array_ut[:, 24, :, :] = wind_array_ut[:, 0, :, :]



def calc_alt_at_pressure(time, lat, lon, pressure, altitudes=np.arange(70, 120)):
    msis_ds = load_msis(time, lat, lon, altitudes)
    alt = sp.interpolate.interp1d(msis_ds['pressure'], altitudes)(pressure)

    return alt



def load_msis(time, lat, lon, altitudes):    
    """ load the MSIS model for a location """
    loschmidt_per_m3 = 2.686780111e25
    zero_degrees_c_in_k = 273.15

    msis_data = msis.run(time, lon, lat, altitudes, geomagnetic_activity=-1)

    mass_density = msis_data[:, 0, 0, :, 0]
    n2 = msis_data[:, 0, 0, :, 1]
    o2 = msis_data[:, 0, 0, :, 2]
    o = msis_data[:, 0, 0, :, 3]
    he = msis_data[:, 0, 0, :, 4]
    h = msis_data[:, 0, 0, :, 5]
    ar = msis_data[:, 0, 0, :, 6]
    n = msis_data[:, 0, 0, :, 7]
    anomalous_o = msis_data[:, 0, 0, :, 8]
    no = msis_data[:, 0, 0, :, 9]
    temperature = msis_data[:, 0, 0, :, 10]    
 
    msis_ds = {
        "mass_density": mass_density.ravel(),
        "n2": n2.ravel(),
        "o2": o2.ravel(),
        "o": o.ravel(),
        "he": he.ravel(),
        "h": h.ravel(),
        "ar": ar.ravel(),
        "n": n.ravel(),
        "anomalous_o": anomalous_o.ravel(),
        "no": no.ravel(),
        "temperature": temperature.ravel(),
        "altitude": altitudes,
    }

    for k, v in msis_ds.items():
        msis_ds[k][np.isnan(v)] = 0
    total_density = msis_ds['n2'] + msis_ds['o2']+ msis_ds['o'] + msis_ds['he'] + msis_ds['h'] + \
        msis_ds['ar'] + msis_ds['n'] + msis_ds['anomalous_o'] + msis_ds['no']
    pressure_ratio = (total_density * msis_ds['temperature'] / (loschmidt_per_m3 * zero_degrees_c_in_k))
    pressure = pressure_ratio * 1013.25 # This converts the ratio to pascals (101325 is pascals at sea level)
    msis_ds['pressure'] = pressure

    return msis_ds



def calc_full_wind(month, lats, lons, alt, model_coeffs, plot=False):
    """ returns a u+v lst/lat/lon distribution of model winds at specified alt and month """
    hours = np.arange(0, 25)

    comps = table_of_components()
    dirns = 'u', 'v'

    # Load the winds in LST 
    wind_array_lst = np.zeros((len(dirns), len(hours), len(lats), len(lons)))
    for il, lst in enumerate(hours):
        for idn, dirn in enumerate(dirns):
            wind_component = calc_wind_component(
                lats, lons, alt, month, model_coeffs, comps, lst=lst, dirn=dirn)
            wind_array_lst[idn, il, :, :] = wind_component
   
    # Convert to UT 
    wind_array_ut = np.zeros_like(wind_array_lst)

    for ilst, lst in enumerate(hours):
        UTs = lst - lons * 24 / 360 
        UTs[UTs < 0] += 24
        for iut, ut in enumerate(hours):
            lonidx = np.where(np.in1d(UTs, ut))[0]
            wind_array_ut[:, iut, :, lonidx] = wind_array_lst[:, ilst, :, lonidx]
    wind_array_ut[:, 24, :, :] = wind_array_ut[:, 0, :, :]

    if plot: 
        for iut, ut in enumerate(hours):
            fig, ax  = plt.subplots(1, 2)
            ax[0].contourf(lons, lats, wind_array_ut[0, iut, :, :])
            noonlon = 360 - ut * 360 / 24 
            ax[0].plot([noonlon, noonlon], [-90, 90], '-r')
            ax[1].contourf(lons, lats, wind_array_lst[0, iut, :, :])
            plt.show()
     
    wind = {
        'wind': wind_array_ut,
        'dirns': dirns,
        'UTs': hours,
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
    if type(lats) == int or type(lats) == np.int64:
        wind = 0
    else:
        wind = np.zeros((len(lats), len(lons)))
    hours = lst - lons / 360 * 24
    for ds, comp_list in comps.items():
        for comp in comp_list:
            wind_comp, phase, amp = calc_wind(
                model_coeffs[ds], lats, lons, alt, hours, month, comp, dirn, ds)
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
    li = np.isin(model_coeffs['lat'], lat).ravel()

    #  amplitude (m/s) (east/west/north/up, depending on component)
    amparr = np.squeeze(model_coeffs['amp_%s_%s' % (component, direction)][mi, :, li])
    amp = sp.interpolate.interp1d(model_coeffs['lev'], amparr)(alt)

    # phase (UT of MAX at 0 deg lon)
    phasearr = np.squeeze(model_coeffs['phase_%s_%s' % (component, direction)][mi, :, li])
    phase = sp.interpolate.interp1d(model_coeffs['lev'], phasearr)(alt)

    # propagation direction multiplier used to determine phase at specified longitude
    if component[0] == 'e':  # eastward
        dirn_multiplier = 1
    elif component[0] == 'w':  # westward
        dirn_multiplier = -1
    elif component[0] == 's':  # stationary
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
    wind = amp2 * np.cos(ds_multiplier * np.pi / 12. * hour - dirn_multiplier *
                         s * lon2 * np.pi / 180. - phase2 * ds_multiplier * np.pi / 12)

    return wind, phase2, amp2


def summed_wind_components_at_ut(lats, lons, alt, hour, month, model_coeffs, comps):
    # Calculate the wind
    zeros = np.zeros((len(lats), len(lons)))
    wind = {'u': zeros.copy(), 'v': zeros.copy()}
    for ds, comp_list in comps.items():
        for comp in comp_list:
            for dirn in wind.keys():
                wind_comp, phase, amp = calc_wind(
                    model_coeffs[ds], lats, lons, alt, hour, month, comp, dirn, ds)
                wind[dirn] += wind_comp

    return wind


def table_of_components():
    diurnal = ['w2', 'w1', 's0', 'e1', 'e2', 'e3',]
    semidiurnal = ['w4', 'w3',] + diurnal

    return {'d': diurnal, 's': semidiurnal}


if __name__ == '__main__':
    main()






