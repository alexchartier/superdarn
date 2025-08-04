""" 
Compare SD against CTMT winds

 TODO:
    #1 Determine accuracy of all sites against CTMT in Jan. Use performance vs July CTMT as baseline
    #2 Add phase fitting. Make sure it doesn't make things worse
    #3 Confirm whether valsites show better or worse performance against CTMT
    #4 Check if fit gets better when adding SH data
"""
import sys
sys.path.append('..')
from icon_houghmode_viewer import eval_icon_hme
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
    # Model params
    pressure=0.002, # hPa
    lats=np.arange(-90, 95, 5),
    lons=np.arange(0, 375, 15),

    # SuperDARN meteor wind data
    sd_fn_fmt='~/data/superdarn/meteorwindnc/%Y/%m/%Y%b%d.{}.nc',

    # SD hdw.dat dir
    hdw_dat_dir='~/rst/tables/superdarn/hdw/',

    # CTMT diurnal/semidiurnal
    in_fn_semidiurnal='~/data/ctmt/ctmt_semidiurnal_2002_2008.nc',
    in_fn_diurnal='~/data/ctmt/ctmt_diurnal_2002_2008.nc',

    # ICON files
    icon_fn_fmt='~/data/icon/l4/hme/%Y/%j/ICON_L4-1_HME_%Y-%m-%d_v03r000.NC',

    # valsites=['inv', 'kap', 'hok', 'wal', 'pyk', 'rkn', 'kod', 'pgr', 'ksr', 'sas', 'han', 'sto'],
):
    radar_list = np.array([*sd_utils.get_radar_params(hdw_dat_dir)])
    radar_list.sort()
    ctmt_coeffs = calc_ctmt_winds.load_wind_coeffs(in_fn_diurnal, in_fn_semidiurnal)

    """ ICON comparison """
    year = 2020
    #site_model_comparison(year, 9, sd_fn_fmt, 'fhe', lats, lons, alt, icon_fn_fmt)
    #icon_sd_comparison(year, sd_fn_fmt, radar_list, lats, lons, alt, icon_fn_fmt)

    """ CTMT comparisons """
    # radar-by-radar comparison to CTMT
    year = 2008 
    #site_model_comparison(year, 10, sd_fn_fmt, 'sys', lats, lons, alt, ctmt_coeffs)
    #scores_by_radar = radar_by_radar_comparison(year, sd_fn_fmt, radar_list, lats, lons, alt, ctmt_coeffs)

    # Compare all months of the radar data against all months of CTMT
    time = dt.datetime(year, 1, 1)
    scores_matrix = ctmt_sd_comparison(time, sd_fn_fmt, radar_list, lats, lons, pressure, ctmt_coeffs)

    """ fitting """
    #fit_test(year, sd_fn_fmt, radar_list, lats, lons, alt, ctmt_coeffs)


def icon_sd_comparison(year, sd_fn_fmt, radar_list, lats, lons, alt, icon_fn_fmt):
    """ matrix evaluation of all months of SD vs all months of model """

    scores = np.zeros((12, len(radar_list))) * np.nan
    for i, month in enumerate(range(1, 13)):
        print(month)
        time = dt.datetime(year, month, 15)
        sd_wind = load_sd_wind(year, month, sd_fn_fmt, radar_list)
        icon = eval_icon_hme(time.strftime(icon_fn_fmt), lats, lons, alt, hr)
        for j, radar in enumerate(radar_list):
            if radar in sd_wind.keys():
                radar_wind = {radar: sd_wind[radar]}
                scores[i, j] = calc_weighted_rmse(icon, radar_wind)

    available_data_idx = np.isfinite(np.nanmean(scores, axis=0)) 
    scores = scores[:, available_data_idx]

    fig, ax = plt.subplots()
    heatmap = ax.pcolor(scores, edgecolors='w', vmin=0, vmax=30)
    ax.set_xticks(np.arange(0, scores.shape[1]))
    ax.set_yticks(np.arange(12), np.arange(1, 13))
    cb = plt.colorbar(heatmap)
    cb.set_label('Normalized RMSE (m/s)')
    ax.set_xticklabels(np.char.upper(radar_list[available_data_idx]))
    ax.set_ylabel('Month')
    ax.set_title('RMSEs vs Icon V3 %i' % year)
    plt.show()

    return scores


