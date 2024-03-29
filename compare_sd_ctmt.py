""" 
Compare SD against CTMT winds

 TODO: Notes from Ruth: 
    #1 calculate fit based on just one hemisphere at a time. 
    #2 do a ~6-year comparison (2002 - 2008) against the CTMT
    #3 compare  performance against the average against all realizations of CTMT

    [later] go from mean to median to mitigate impact of high-lat convection contamination 

"""


import nc_utils   # available from github.com/alexchartier/nc_utils
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import minimize
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

):

    radar_list = sd_utils.get_radar_params(hdw_dat_dir)
    model_coeffs = calc_ctmt_winds.load_wind_coeffs(in_fn_diurnal, in_fn_semidiurnal)

    #error_analysis(year, lats, lons, alt, model, in_fn_fmt_wind, radar_list)

    month = 1
    fit_model(year, lats, lons, alt, month, model_coeffs, in_fn_fmt_wind, radar_list)


def fit_model(year, lats, lons, alt, month, model_coeffs, in_fn_fmt_wind, radar_list):
    """ calculate a tidal fit that best matches the SuperDARN data 
    TODO: downselect to just NH (or SH) sites, update fit coefficients
    Use scaling factors to vary the coefficient amplitudes (6x diurnal, 8x semidiurnal
    How to vary phases??
    """ 
    
    time = dt.datetime(year, month, 1)

    wind = load_sd_wind(year, month, in_fn_fmt_wind, radar_list)

    # 2 lines just an example
    model = calc_ctmt_winds.calc_full_wind(lats, lons, alt, model_coeffs)
    wind = get_ctmt_wind_at_sd_locs(model, month, wind)  
    breakpoint()

    # Now create a cost function to minimize from there
    components = calc_ctmt_winds.table_of_components() 
    dirns = 'u', 'v'

    # TODO: add phase adjustment (coeffs=2x len comps, phase += coeffs * 12)
    # TODO: also decide whether to change the u and v independently (currently they're scaled together)
    X0 = np.zeros(len(components['d'] + components['s'])) # coefficients for amplitude of each component in U and V
    fitted_model_coeffs = model_coeffs.copy()

    def cost_function(X): 
        ct = 0
        for ds in 'd', 's':  # diurnal/semidiurnal 
            for component in components[ds]:  # wave component
                for direction in dirns:  # u/v
                    fitted_model_coeffs[ds]['amp_%s_%s' % (component, direction)] *= 1 + X[ct] * 1E2
                ct += 1

        model = calc_ctmt_winds.calc_full_wind(lats, lons, alt, fitted_model_coeffs)

        # mean_wind contains the modeled and observed wind 
        # note the >3 STD data-points are removed
        mean_wind = calc_monthly_mean_wind(model, time, time, in_fn_fmt_wind, radar_list)  
        weighted_errs = []
        for station, vals in mean_wind.items():
            weighted_errs += (vals['err_vs_model'] / vals['obs_std']).tolist()
        cost = np.nansum(np.array(weighted_errs)**2)
        print(X)
        print('Cost: %1.1f' % cost)

        return cost
    
    X = minimize(cost_function, X0, method='nelder-mead')
    

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

    
def get_ctmt_wind_at_sd_locs(model, month, wind):
    """ Calculate the model wind in the boresight direction at the radar locations 
    TODO: break out the SuperDARN data-load from this
    """
    # Setup interpolators
    interp_fn_U = RegularGridInterpolator(
        (model['lsts'], model['lats'], model['lons']), 
        np.squeeze(model['wind'][model['months']==month, :, 0, :, :]),
    )
    interp_fn_V = RegularGridInterpolator(
        (model['lsts'], model['lats'], model['lons']), 
        np.squeeze(model['wind'][model['months']==month, :, 1, :, :]),
    )

    """ Get the model wind at the radar locs """
    for radarcode, vals in wind.items():
        """ get the model and observed winds into a structure """
        model_boresight_wind = calc_boresight_wind(vals['lat'], vals['lon'], vals['boresight'], interp_fn_U, interp_fn_V)
        wind[radarcode]['model'] = model_boresight_wind

    return wind


