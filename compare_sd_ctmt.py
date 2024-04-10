""" 
Compare SD against CTMT winds

 TODO:
    #1 Determine accuracy of all sites against CTMT in Jan. Use performance vs July CTMT as baseline
    #2 Add phase fitting. Make sure it doesn't make things worse
    #3 Confirm whether valsites show better or worse performance against CTMT
"""

from itertools import islice
from line_profiler import LineProfiler
import nc_utils   # available from github.com/alexchartier/nc_utils
import numpy as np
import copy
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import minimize, direct, Bounds
import matplotlib.pyplot as plt 
import datetime as dt
from cartopy import config
import cartopy.crs as ccrs
import calc_ctmt_winds
import sd_utils

hr = np.arange(0, 24)


def main(
    year = 2008,
    # Model params
    alt = 90,
    lats = np.arange(-90, 95, 5),
    lons = np.arange(0, 375, 15),

    # SuperDARN meteor wind data
    in_fn_fmt_wind = '~/data/superdarn/meteorwindnc/%Y/%m/%Y%b%d.{}.nc',

    # SD hdw.dat dir
    hdw_dat_dir = '~/rst/tables/superdarn/hdw/',

    # CTMT diurnal/semidiurnal
    in_fn_semidiurnal = '~/data/ctmt/ctmt_semidiurnal_2002_2008.nc',
    in_fn_diurnal = '~/data/ctmt/ctmt_diurnal_2002_2008.nc',
    valsites=['gbr', 'kod', 'hok'],
    #valsites=['inv', 'kap', 'hok', 'wal', 'pyk', 'rkn', 'kod', 'pgr', 'ksr', 'sas', 'han', 'sto'],
):

    radar_list = sd_utils.get_radar_params(hdw_dat_dir)
    model_coeffs = calc_ctmt_winds.load_wind_coeffs(in_fn_diurnal, in_fn_semidiurnal)

    month = 1
   
    # Load the SuperDARN wind data 
    sd_wind = load_sd_wind(year, month, in_fn_fmt_wind, radar_list)
    sd_wind = downselect_sites(sd_wind, hem='N')
    sd_wind_novalsites = downselect_sites(sd_wind, exclude=valsites)
    sd_wind_valsites = downselect_sites(sd_wind, include=valsites)

    # Fit the model 
    pkl_fn = 'fit.pkl'
    try: 
        fitted_model_coeffs = nc_utils.unpickle(pkl_fn)
    except:
        fitted_model_coeffs, X = fit_model(year, lats, lons, alt, month, model_coeffs, sd_wind_novalsites)
        nc_utils.pickle(fitted_model_coeffs, pkl_fn)

    # run error analysis
    model = calc_ctmt_winds.calc_full_wind(month, lats, lons, alt, model_coeffs)  # CTMT winds on a grid
    fitted_model = calc_ctmt_winds.calc_full_wind(month, lats, lons, alt, fitted_model_coeffs)  # fitted winds on a grid


    errs_full = error_analysis(year, lats, lons, alt, model, sd_wind)
    errs_full_fitted = error_analysis(year, lats, lons, alt, fitted_model, sd_wind)
    errs_valsites = error_analysis(year, lats, lons, alt, model, sd_wind_valsites)
    errs_valsites_fitted = error_analysis(year, lats, lons, alt, fitted_model, sd_wind_valsites)
    
    # plotting/reporting 
    disp_errs(errs_full, errs_full_fitted)
    plot_errors(errs_valsites, fitted=errs_valsites_fitted)
    #plot_errors(errs_full, fitted=errs_full_fitted)


def disp_errs(errs, errs_fitted):
    print("\n\n******** error scores (+ve = worse)")
    term = 'weighted_err_score'
    for station, vals in errs.items():
        print('%s: %1.2f %1.2f %1.2f' % \
        (station, vals[term], errs_fitted[station][term], errs_fitted[station][term] - vals[term]))


def error_analysis(year, lats, lons, alt, model, sd_wind, verbose=False):
    """ compare the data against the model. 
    """
    wind = get_ctmt_wind_at_sd_locs(model, sd_wind)
   
    if verbose:  
        print("\n\n******** error scores")
    errs = {}
    for station, vals in wind.items():
        errs[station] = {}
        errs[station]['obs'] = vals['obs_med']
        errs[station]['mod'] = vals['model']
        errs[station]['error'] = vals['obs_med'] - vals['model']
        errs[station]['weighted_err_score'] = np.nanmean(np.abs(errs[station]['error']) / vals['obs_MAD'])
        errs[station]['obs_MAD'] = vals['obs_MAD']
        if verbose:
            print('%s: %1.1f' % (station, errs[station]['weighted_err_score']))

    return errs


