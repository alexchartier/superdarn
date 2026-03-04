# Demonstrate velocity vector bearing calculation using nvector
# Plots the fitACF-level nc files

import datetime as dt
import os
import sys

import matplotlib
import matplotlib.pyplot as plt
import nvector as nv
import numpy as np
from mpl_toolkits.axes_grid1 import make_axes_locatable

import cartopy
import cartopy.crs as ccrs
from scipy.interpolate import griddata

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (
    repo_root,
    os.path.join(repo_root, "update_data_proc"),
    os.path.join(repo_root, "utils"),
):
    if path not in sys.path:
        sys.path.insert(0, path)

import nc_utils
import jdutil
import radFov

font = {"size": 18}

matplotlib.rc("font", **font)

wgs84 = nv.FrameE(name='WGS84')
depth = 0  # nvector uses depths in m


def main(
    in_fn_fmt="/Users/chartat1/data/superdarn/fit_nc_3/%Y/%m/%Y%m%d.wal.a.nc",
    map_plt_fn_fmt="plots/maps/%Y%m%d/{radarcode}/%Y%m%d-%H%M.png",
    beam_plt_fn_fmt="plots/beam_rtis/%Y%m/{radarcode}/beam_{bmnum}_%Y%m%d.png",
    stime=dt.datetime(2023, 7, 28, 0, 0),
    etime=dt.datetime(2023, 8, 1, 0, 0),
    tstep=dt.timedelta(minutes=10),
    clim=None,
    map_extent=None,
    rangelim=None,
    maxpwr=15,
    plot_gs=True,
    plot_fov=True,
    fov_alt_km=300,
):
    if clim is None:
        clim = [-100, 100]
    if map_extent is None:
        map_extent = [-80, -67.5, 37, 50]
    # map_extent = [-100, -67.5, 37, 50]
    if rangelim is None:
        rangelim = [0, 2000]

    radarcode = os.path.basename(in_fn_fmt).split('.')[1]
    map_plt_fn_fmt = map_plt_fn_fmt.format(radarcode=radarcode)

    day = stime.date()
    end_day = etime.date()
    day_starts = []
    while day <= end_day:
        day_starts.append(dt.datetime.combine(day, dt.time()))
        day += dt.timedelta(days=1)

    utlim = [0, 24]
    for day_start in day_starts:
        in_fn = day_start.strftime(in_fn_fmt)
        if not os.path.exists(in_fn):
            print(f"Missing file: {in_fn}")
            continue
        sd_data, sdrad = nc_utils.ncread_vars(in_fn), nc_utils.load_nc(in_fn)
        for bmnum in range(sdrad.beams.max() + 1):
            plot_rti(sd_data, sdrad, bmnum, clim, rangelim, utlim, maxpwr)
            plt_fn = day_start.strftime(beam_plt_fn_fmt.format(radarcode=radarcode, bmnum=bmnum))
            os.makedirs(os.path.dirname(plt_fn), exist_ok=True)
            plt.savefig(f"{plt_fn}")
            print(f"Saved to {plt_fn}")
            plt.close()

    for day_start in day_starts:
        in_fn = day_start.strftime(in_fn_fmt)
        if not os.path.exists(in_fn):
            print(f"Missing file: {in_fn}")
            continue
        sd_data, sdrad = nc_utils.ncread_vars(in_fn), nc_utils.load_nc(in_fn)
        day_end = day_start + dt.timedelta(days=1) - dt.timedelta(seconds=1)
        day_stime = max(stime, day_start)
        day_etime = min(etime, day_end)
        if day_stime <= day_etime:
            plot_on_map(
                map_plt_fn_fmt,
                day_stime,
                day_etime,
                tstep,
                sd_data,
                sdrad,
                clim,
                map_extent,
                maxpwr,
                plot_gs,
                plot_fov,
                fov_alt_km,
            )
    # rlat, rlon, lats, lons, vels = load_example_data(in_fn)
    # brng_deg = calc_bearings(rlat, rlon, lats, lons)
    # plot_quiver(rlat, rlon, lats, lons, vels, brng_deg, fname)