def site_model_comparison(year, month, sd_fn_fmt, radarcode, lats, lons, alt, model):

    sd_wind = load_sd_wind(year, month, sd_fn_fmt, [radarcode,])
    # TODO: calculate model wind at reference pressure instead of altitude
    
    if type(model) == str:
        time = dt.datetime(year, month, 15) 
        gridded_model = eval_icon_hme(time.strftime(model), lats, lons, alt, hr)
    else:
        gridded_model = calc_ctmt_winds.calc_full_wind(month, lats, lons, alt, model)  # CTMT winds on a grid

    model_wind = get_model_wind_at_sd_locs(gridded_model, sd_wind)
    plot_median_wind(sd_wind, radarcode, model=model_wind[radarcode]['model'])


def radar_by_radar_comparison(year, sd_fn_fmt, radar_list, lats, lons, alt, model_coeffs):
    """ radar by radar evaluation of SD winds vs CTMT model """

    scores = np.zeros((12, len(radar_list))) * np.nan
    for i, sdmonth in enumerate(range(1, 13)):
        sd_wind = load_sd_wind(year, sdmonth, sd_fn_fmt, radar_list)
        model = calc_ctmt_winds.calc_full_wind(
            sdmonth, lats, lons, alt, model_coeffs)  # CTMT winds on a grid
        for j, radar in enumerate(radar_list):
            if radar in sd_wind.keys():
                radar_wind = {radar: sd_wind[radar]}
                scores[i, j] = calc_weighted_rmse(model, radar_wind)

    available_data_idx = np.isfinite(np.nanmean(scores, axis=0)) 
    scores = scores[:, available_data_idx]

    fig, ax = plt.subplots()
    heatmap = ax.pcolor(scores, edgecolors='w', vmin=0, vmax=30)
    ax.set_xticks(np.arange(0, scores.shape[1]))
    ax.set_yticks(np.arange(12), np.arange(1, 13))
    cb = plt.colorbar(heatmap)
    cb.set_label('Normalized RMSE (m/s)')
    ax.set_xticklabels(np.char.upper(radar_list[available_data_idx]))
    ax.set_ylabel('Month')
    ax.set_title('RMSEs vs CTMT %i' % year)
    plt.show()

    return scores


def ctmt_sd_comparison(time, sd_fn_fmt, radar_list, lats, lons, pressure, model_coeffs):
    """ matrix evaluation of all months of SD vs all months of model """

    components = calc_ctmt_winds.table_of_components()
    # coefficients for amplitude of each component in U and V
    X0 = np.zeros(len(components['d'] + components['s']))

    scores = np.zeros((12, 12))
    for i, sdmonth in enumerate(range(1, 13)):
        sd_wind = load_sd_wind(time.year, sdmonth, sd_fn_fmt, radar_list)
        for j, mmonth in enumerate(range(1, 13)):

            model = calc_ctmt_winds.calc_full_wind_at_pressure_level(
                time, lats, lons, pressure, model_coeffs)  # model winds on a grid

            scores[i, j] = calc_weighted_rmse(model, sd_wind)

    fig, ax = plt.subplots()
    heatmap = ax.pcolor(scores, edgecolors='w', vmin=0, vmax=30)
    ax.set_xticks(np.arange(12), np.arange(1, 13))
    ax.set_yticks(np.arange(12), np.arange(1, 13))
    cb = plt.colorbar(heatmap)
    cb.set_label('Normalized RMSE (m/s)')
    ax.set_xlabel('CTMT Month')
    ax.set_ylabel('SD Month')
    plt.show()

    return scores


