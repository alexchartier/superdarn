import pydarn
import glob
import matplotlib.pyplot as plt
from matplotlib import ticker, cm, colors
import numpy as np
import jdutil
import datetime as dt
import aacgmv2
import os
from sd_utils import get_radar_params, id_hdw_params_t, get_random_string, get_radar_list
import netCDF4
import nc_utils
import nvector as nv
wgs84 = nv.FrameE(name='WGS84')

MIN_FITACF_FILE_SIZE = 1E5 # bytes

def main(
    stime = dt.datetime(2015, 3, 15),
    etime = dt.datetime(2015, 3, 18),
    fit_fn_fmt = '/project/superdarn/data/fitacf/%Y/%m/%Y%m%d.*.v3.0.fit',
    grid_dirn = '/project/superdarn/data/grid/%Y/%m/',
    out_dirn = '/project/superdarn/data/grid_nc/%Y/%m/',
    hdw_dat_dir = '/project/superdarn/software/rst/tables/superdarn/hdw/',
    clobber = False):

    time = stime
    while time <= etime:
        grid_dirn_t = time.strftime(grid_dirn)
        out_dirn_t = time.strftime(out_dirn)
        os.makedirs(grid_dirn_t, exist_ok=True)
        os.makedirs(out_dirn_t, exist_ok=True)

        flist = glob.glob(time.strftime(fit_fn_fmt))
        for fit_fn in flist:
            fn_head = '.'.join(os.path.basename(fit_fn).split('.')[:-1])
            grid_fn = os.path.join(grid_dirn_t, fn_head + '.grid')
            out_fn = os.path.join(out_dirn_t, fn_head + '.grid.nc')
            convert_fit_to_grid_nc(time, fit_fn, grid_fn, out_fn, hdw_dat_dir, clobber=clobber)

        time += dt.timedelta(days=1)
        

def convert_fit_to_grid_nc(time, fit_fname, grid_fname, out_fname, hdw_dat_dir,
    fitVersion='3.0',
    ref_ht=300.,  # matches the RST operation
    convert_cmd='make_grid -xtd -chisham -ion %s > %s',
    clobber=False,
):
    """ Convert fitACF files to .grid (median-filtered & geolocated), then to netCDF """

    # Check if file exists
    if os.path.isfile(out_fname):
        if not clobber:
            print('Output file exists: %s - skipping' % out_fname)
            return 

    # Run fit to GRID file conversion 
    status = fit_to_grid(fit_fname, grid_fname, convert_cmd, clobber=clobber)

    # load
    SDarn_read = pydarn.SuperDARNRead(grid_fname)
    grid_data = SDarn_read.read_grid()
    radar_info = get_radar_params(hdw_dat_dir)
    radar_code = os.path.basename(fit_fname).split('.')[1]
    radar_info_t = id_hdw_params_t(time, radar_info[radar_code])
    
    # set up data holders
    copy_vn = ['vector.mlat', 'vector.mlon', 'vector.kvect', 'vector.vel.median', 
        'vector.vel.sd', 'vector.pwr.median', 'vector.wdt.median',
    ]
    new_vn = ['mjd_start', 'mjd_end', 'vector.glat', 'vector.glon', 'vector.g_kvect']
    out_vars = {}
    for vn in copy_vn + new_vn:
        out_vars[vn] = []

    # run through and fill out the out_vars
    for data in grid_data:

        # Skip empty entries
        if 'vector.mlat' not in data.keys():
            continue

        # straight copy the easy stuff 
        for vn in copy_vn:
            out_vars[vn] = np.append(out_vars[vn], data[vn])

        # Create the MJD start and end time vectors
        stime = dt.datetime(
            int(data['start.year']), int(data['start.month']), int(data['start.day']),
            int(data['start.hour']), int(data['start.minute']), int(data['start.second']),
        )
        etime = dt.datetime(
            int(data['end.year']), int(data['end.month']), int(data['end.day']),
            int(data['end.hour']), int(data['end.minute']), int(data['end.second']),
        )
        shape = np.ones(data['vector.mlat'].shape)
        out_vars['mjd_start'] = np.append(out_vars['mjd_start'], jdutil.jd_to_mjd(jdutil.datetime_to_jd(stime)) * shape)
        out_vars['mjd_end'] = np.append(out_vars['mjd_end'], jdutil.jd_to_mjd(jdutil.datetime_to_jd(etime)) * shape)

        # AACGM to geo
        mlat = data['vector.mlat']
        mlon = data['vector.mlon']
        [glat, glon, alt] = aacgmv2.convert_latlon_arr(mlat, mlon, ref_ht, stime, method_code="A2G")
        out_vars['vector.glat'] = np.append(out_vars['vector.glat'], glat)
        out_vars['vector.glon'] = np.append(out_vars['vector.glon'], glon)
        
        # bearing
        gaz = calc_bearings(radar_info_t['glat'], radar_info_t['glon'], glat, glon, ref_ht)
        out_vars['vector.g_kvect'] = np.append(out_vars['vector.g_kvect'], gaz)

    # Write out to netCDF
    var_defs = def_vars()
    dim_defs = {
        'npts': out_vars['mjd_start'].shape[0],
    }
    hdr_vals = get_hdr_vals(radar_info_t, fitVersion)
    header_info = def_header_info(fit_fname, convert_cmd, hdr_vals)
    write_nc(out_fname, header_info, dim_defs, var_defs, out_vars)

    print('Wrote to %s' % out_fname)