def plot_on_map(
    plt_fn_fmt,
    stime,
    etime,
    tstep,
    sd_data,
    sdrad,
    clim,
    map_extent,
    maxpwr,
    plot_gs,
    plot_fov,
    fov_alt_km,
):
    # Plot LOS velocities on map with alpha=power.
    time = stime
    td_mjd = tstep.total_seconds() / 86400 / 2
    pwr = sd_data['p_l']
    pwr_norm = pwr / maxpwr
    pwr_norm[pwr_norm > 1] = 1
    pwr_norm[pwr_norm < 0] = 0

    lats = np.arange(min(sd_data['lat']), max(sd_data['lat']), 0.1)
    lons = np.arange(min(sd_data['lon']), max(sd_data['lon']), 0.1)
    grid_lat, grid_lon = np.meshgrid(lats, lons)

    fov_poly = None
    if plot_fov:
        fov_poly = build_fov_polygon(sdrad, fov_alt_km=fov_alt_km)

    while time <= etime:
        time_mjd = dt_to_mjd(time)
        tidx = np.abs(sd_data['mjd'] - time_mjd) < td_mjd
        gs_idx = sd_data['gflg'] == 1
        is_idx = sd_data['gflg'] == 0

        fig = plt.figure(figsize=(12, 6))
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
        ax.set_extent(map_extent)
        plt.title(time.strftime("%Y-%m-%d %H:%M"))
        cmap = plt.get_cmap("Spectral")
        norm = matplotlib.colors.Normalize(vmin=clim[0], vmax=clim[1])

        ax.patch.set_facecolor(color='black')
        ax.add_feature(cartopy.feature.LAND, color='black')
        ax.coastlines(resolution='50m', color='w')
        ax.add_feature(cartopy.feature.LAKES.with_scale('50m'), facecolor='k', edgecolor='w')
        gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                          linewidth=1, color='white', linestyle='--')
        gl.top_labels = False
        gl.right_labels = False

        if fov_poly is not None:
            fov_lats, fov_lons = fov_poly
            ax.fill(
                fov_lons,
                fov_lats,
                transform=ccrs.PlateCarree(),
                facecolor='white',
                edgecolor='white',
                linewidth=1.0,
                alpha=0.15,
                zorder=3,
            )
        
        idx = tidx & is_idx

        #grid_v = griddata((sd_data['lat'][idx], sd_data['lon'][idx]), sd_data['v'][idx], (grid_lat.ravel(), grid_lon.ravel()))
        if np.sum(idx) > 0:
            ax.scatter(
                sd_data['lon'][idx], sd_data['lat'][idx], 
                c=sd_data['v'][idx],
                alpha=pwr_norm[idx],
                cmap=cmap,
                norm=norm,
                edgecolors='none',
            )
            
            if (np.sum(tidx & gs_idx) > 0) and plot_gs:
                im_gs = ax.scatter(
                    sd_data['lon'][tidx & gs_idx], sd_data['lat'][tidx & gs_idx], 
                    c='w',
                    alpha=pwr_norm[tidx & gs_idx],
                )

        sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, orientation='vertical')
        cbar.set_label('Vel. towards radar (m/s)')

        ax.plot(sdrad.lon, sdrad.lat, '.r', markersize=10)
        out_fn = time.strftime(plt_fn_fmt)
        os.makedirs(os.path.dirname(out_fn), exist_ok=True)
        plt.savefig(out_fn)
        print(f"saved to {out_fn}")
        plt.close()

        time += tstep
    


def plot_rti(sd_data, sdrad, bmnum, clim, rangelim, utlim, maxpwr):

    bmidx = sd_data['beam'] == bmnum
    idx = bmidx 

    ranges = np.arange(int(sdrad.maxrangegate) + 1) * sdrad.rsep_km
    times = np.arange(0, 60 * 24) 
    sdtime = np.floor((sd_data['mjd'] - np.floor(sd_data['mjd'])) * 60 * 24).astype(int)

    pwr = np.zeros((len(times), len(ranges))) * np.nan
    vel = np.zeros((len(times), len(ranges))) * np.nan
    if np.any(idx):
        range_vals = sd_data["range"][idx]
        if (
            np.nanmax(range_vals) <= sdrad.maxrangegate + 1
            and np.allclose(range_vals, np.round(range_vals), equal_nan=True)
        ):
            range_idx = np.round(range_vals).astype(int)
        else:
            range_idx = np.round(range_vals / sdrad.rsep_km).astype(int)

        time_idx = sdtime[idx]
        valid = (
            (time_idx >= 0)
            & (time_idx < len(times))
            & (range_idx >= 0)
            & (range_idx < len(ranges))
        )
        pwr[time_idx[valid], range_idx[valid]] = sd_data["p_l"][idx][valid]
        vel[time_idx[valid], range_idx[valid]] = sd_data["v"][idx][valid]

    if utlim is None or utlim[0] == utlim[1]:
        if np.any(idx):
            tmin = int(np.min(sdtime[idx]))
            tmax = int(np.max(sdtime[idx]))
            utlim = [tmin / 60, min(24, (tmax + 1) / 60)]
            if utlim[0] == utlim[1]:
                utlim = [max(0, utlim[0] - 0.5), min(24, utlim[1] + 0.5)]
        else:
            utlim = [0, 24]

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


def build_fov_polygon(sdrad, fov_alt_km=300, hop=2):
    try:
        brngs = np.asarray(sdrad.brng_at_15deg_el)
        max_range_km = float(sdrad.maxrangegate) * float(sdrad.rsep_km)
        radar_alt_km = float(sdrad.alt)
        if radar_alt_km > 10:
            radar_alt_km /= 1000.0
        lats = []
        lons = []
        for brng in brngs:
            beam_off = brng - sdrad.boresight
            lat, lon = radFov.calcFieldPnt(
                sdrad.lat,
                sdrad.lon,
                radar_alt_km,
                sdrad.boresight,
                beam_off,
                max_range_km,
                hop=hop,
                adjusted_sr=False,
                altitude=fov_alt_km,
            )
            lon = ((lon + 180) % 360) - 180
            lats.append(lat)
            lons.append(lon)
        if not lats:
            return None
        poly_lats = [sdrad.lat] + lats + [sdrad.lat]
        poly_lons = [sdrad.lon] + lons + [sdrad.lon]
        return poly_lats, poly_lons
    except Exception as exc:
        print(f"Unable to compute FOV polygon: {exc}")
        return None


def dt_to_mjd(dt):
    mjd = jdutil.jd_to_mjd(jdutil.datetime_to_jd(dt) )
    return mjd


def mjd_to_dt(mjd):
    dt = jdutil.jd_to_datetime(jdutil.mjd_to_jd(mjd))
    return dt


if __name__ == '__main__':
    main()