def fit_test(year, sd_fn_fmt, radar_list, lats, lons, alt, model_coeffs,
             valsites=['gbr', 'kod', 'hok'],
             badsites=['inv'],
             ):

    # TODO kick out the bad sites (>X m/s cost vs standard CTMT)
    month = 1

    # Load the SuperDARN wind data (NH only)
    sd_wind = load_sd_wind(year, month, sd_fn_fmt, radar_list)
    sd_wind_NH = downselect_sites(sd_wind, hem='N')
    sd_wind_novalsites = downselect_sites(
        sd_wind_NH, exclude=valsites)  # + badsites
    sd_wind_valsites = downselect_sites(sd_wind_NH, include=valsites)

    # Fit the model
    """
    pkl_fn = 'fit.pkl'
    try:
        fitted_model_coeffs = nc_utils.unpickle(pkl_fn)
    except:
    """
    fitted_model_coeffs, X = fit_model(
        year, lats, lons, alt, month, model_coeffs, sd_wind_novalsites)
    nc_utils.pickle(fitted_model_coeffs, pkl_fn)

    # run error analysis
    model = calc_ctmt_winds.calc_full_wind(
        month, lats, lons, alt, model_coeffs)  # CTMT winds on a grid
    fitted_model = calc_ctmt_winds.calc_full_wind(
        month, lats, lons, alt, fitted_model_coeffs)  # fitted winds on a grid

    errs_full = error_analysis(
        year, lats, lons, alt, model, sd_wind_novalsites)
    errs_full_fitted = error_analysis(
        year, lats, lons, alt, fitted_model, sd_wind_novalsites)
    errs_valsites = error_analysis(
        year, lats, lons, alt, model, sd_wind_valsites)
    errs_valsites_fitted = error_analysis(
        year, lats, lons, alt, fitted_model, sd_wind_valsites)

    # plotting/reporting
    disp_errs(errs_full, errs_full_fitted)
    plot_errors(errs_valsites, fitted=errs_valsites_fitted)
    # plot_errors(errs_full, fitted=errs_full_fitted)


def disp_errs(errs, errs_fitted):
    print("\n\n******** error scores (+ve = worse)")
    term = 'weighted_err_score'
    for station, vals in errs.items():
        print('%s: %1.2f %1.2f %1.2f' %
              (station, vals[term], errs_fitted[station][term], errs_fitted[station][term] - vals[term]))


def error_analysis(year, lats, lons, alt, model, sd_wind, verbose=False):
    """ compare the data against the model. 
    """
    breakpoint()
    wind = get_model_wind_at_sd_locs(model, sd_wind)

    if verbose:
        print("\n\n******** error scores")
    errs = {}
    for station, vals in wind.items():
        errs[station] = {}
        errs[station]['obs'] = vals['obs_med']
        errs[station]['mod'] = vals['model']
        errs[station]['error'] = vals['obs_med'] - vals['model']
        errs[station]['weighted_err_score'] = np.nanmean(
            np.abs(errs[station]['error']) / vals['obs_std'])
        errs[station]['obs_std'] = vals['obs_std']
        if verbose:
            print('%s: %1.1f' % (station, errs[station]['weighted_err_score']))

    return errs


def plot_errors(errs, fitted=None, ylim=[-30, 30]):
    if len(errs) > 6:
        errs = take(6, errs.items())

    fig, ax = plt.subplots(len(errs), 1)
    ct = 0
    for station, vals in errs.items():
        ax[ct].errorbar(hr, vals['obs'], yerr=vals['obs_std'],
                        label='Observed')
        ax[ct].plot(hr, vals['mod'], label='CTMT')
        if fitted:
            ax[ct].plot(hr, fitted[station]['mod'], label='Fitted')
        ax[ct].grid()
        ax[ct].set_xlabel('Hour (UT)')
        ax[ct].set_ylabel('Boresight Wind (m/s)')
        ax[ct].set_title(station)
        ax[ct].set_xlim([0, 24])
        ax[ct].set_ylim(ylim)

        ct += 1

    ax[0].legend()
    plt.show()