def write_nc(out_fname, header_info, dim_defs, var_defs, out_vars):
    # Write out the netCDF 
    with netCDF4.Dataset(out_fname, 'w') as nc:
        set_header(nc, header_info)
        for k, v in dim_defs.items():
            nc.createDimension(k, size=v)
        for k, v in out_vars.items():
            defs = var_defs[k]
            var = nc.createVariable(k, defs['type'], defs['dims'])
            var[:] = v
            """
            try:
                var[:] = v
            except Exception as e:
                print(e)
                os.remove(out_fname)
                moved_out_fn = os.path.join(date.strftime(helper.PROCESSING_ISSUE_DIR), os.path.basename(out_fname))
                os.makedirs(date.strftime(helper.PROCESSING_ISSUE_DIR), exist_ok=True)
                shutil.move(in_fname, moved_out_fn)
                return SHAPE_MISMATCH_ERROR_CODE
            """

            var.units = defs['units']
            var.long_name = defs['long_name']

    return 0


def calc_bearings(rlat, rlon, lats, lons, ref_ht):
    depth = -ref_ht * 1E3
    brng_deg = np.zeros(len(lats)) * np.nan
    pointB = wgs84.GeoPoint(latitude=rlat, longitude=rlon, z=depth, degrees=True)
    for ind, lat in enumerate(lats):
        lon = lons[ind]
        pointA = wgs84.GeoPoint(latitude=lat, longitude=lon, z=depth, degrees=True)
        p_AB_N = pointA.delta_to(pointB)  # note we want the bearing at point A
        brng_deg[ind] = p_AB_N.azimuth_deg 

    return brng_deg