def plot_errors(errs, fitted=None, ylim=[-30, 30]):
    if len(errs) > 6:
        errs = take(6, errs.items())

    fig, ax = plt.subplots(len(errs), 1)
    ct = 0
    for station, vals in errs.items():
        ax[ct].errorbar(hr, vals['obs'], yerr=vals['obs_MAD'], label='Observed')
        ax[ct].plot(hr, vals['mod'], label='CTMT')
        if fitted:
            ax[ct].plot(hr, fitted[station]['mod'], label='Fitted')
        ax[ct].grid()
        ax[ct].set_xlabel('Hour (UT)')
        ax[ct].set_ylabel('Boresight Wind (m/s)')
        ax[ct].set_title(station)
        ax[ct].set_xlim([0, 24])
        ax[ct].set_ylim(ylim)

        ct +=1

    ax[0].legend()
    plt.show()



def fit_model(year, lats, lons, alt, month, model_coeffs, sd_wind):
    """ calculate a tidal fit that best matches the SuperDARN data 
    TODO: downselect to just NH (or SH) sites, update fit coefficients
    Use scaling factors to vary the coefficient amplitudes (6x diurnal, 8x semidiurnal
    How to vary phases??
    """ 
    
    time = dt.datetime(year, month, 1)

    """ Load SuperDARN wind """
    #plot_median_wind(wind, 'gbr')

    # Now create a cost function to minimize from there

    components = calc_ctmt_winds.table_of_components() 
    X0 = np.zeros(len(components['d'] + components['s'])) # coefficients for amplitude of each component in U and V

    def cost_function(X): 
        # Update the coefficients according to X
        fitted_model_coeffs = scale_model(model_coeffs, X)

        # Calculate the wind errors
        model = calc_ctmt_winds.calc_full_wind(month, lats, lons, alt, fitted_model_coeffs)  # model winds on a grid
        wind = get_ctmt_wind_at_sd_locs(model, sd_wind)
        weighted_errs = []
        for station, vals in wind.items():
            weighted_errs += (np.abs(vals['obs_med'] - vals['model']) / vals['obs_MAD']**2).tolist()

        weighted_errs = np.array(weighted_errs)
        cost = np.nansum(weighted_errs**2)
        print('Cost: %1.1f' % cost)

        return cost
  
    result = powell_search(cost_function, X0)
    print('**********')
    print(result.x)
    print('Final cost: %1.1f' % result.fun)

    # fit to the result
    fitted_model_coeffs = scale_model(model_coeffs, result.x)

    return fitted_model_coeffs, result.x


def scale_model(model_coeffs, X):
    """ Scale the model coefficients according to X (=zeros for no scaling) """

    # TODO: add phase adjustment (X=2x len comps, phase += X[ct * 2] * 12)

    components = calc_ctmt_winds.table_of_components() 
    dirns = 'u', 'v'

    # Copy so as not to modify the original
    fitted_model_coeffs = copy.deepcopy(model_coeffs)

    # Vary the model according to the fit coefficients
    ct = 0
    for ds in 'd', 's':  # diurnal/semidiurnal 
        for component in components[ds]:  # wave component
            for direction in dirns:  # u/v
                fitted_model_coeffs[ds]['amp_%s_%s' % (component, direction)] *= 1 + X[ct]
            ct += 1

    return fitted_model_coeffs


def bruteforce_search(cost_function, X0, searchslice=slice(-1, 1, 0.1)):
    # bruteforce array is too big
    ranges = []
    bounds = Bounds(-np.ones(len(X0)), np.ones(len(X0)))
    result = direct(cost_function, bounds) 


def neldermead_search(cost_function, X0):
    result = minimize(cost_function, X0, method='nelder-mead') # , options={'eps':0.25})
    return result


def powell_search(cost_function, X0):
    result = minimize(cost_function, X0, method='powell') # , options={'eps':0.25})
    return result