def calc_err(wind):
    """ TODOO: run through the stations and calculate MAD-weighted errors (maybe MAD**2) """


def error_analysis(year, lats, lons, alt, model_coeffs, in_fn_fmt_wind, radar_list):
    """ compare the data against the model. 
    Run all 12 months of model winds against model Jan, then run against correct months 
    """

    """ Load the model """
    model = calc_ctmt_winds.calc_full_wind(lats, lons, alt, model_coeffs)

    # NB: the 'obs' values can change between the following two versions, 
    # as points >3 standard deviations from the model are kicked from the analysis 

    """ calculate the RMSEs against one model month """
    wind_vs_jan = {}
    model_time = dt.datetime(year, 1, 1)
    for month in np.arange(1, 13):
        # Calculate 24 hours of monthly mean model & observed winds at all the stations
        obs_start_time = dt.datetime(year, month, 1)
        wind_vs_jan[month] = calc_monthly_mean_wind(model, model_time, obs_start_time, in_fn_fmt_wind, radar_list)
        #plot_mean_wind(wind_vs_jan[month]['kap']) 
    print('*** Errors vs Jan model *** ')
    wind_errs_jan = calc_station_avg_errs(wind_vs_jan, radar_list)

    """ calculate the RMSEs against the correct model months """
    wind_vs_right_month = {}
    for month in np.arange(1, 13):
        # Calculate 24 hours of monthly mean model & observed winds at all the stations
        time = dt.datetime(year, month, 1)
        wind_vs_right_month[month] = calc_monthly_mean_wind(model, time, time, in_fn_fmt_wind, radar_list)
        #plot_mean_wind(wind_vs_right_month[month]['kap']) 
    print('*** Errors vs right month model *** ')
    wind_errs_right_month = calc_station_avg_errs(wind_vs_right_month, radar_list)
   

def calc_station_avg_errs(annual_mean_wind, radar_list):
    """ get overall RMS of observations and obs-model diffs on station-by-station basis"""

    #set up storage  
    out = {}
    overall = {}
    varnames = 'obs', 'err_vs_model'
    for vn in varnames:
        overall[vn] = 0
    for station in radar_list:
        out[station] = {}
        for vn in varnames:
            out[station][vn] = []
    
    for month in np.arange(1, 13):
        for station, vals in annual_mean_wind[month].items():
            for vn in varnames:
                out[station][vn].append(vals[vn])
        
    # Calculate average errors for all the model months
    print('Station, Obs RMS, RMSE vs model')
    ct = 0
    for station, vals in out.items():
        if not vals[varnames[0]]:
            continue
        for vn in varnames: 
            out[station][vn] = np.array(vals[vn])
            out[station]['rms_' + vn] = np.sqrt(np.nanmean(out[station][vn] ** 2))
            overall[vn] += out[station]['rms_' + vn] 

        print('%s       %1.1f    %1.1f' % \
            (station, out[station]['rms_obs'], out[station]['rms_err_vs_model']))
        ct += 1

    print('Overall %s: %1.1f, %s: %1.1f\n' % \
        (varnames[0], overall[varnames[0]] / ct, varnames[1], overall[varnames[1]] / ct))

    return out


def remove_anomalies(mean_wind, maxerr=3):
    """ calculate the errors by radar, considering the Std. Devs. Remove those that are >maxerr STDs out """
    badids = []
    errs_out = []
    for k, v in mean_wind.items():
        errs = v['obs'] - v['model']
        err_pct = errs / v['obs_std'] * 100
        mean_err = np.nanmean(np.abs(err_pct))
        errs_out.append(mean_err)
        # print('%s %1.0f' % (k, mean_err))

        if mean_err > maxerr * 100:
            badids.append(k)
        mean_wind[k]['err_vs_model'] = errs
    [mean_wind.pop(k) for k in badids]

    return mean_wind


def plot_median_wind(wind):
    code = 'gbr'
    plt.errorbar(hr, wind[code]['obs_med'], yerr=wind[code]['obs_MAD'])
    plt.plot(hr, wind[code]['obs_daily'].T, '.')
    plt.grid()
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


if __name__ == '__main__':
    main()

