def fit_model(year, lats, lons, alt, month, model_coeffs, sd_wind):
    """ calculate a tidal fit that best matches the SuperDARN data 
    Use scaling factors to vary the coefficient amplitudes (6x diurnal, 8x semidiurnal
    How to vary phases??
    """

    time = dt.datetime(year, month, 1)

    """ Load SuperDARN wind """
    # plot_median_wind(wind, 'gbr')

    # Now create a cost function to minimize from there

    components = calc_ctmt_winds.table_of_components()
    # coefficients for amplitude of each component in U and V
    X0 = np.zeros(len(components['d'] + components['s']))

    result = powell_search(cost_function, X0, model_coeffs,
                           month, lats, lons, alt, sd_wind)
    print('**********')
    print(result.x)
    print('Final cost: %1.1f' % result.fun)

    # fit to the result
    fitted_model_coeffs = scale_model(model_coeffs, result.x)

    return fitted_model_coeffs, result.x


def cost_function(X, model_coeffs, month, lats, lons, alt, sd_wind):
    # Update the coefficients according to X
    fitted_model_coeffs = scale_model(model_coeffs, X)

    # Calculate the wind errors
    model = calc_ctmt_winds.calc_full_wind(
        month, lats, lons, alt, fitted_model_coeffs)  # model winds on a grid

    cost = calc_weighted_rmse(model, sd_wind)
    print('Cost: %1.1f' % cost)

    return cost


def calc_weighted_rmse(model, sd_wind):
    wind = get_model_wind_at_sd_locs(model, sd_wind)
    y = []
    Hx = []
    obs_errs = []
    for station, vals in wind.items():
        finidx = np.isfinite(vals['obs_med'])
        y += vals['obs_med'][finidx].tolist()
        Hx += vals['model'][finidx].tolist()
        obs_errs += vals['obs_std'][finidx].tolist()

    norm_obs_errs = obs_errs / np.mean(obs_errs)
    weighted_avg_rmse = np.sqrt(np.nanmean(
        ((np.array(y) - np.array(Hx)) / norm_obs_errs) ** 2))

    return weighted_avg_rmse


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
                fitted_model_coeffs[ds]['amp_%s_%s' %
                                        (component, direction)] *= 1 + X[ct]
            ct += 1

    return fitted_model_coeffs


def powell_search(cost_function, X0, model_coeffs, month, lats, lons, alt, sd_wind):
    result = minimize(cost_function, X0, method='powell',
        args=(model_coeffs, month, lats, lons, alt, sd_wind))
    return result