def def_vars():
     # netCDF writer expects a series of variable definitions - here they are
    stdin_flt = {'type': 'f4', 'dims': 'npts'} 
    stdin_dbl = {'type': 'f8', 'dims': 'npts'} 
    var_defs = { 
        'mjd_start': dict({'units': 'days', 'long_name': 'Modified Julian Date (start of window)'}, **stdin_dbl),
        'mjd_end': dict({'units': 'days', 'long_name': 'Modified Julian Date (end of window)'}, **stdin_dbl),
        'vector.glat': dict({'units': 'deg.', 'long_name': 'Geographic Latitude'}, **stdin_flt),
        'vector.glon': dict({'units': 'deg.', 'long_name': 'Geographic Longitude'}, **stdin_flt),
        'vector.g_kvect': dict({'units': 'deg.', 'long_name': 'Geographic Azimuth angle'}, **stdin_flt),
        'vector.mlat': dict({'units': 'deg.', 'long_name': 'AACGM Latitude'}, **stdin_flt),
        'vector.mlon': dict({'units': 'deg.', 'long_name': 'AACGM Longitude'}, **stdin_flt),
        'vector.kvect': dict({'units': 'deg.', 'long_name': 'AACGM Azimuth angle'}, **stdin_flt),
        'vector.vel.median': dict({'units': 'm/s', 'long_name': 'Weighted mean velocity magnitude (+ve away from radar'}, **stdin_flt),
        'vector.vel.sd': dict({'units': 'm/s', 'long_name': 'Velocity standard deviation'}, **stdin_flt),
        'vector.pwr.median': dict({'units': 'dB', 'long_name': 'Weighted mean power'}, **stdin_flt),
        'vector.wdt.median': dict({'units': 'm/s', 'long_name': 'Weighted mean spectral width'}, **stdin_flt),
    }
    return var_defs



def set_header(rootgrp, header_info) :
    rootgrp.description = header_info['description']
    rootgrp.fitacf_source = header_info['fitacf_source']
    rootgrp.make_grid_call = header_info['make_grid call']
    rootgrp.history = header_info['history']
    rootgrp.fitacf_version = header_info['fitacf_version']
    rootgrp.lat = header_info['lat']
    rootgrp.lon = header_info['lon']
    rootgrp.alt = header_info['alt']
    rootgrp.boresight = header_info['boresight']
    return rootgrp


def get_hdr_vals(radar_info, fitVersion):
    hdr_vals = {
        'lat': radar_info['glat'],
        'lon': radar_info['glon'],
        'alt': radar_info['alt'],
        'boresight': radar_info['boresight'],
        'fitacf_version': fitVersion,
    }
    return hdr_vals


def def_header_info(in_fname, convert_cmd, hdr_vals):
    hdr = { 
        **{ 
        'description': 'Gridded, median-filtered "line-of-sight" ExB velocities and related parameters from SuperDARN. Ground scatter removed.',
        'fitacf_source': in_fname,
        'make_grid call': convert_cmd, 
        'history': 'Created on %s' % dt.datetime.now(),
        },
        **hdr_vals,
    }

    return hdr


def fit_to_grid(fit_fname, grid_fname, convert_cmd, 
        clobber=False,
):

    """ Run make_grid on the fitACF to create .grid file """

    # Check the input file exists
    if not os.path.isfile(fit_fname):
        print('Input file does not exist: %s' % fit_fname) 
        return 1
        
    # Check the input is big enough to be worth bothering with
    fn_info = os.stat(fit_fname)
    if fn_info.st_size < MIN_FITACF_FILE_SIZE:
        print('\n\n%s %1.1f MB\nFile too small - skipping' % (fit_fname, fn_info.st_size / 1E6))
        return 1

    if os.path.isfile(grid_fname):
        print("File exists: %s" % grid_fname)
        if clobber:
            print(' ... overwriting')
        else:
            print(' ... skipping fit -> grid conversion')
            return 0

    # Set up storage directory
    out_dir = os.path.dirname(grid_fname)
    os.makedirs(out_dir, exist_ok=True)

    # Run the executable
    os.system(convert_cmd % (fit_fname, grid_fname))

    return 0


def load_grid(grid_nc_fn, time):
    grid_data = nc_utils.ncread_vars(grid_nc_fn)     
    atts = nc_utils.load_nc(grid_nc_fn)     
    radar_loc = [atts.lat, atts.lon, atts.alt / 1E3]
    m_radar_loc = aacgmv2.convert_latlon_arr(*radar_loc, time, method_code="G2A")
    radar_loc += [l[0] for l in m_radar_loc]
    return grid_data, radar_loc 