def load_sd_wind(year, month, in_fn_fmt_wind, radar_list):
    """ 
    loads a month of SuperDARN wind data 
    See also: plot_median_wind()
    """
    wind = {}
    for radarcode in radar_list.keys():
        wind[radarcode] = {}
        zeroarr = np.zeros((31, 24)) * np.nan
        wind[radarcode]['obs_daily'] = zeroarr.copy()
        wind[radarcode]['obs_sdev_daily'] = zeroarr.copy()
        wind[radarcode]['hour'] = hr
        time = dt.datetime(year, month, 1)
        dayct = 0
        while time.month == month:
            
            # Load the SuperDARN wind
            try:
                sd = nc_utils.load_nc(time.strftime(in_fn_fmt_wind.format(radarcode)))
            except:
                time += dt.timedelta(days=1)
                continue

            hridx = np.isin(hr, sd.variables['hour'][:])
            wind[radarcode]['obs_daily'][dayct, hridx] = sd.variables['Vx'][:]
            wind[radarcode]['obs_sdev_daily'][dayct, hridx] = sd.variables['sdev_Vx'][:]
            wind[radarcode]['lat'] = sd.lat
            wind[radarcode]['lon'] = sd.lon
            wind[radarcode]['boresight'] = float(sd.boresight.split()[0])
            time += dt.timedelta(days=1)
            dayct += 1

        # Calculate the median and median abs deviation
        wind[radarcode]['obs_med'] = np.nanmedian(wind[radarcode]['obs_daily'], axis=0)
        wind[radarcode]['obs_MAD'] = np.nanmedian(np.abs(
            wind[radarcode]['obs_daily'] - np.nanmedian(wind[radarcode]['obs_daily'])), axis=0)

    # throw out the empties
    for radarcode in radar_list.keys():
        if np.isfinite(wind[radarcode]['obs_daily']).sum() == 0:
            wind.pop(radarcode)

    return wind

    
def get_ctmt_wind_at_sd_locs(model, wind):
    """ Calculate the model wind in the boresight direction at the radar locations 
    """
    # Setup interpolators
    interp_fn_U = RegularGridInterpolator(
        (model['lsts'], model['lats'], model['lons']), 
        np.squeeze(model['wind'][0, :, :, :]),
    )
    interp_fn_V = RegularGridInterpolator(
        (model['lsts'], model['lats'], model['lons']), 
        np.squeeze(model['wind'][1, :, :, :]),
    )

    """ Get the model wind at the radar locs """
    for radarcode, vals in wind.items():
        """ get the model and observed winds into a structure """
        model_boresight_wind = calc_boresight_wind(vals['lat'], vals['lon'], vals['boresight'], interp_fn_U, interp_fn_V)
        wind[radarcode]['model'] = model_boresight_wind

    return wind

def plot_median_wind(wind, code):
    plt.errorbar(hr, wind[code]['obs_med'], yerr=wind[code]['obs_MAD'])
    plt.plot(hr, wind[code]['obs_daily'].T, '.')
    plt.grid()
    plt.xlabel('Hour (UT)')
    plt.ylabel('Boresight Wind (m/s)')
    plt.title(code)
    plt.show()


def calc_boresight_wind(lat, lon, boresight, interp_fn_U, interp_fn_V):
    """ Get model boresight winds at the SuperDARN locations """
    boresight_rad = np.deg2rad(boresight)
    lst = hr + lon / 360. * 24.
    lst[lst < 0] += 24
    lst[lst >= 24] -= 24
    sd_lon = np.array([lon,])
    sd_lon[sd_lon < 0] += 360.

    """ Interpolate """
    # Get the model U/V at the radar location, for the specified month
    U = interp_fn_U(np.squeeze(np.array([lst, np.ones(lst.shape) * lat, np.ones(lst.shape) * sd_lon]).T))
    V = interp_fn_V(np.squeeze(np.array([lst, np.ones(lst.shape) * lat, np.ones(lst.shape) * sd_lon]).T))
    model_boresight_wind = np.sin(boresight_rad) * U + np.cos(boresight_rad) * V

    return model_boresight_wind


def downselect_sites(sd_wind, hem=None, exclude=[], include=[]):
    """ kick out hemisphere & exclude-list stations """ 
    sd_wind_short = {}

    for radarcode, vals in sd_wind.items():
        # kick out exclude sites
        if radarcode in exclude:
            continue

        # kick out non-include sites
        if include and radarcode not in include:
            continue

        # kick out wrong hemisphere
        if hem:
            if hem == 'N':
                if vals['lat'] < 0:
                    continue
            if hem == 'S':
                if vals['lat'] > 0:
                    continue

        sd_wind_short[radarcode] = vals

    return sd_wind_short



def take(n, iterable):
    """Return the first n items of the iterable as a list."""
    return dict(islice(iterable, n))


if __name__ == '__main__':
    main()

















