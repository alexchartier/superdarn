"""
Calculate winds from the CTMT - Climatological Tidal Model of the Thermosphere
Aim to do SuperDARN winds analysis against it

"""
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
    calc_full_wind(lats, lons, alt, in_fn_d, in_fn_sd)


    # Load the files
    model = {'d':nc_utils.ncread_vars(in_fn_d), 's':nc_utils.ncread_vars(in_fn_sd)}
    comps = table_of_components()

    # generate the Oberheide figure
    lsts = [0, 6, 12, 18]
    wind_dirs = {'u': 'Zonal', 'v': 'Meridional'}
    for dirn, wind_str in wind_dirs.items():
        wind = []
        for lst in lsts:
            wind.append(calc_wind_component(lats, lons, alt, month, model, comps, lst=lst, dirn=dirn))

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


    wind = summed_wind_components_at_ut(lats, lons, alt, hour, month, model, comps)
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


def calc_full_wind(lats, lons, alt, in_fn_d, in_fn_sd):

    months = np.arange(1, 13)
    lsts = np.arange(0, 25) 

    model = {'d':nc_utils.ncread_vars(in_fn_d), 's':nc_utils.ncread_vars(in_fn_sd)}
    comps = table_of_components()
    dirns = 'u', 'v'

    wind_array = np.zeros((len(months), len(lsts), len(dirns), len(lats), len(lons)))
    for im, month in enumerate(months):
        for il, lst in enumerate(lsts):
            for idn, dirn in enumerate(dirns):
                wind_component = calc_wind_component(lats, lons, alt, month, model, comps, lst=lst, dirn=dirn)
                wind_array[im, il, idn, :, :] = wind_component

    wind = {
        'wind': wind_array, 
        'months': months, 
        'lsts': lsts, 
        'dirns': dirns, 
        'lats': lats, 
        'lons': lons, 
        'alt': alt,
    }

    return wind


def calc_wind_component(lats, lons, alt, month, model, comps, lst=18, dirn='u'):
    """
    compare against https://agupubs.onlinelibrary.wiley.com/doi/epdf/10.1029/2011JA016784

    lats: list of latitudes (deg)
    lons: list of longitudes (deg)
    alt: reference altitude (km)
    month: 1-12 
    model: Jens' netCDFs loaded into a dict
    comps: dict of wave components (diurnal and semidiurnal - see table_of_components())
    lst: local solar time
    dirn: 'u' or 'v' (zonal/meridional)
    """

    # Calculate the wind
    wind = np.zeros((len(lats), len(lons)))
    hours = lst - lons / 360 * 24
    for lonind, lon in enumerate(lons):
        hour = hours[lonind]
        for ds, comp_list in comps.items():
            for comp in comp_list:
                wind_comp, phase, amp = calc_wind(model[ds], lats, lon, alt, hour, month, comp, dirn, ds)
                wind[:, lonind] = wind[:, lonind] + np.squeeze(wind_comp)

    return wind


def summed_wind_components_at_ut(lats, lons, alt, hour, month, model, comps):
    # Calculate the wind
    zeros = np.zeros((len(lats), len(lons)))
    wind = {'u': zeros.copy(), 'v': zeros.copy()}  
    for ds, comp_list in comps.items():
        for comp in comp_list:
            for dirn in wind.keys():
                wind_comp, phase, amp = calc_wind(model[ds], lats, lons, alt, hour, month, comp, dirn, ds)
                wind[dirn] += wind_comp

    return wind


def calc_wind(model, lat, lon, alt, t, month, component, direction, diurnal_semidiurnal='d'):
    """ 
    model: loaded diurnal or semidiurnal file
    lat: scalar or vector latitude (must be subset of model['lat'])
    lon: scalar or vector longitudes
    alt: scalar in km
    t: scalar UT in decimal hours
    month: scalar
    component: 'e', 'w', 's' for east, west or stationary propagation + 0 - 4 for wavenumber
    direction: 'u' or 'v' (zonal or meridional, aka east or north)
    diurnal_semidiurnal: either 'd' or 's'

    TODO: be careful about the meaning of the output (could be eastward, westward, northward or upward)
    """

    # Expand the query points into 2D arrays if necessary
    lon, lat = np.meshgrid(lon, lat)
    
    # Get the dimensions  
    mi = model['month'] == month
    ai = model['lev'] == alt

    # check all requested lat within model['lat']
    assert np.all(np.in1d(lat, model['lat'])), "requested lat must be subset of model['lat']"

    #  amplitude (m/s) (east/west/north/up, depending on component)
    amp = np.interp(lat, model['lat'], model['amp_%s_%s' % (component, direction)][mi, ai, :].flatten())
    #amp = CubicSpline(model['lat'], model['amp_%s_%s' % (component, direction)][mi, ai, :].flatten())(lat)

    # phase (UT of MAX at 0 deg lon)
    phase = np.interp(lat, model['lat'], model['phase_%s_%s' % (component, direction)][mi, ai, :].flatten())
    #phase = CubicSpline(model['lat'], model['phase_%s_%s' % (component, direction)][mi, ai, :].flatten())(lat)
   
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

    # # Phase (UT of max at the specified lon).
    # phase_at_lon = phase + dirn_multiplier * s * lon / 360 * 24    

    # Wind values at the requested locations
    # wind = amp * np.cos((phase_at_lon - hour * ds_multiplier)  / 24 * np.pi * 2)  
    wind = amp * np.cos(ds_multiplier * np.pi / 12. * t \
                      - dirn_multiplier * s * lon * np.pi / 180. \
                      - phase * ds_multiplier * np.pi / 12)

    return wind, phase, amp


def table_of_components():
    diurnal = ['w2', 'w1', 's0', 'e1', 'e2', 'e3',] 
    semidiurnal = ['w4', 'w3',] + diurnal
    
    return {'d':diurnal, 's':semidiurnal}


if __name__ == '__main__':
    main()