def plot_grid_nc(grid_nc_fn, time, intvl_min=2):
    grid_data, radar_loc = load_grid(grid_nc_fn, time)
    grid_data_t = subsample_data(grid_data, time, intvl_min)

    vels = grid_data_t['vector.vel.median']
    lons = grid_data_t['vector.glon']
    lats = grid_data_t['vector.glat']
    brng_deg = grid_data_t['vector.g_kvect']

    brng_rad = np.deg2rad(brng_deg)
    plt.plot(lons, lats, '.k', markersize=5)
    plt.plot(radar_loc[1], radar_loc[0], '.r', markersize=20)
    plt.quiver(lons, lats, np.sin(brng_rad) * vels / 100, np.cos(brng_rad) * vels / 100)
    plt.xlabel('Lon. (deg)')
    plt.ylabel('Lat. (deg)')
    plt.title('ExB drift components from %s' % grid_nc_fn)
    plt.grid()
    plt.show()


def plot_grid(grid_fn, time):
    SDarn_read = pydarn.SuperDARNRead(grid_fn)
    grid_data = SDarn_read.read_grid()
    gridplot = pydarn.Grid.plot_grid(grid_data, start_time=time)
    plt.show()


def subsample_data(grid_data, time, intvl_min=2):
    delta_ts = []
    for t, mjd_s in enumerate(grid_data['mjd_start']):
        mjd_e = grid_data['mjd_end'][t]
        mjd = np.mean([mjd_s, mjd_e])
        datet = jdutil.jd_to_datetime(jdutil.mjd_to_jd(mjd))
        delta_ts.append((datet - time).total_seconds())
    delta_ts = np.abs(np.array(delta_ts))
    tidx = delta_ts < (intvl_min * 60 / 2)  # divide by 2 for plus/minus
    grid_data_t = {}
    for k, v in grid_data.items():
        grid_data_t[k] = v[tidx]
    return grid_data_t


if __name__ == '__main__':
    """
    stime = dt.datetime(2015, 3, 15)
    etime = dt.datetime(2015, 3, 18)
    fit_fn_fmt = '/project/superdarn/data/fitacf/%Y/%m/%Y%m%d.*.v3.0.fit'
    grid_dirn = '/project/superdarn/data/grid/%Y/%m/'
    out_dirn = '/project/superdarn/data/grid_nc/%Y/%m/'
    hdw_dat_dir = '/project/superdarn/software/rst/tables/superdarn/hdw/'
    clobber = False

    time = stime
    while time <= etime:
        grid_dirn_t = time.strftime(grid_dirn)
        out_dirn_t = time.strftime(out_dirn)
        os.makedirs(grid_dirn_t, exist_ok=True)
        os.makedirs(out_dirn_t, exist_ok=True)

        flist = glob.glob(time.strftime(fit_fn_fmt))
        for fit_fn in flist:
            fn_head = '.'.join(os.path.basename(fit_fn).split('.')[:-1])
            grid_fn = os.path.join(grid_dirn_t, fn_head + '.grid')
            out_fn = os.path.join(out_dirn_t, fn_head + '.grid.nc')
            convert_fit_to_grid_nc(time, fit_fn, grid_fn, out_fn, hdw_dat_dir, clobber=clobber)

        time += dt.timedelta(days=1)

    """ #one-off instance w. before/after plotting for sanity check 
    time = dt.datetime(2015, 3, 16, 1, 58)
    hdw_dat_dir = '/project/superdarn/software/rst/tables/superdarn/hdw/'
    fit_fname = '/project/superdarn/data/fitacf/2015/03/20150316.tig.v3.0.fit'
    grid_fname = '/project/superdarn/data/grid/2015/03/20150316.tig.v3.0.grid'
    out_fname = '/project/superdarn/data/grid_nc/2015/03/20150316.tig.v3.0.grid.nc'
    convert_fit_to_grid_nc(time, fit_fname, grid_fname, out_fname, hdw_dat_dir, clobber=True)

    plot_grid_nc(out_fname, time)
    plot_grid(grid_fname, time)