def load_sd_wind(year, month, sd_fn_fmt, radar_list, qc=True):
    """ 
    loads a month of SuperDARN wind data 
    See also: plot_median_wind()
    """
    wind = {}
    for radarcode in radar_list:
        wind[radarcode] = {}
        zeroarr = np.zeros((31, 24)) * np.nan
        wind[radarcode]['obs_daily'] = zeroarr.copy()
        wind[radarcode]['hour'] = hr
        time = dt.datetime(year, month, 1)
        dayct = 0
        wind[radarcode]['year'] = year
        wind[radarcode]['month'] = month
        while time.month == month:

            # Load the SuperDARN wind
            try:
                sd = nc_utils.load_nc(time.strftime(
                    sd_fn_fmt.format(radarcode)))
            except:
                time += dt.timedelta(days=1)
                continue

            hridx = np.isin(hr, sd.variables['hour'][:])
            wind[radarcode]['obs_daily'][dayct, hridx] = sd.variables['Vx'][:]
            wind[radarcode]['lat'] = sd.lat
            wind[radarcode]['lon'] = sd.lon
            wind[radarcode]['boresight'] = float(sd.boresight.split()[0])
            time += dt.timedelta(days=1)
            dayct += 1

        # Remove >100 m/s data-points
        wind[radarcode]['obs_daily'][np.abs(wind[radarcode]['obs_daily']) > 100] *= np.nan

        # Calculate the median and standard deviation
        wind[radarcode]['obs_med'] = np.nanmedian(wind[radarcode]['obs_daily'], axis=0)
        wind[radarcode]['obs_std'] = np.nanstd(wind[radarcode]['obs_daily'], axis=0)

        # id the entries with zero std
        zeroidx = wind[radarcode]['obs_std'] == 0

        # id those data where few data-points are available
        low_data_idx = np.sum(np.isfinite(wind[radarcode]['obs_daily']), axis=0) < 15

        # nan out the bad stuff
        bad_idx = np.logical_or(zeroidx, low_data_idx)
        wind[radarcode]['obs_std'][bad_idx] *= np.nan
        wind[radarcode]['obs_med'][bad_idx] *= np.nan

    # throw out bad months of data
    for radarcode in radar_list:

        if np.isfinite(wind[radarcode]['obs_daily']).sum() == 0:
            wind.pop(radarcode)
            continue

        if qc:
            if np.any(np.abs(wind[radarcode]['obs_med']) > 50):
                #print('%s vals > 50 m/s - popping' % radarcode)
                wind.pop(radarcode)
                continue

            if np.sum(np.isfinite(wind[radarcode]['obs_med'])) < 22:
                print('%s insufficient data-points - popping' % radarcode)
                wind.pop(radarcode)
                continue
            
            # id values where the uncertainty is too large
            qualscore = np.nanmean(wind[radarcode]['obs_std']) / np.nanstd(wind[radarcode]['obs_med'])
            #plot_median_wind(wind, radarcode)
            if qualscore > 3:
                print('%s %1.1f' % (radarcode, qualscore))
                print('%s qualscore too high - popping' % radarcode)
                wind.pop(radarcode)
                continue
    return wind


def get_model_wind_at_sd_locs(model, wind):
    """ Calculate the model wind in the boresight direction at the radar locations 
    """
    # Setup interpolators
    interp_fn_U = RegularGridInterpolator(
        (model['UTs'], model['lats'], model['lons']),
        np.squeeze(model['wind'][0, :, :, :]),
    )
    interp_fn_V = RegularGridInterpolator(
        (model['UTs'], model['lats'], model['lons']),
        np.squeeze(model['wind'][1, :, :, :]),
    )

    # Get the model wind at the radar locs
    for radarcode, vals in wind.items():
        model_boresight_wind = calc_boresight_wind(
            vals['lat'], vals['lon'], vals['boresight'], interp_fn_U, interp_fn_V)
        wind[radarcode]['model'] = model_boresight_wind

    return wind


def plot_median_wind(wind, code, model=None):
    plt.plot(hr, wind[code]['obs_daily'].T, '.k', label='Radar data')
    plt.errorbar(hr, wind[code]['obs_med'], color='m', 
        yerr=wind[code]['obs_std'], linewidth=2, label='Radar median')
    if model is not None:
        plt.plot(hr, model, label='Model')

    handles, labels = plt.gca().get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    plt.legend(by_label.values(), by_label.keys())
    plt.grid()
    plt.xlabel('Hour (UT)')
    plt.ylabel('Boresight Wind (m/s)')
    plt.title('%s %i/%i' % (code.upper(), wind[code]['month'], wind[code]['year']))
    plt.show()


def calc_boresight_wind(lat, lon, boresight, interp_fn_U, interp_fn_V):
    """ Get model boresight winds at the SuperDARN locations """
    boresight_rad = np.deg2rad(boresight)
    sd_lon = np.array([lon,])
    sd_lon[sd_lon < 0] += 360.

    """ Interpolate """
    # Get the model U/V at the radar location, for the specified month
    U = interp_fn_U(np.squeeze(
        np.array([hr, np.ones_like(hr) * lat, np.ones_like(hr) * sd_lon]).T))
    V = interp_fn_V(np.squeeze(
        np.array([hr, np.ones_like(hr) * lat, np.ones_like(hr) * sd_lon]).T))
    model_boresight_wind = np.sin(
        boresight_rad) * U + np.cos(boresight_rad) * V

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
