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
import matplotlib.pyplot as plt
import cartopy
import cartopy.crs as ccrs
from scipy.interpolate import griddata

font = {'size'   : 18}

matplotlib.rc('font', **font)

"""
Demonstrate velocity vector bearing calculation using nvector
Plots the fitACF-level nc files
"""

wgs84 = nv.FrameE(name='WGS84')
depth = 0  # nvector uses depths in m


def main(
    in_fn_fmt='~/data/superdarn/netcdf/%Y/%m/%Y%m%d.wal.a.despeck.fitacf3.nc',
    map_plt_fn_fmt = 'plots/%Y%m%d/maps/{radarcode}/%Y%m%d-%H%M.png',
    beam_plt_fn_fmt = 'plots/%Y%m%d/beam_rtis/{radarcode}/beam_{bmnum}_%Y%m%d.png',
    stime = dt.datetime(2023, 11, 18, 12, 0),
    etime = dt.datetime(2023, 11, 18, 16, 0),
    tstep = dt.timedelta(minutes=1),

    clim = [-100, 100],

    map_extent = [-80, -67.5, 37, 50,],
    #map_extent = [-100, -67.5, 37, 50,],

    rangelim = [0, 2000],
    maxpwr = 15,
    plot_gs = True,
):

    in_fn = stime.strftime(in_fn_fmt)
    radarcode = os.path.basename(in_fn_fmt).split('.')[1]
    map_plt_fn_fmt = map_plt_fn_fmt.format(radarcode=radarcode)

    os.makedirs(os.path.dirname(stime.strftime(map_plt_fn_fmt)), exist_ok=True)
    os.makedirs(stime.strftime(os.path.dirname(beam_plt_fn_fmt).format(radarcode=radarcode)), exist_ok=True)

    sd_data, sdrad = nc_utils.ncread_vars(in_fn), nc_utils.load_nc(in_fn)
    utlim = [stime.hour + stime.minute / 60, etime.hour + etime.minute / 60]
    for bmnum in range(sdrad.beams.max() + 1):
        plot_rti(sd_data, sdrad, bmnum, clim, rangelim, utlim, maxpwr)
        plt_fn = stime.strftime(beam_plt_fn_fmt.format(radarcode=radarcode, bmnum=bmnum))
        plt.savefig(f'{plt_fn}')
        print(f'Saved to {plt_fn}')
        plt.close()

    plot_on_map(map_plt_fn_fmt, stime, etime, tstep, sd_data, sdrad, clim, map_extent, maxpwr, plot_gs)
    """
    rlat, rlon, lats, lons, vels = load_example_data(in_fn)
    brng_deg = calc_bearings(rlat, rlon, lats, lons)
    plot_quiver(rlat, rlon, lats, lons, vels, brng_deg, fname)
    """

def plot_on_map(
        plt_fn_fmt, stime, etime, tstep, sd_data, sdrad, clim, map_extent, maxpwr, plot_gs, 
):
    """ Plot LOS velocities on map with alpha=power) """
    time = stime
    td_mjd = tstep.total_seconds() / 86400 / 2
    pwr = sd_data['p_l']
    pwr_norm = pwr / maxpwr
    pwr_norm[pwr_norm > 1] = 1
    pwr_norm[pwr_norm < 0] = 0

    lats = np.arange(min(sd_data['lat']), max(sd_data['lat']), 0.1)
    lons = np.arange(min(sd_data['lon']), max(sd_data['lon']), 0.1)
    grid_lat, grid_lon = np.meshgrid(lats, lons)

    while time <= etime:
        time_mjd = dt_to_mjd(time)
        tidx = np.abs(sd_data['mjd'] - time_mjd) < td_mjd
        gs_idx = sd_data['gflg'] == 1
        is_idx = sd_data['gflg'] == 0

        fig = plt.figure(figsize=(12, 6))
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
        ax.set_extent(map_extent)
        plt.title(time.strftime("%Y-%m-%d %H:%M"))
        plt.set_cmap('Spectral')

        ax.patch.set_facecolor(color='black')
        ax.add_feature(cartopy.feature.LAND, color='black')
        ax.coastlines(resolution='50m', color='w')
        ax.add_feature(cartopy.feature.LAKES.with_scale('50m'), facecolor='k', edgecolor='w')
        gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                          linewidth=1, color='white', linestyle='--')
        gl.top_labels = False
        gl.right_labels = False
        
        idx = tidx & is_idx

        im = ax.scatter([0, 0.1, 0.2], [0, 0.1, 0.2], c=(clim + [0.]), alpha=0, vmin=clim[0], vmax=clim[1], edgecolors='none')
        #grid_v = griddata((sd_data['lat'][idx], sd_data['lon'][idx]), sd_data['v'][idx], (grid_lat.ravel(), grid_lon.ravel()))
        if np.sum(idx) > 0:
            im = ax.scatter(
                sd_data['lon'][idx], sd_data['lat'][idx], 
                c=sd_data['v'][idx],
                alpha=pwr_norm[idx],
                vmin=clim[0], vmax=clim[1],
                edgecolors='none',
            )
            
            if (np.sum(tidx & gs_idx) > 0) and plot_gs:
                im_gs = ax.scatter(
                    sd_data['lon'][tidx & gs_idx], sd_data['lat'][tidx & gs_idx], 
                    c='w',
                    alpha=pwr_norm[tidx & gs_idx],
                )

        cbar = fig.colorbar(im, ax=ax, orientation='vertical')
        cbar.set_label('Vel. towards radar (m/s)')

        ax.plot(sdrad.lon, sdrad.lat, '.r', markersize=10)
        plt.savefig(time.strftime(plt_fn_fmt))
        print(f'saved to {time.strftime(plt_fn_fmt)}')
        plt.close()

        time += tstep
    


def plot_rti(sd_data, sdrad, bmnum, clim, rangelim, utlim, maxpwr):

    bmidx = sd_data['beam'] == bmnum
    idx = bmidx 

    ranges = np.linspace(0, int(sdrad.rsep_km * sdrad.maxrangegate), int(sdrad.maxrangegate) + 1)
    times = np.arange(0, 60 * 24) 
    sdtime = np.round( (sd_data['mjd'] - np.floor(sd_data['mjd'])) * 60 * 24)

    pwr = np.zeros((len(times), len(ranges))) * np.nan
    vel = np.zeros((len(times), len(ranges))) * np.nan
    for ind, val in enumerate(sd_data['p_l'][idx]):
        pwr[times == sdtime[idx][ind], ranges == sd_data['range'][idx][ind]] = val 
        vel[times == sdtime[idx][ind], ranges == sd_data['range'][idx][ind]] = sd_data['v'][idx][ind]

    fig, ax = plt.subplots()
    fig.set_figheight(6)
    fig.set_figwidth(12)
    plt.suptitle(f"Beam {bmnum}: {sdrad.brng_at_15deg_el[bmnum]:,.1f} degrees East of North")
    ax.set_facecolor('k')
    alpha = pwr.T
    alpha /= maxpwr
    alpha[alpha > 1] = 1
    alpha[alpha < 0] = 0
    alpha[np.isnan(alpha)] = 0
    im0 = ax.pcolormesh(times / 60, ranges, vel.T, alpha=alpha, vmin=clim[0], vmax=clim[1], cmap='Spectral')
    ax.set_xlabel('Hour (UT)')
    ax.set_ylim(rangelim)
    ax.set_xlim(utlim)

    ax.set_ylabel('Range (km)')
    ax.grid(which='major', color='g', linewidth=0.05)
    ax.grid(which='minor', color='g', linewidth=0.01)
    ax.minorticks_on()

    divider = make_axes_locatable(ax)
    cax = divider.append_axes('right', size='3%', pad=0.05)
    cbar = fig.colorbar(im0, cax=cax, orientation='vertical')
    cbar.set_label('Vel. (m/s)')


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
    main()
