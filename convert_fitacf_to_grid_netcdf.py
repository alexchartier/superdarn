import pydarn
import glob
import matplotlib.pyplot as plt
from matplotlib import ticker, cm, colors
import numpy as np
import jdutil
import helper
from datetime import datetime
import aacgmv2
import os
import sys
from sd_utils import get_radar_params, id_hdw_params_t, get_random_string, get_radar_list
import netCDF4
import nc_utils
import nvector as nv
wgs84 = nv.FrameE(name='WGS84')

MIN_FITACF_FILE_SIZE = 1E5 # bytes

# Global date variable
date = None
clobber = False

def main(date_string):
    print(f'Starting to convert {date_string} fitACFs to GRID netCDF')

    rstpath = os.getenv('RSTPATH')
    assert rstpath, 'RSTPATH environment variable needs to be set'
    
    global date
    date = datetime.strptime(date_string, '%Y%m%d')

    fitacf_dir = date.strftime(helper.FITACF_DIR_FMT)
    grid_dir = date.strftime(helper.GRID_DIR_FMT)
    grid_nc_dir = date.strftime(helper.GRID_NC_DIR_FMT)

    os.makedirs(grid_dir, exist_ok=True)
    os.makedirs(grid_nc_dir, exist_ok=True)

    hdw_dat_dir = os.getenv('SD_HDWPATH')

    # Get all fitACF3 files for the date (not including despeckled)
    # TODO: Confirm this gets all fitacf3 files but not despeck.fitacf3 files
    fitacf_files = glob(os.path.join(fitacf_dir, f"{date_string}.*[^despeck].fitacf3"))

    for fitacf_file in fitacf_files:

        fn_info = os.stat(fitacf_file)
        if fn_info.st_size < MIN_FITACF_FILE_SIZE:
            print('\n\n%s %1.1f MB\nFile too small - skipping' % (fitacf_file, fn_info.st_size / 1E6))
            continue

        fitacf_filename = os.path.basename(fitacf_file)
        grid_filename = fitacf_filename + ".nc"
        grid_file = os.path.join(grid_dir, grid_filename)
        grid_nc_filename = fitacf_filename + ".grid.nc"
        grid_nc_file = os.path.join(grid_nc_dir, grid_nc_filename)
        
        convert_fit_to_grid_nc(date, fitacf_file, grid_file, grid_nc_file, hdw_dat_dir, clobber=clobber)


def convert_fit_to_grid_nc(time, fit_fname, grid_fname, out_fname, hdw_dat_dir,
    fitVersion='3.0',
    ref_ht=300.,  # matches the RST operation
    convert_cmd='make_grid -xtd -chisham -ion -minsrng 500 -maxsrng 3000 %s > %s',
    clobber=False,
):
    """ Convert fitACF files to .grid (median-filtered & geolocated), then to netCDF """

    # Check if file exists
    if os.path.isfile(out_fname):
        if not clobber:
            print('Output file exists: %s - skipping' % out_fname)
            return 

    #print('Trying to produce %s' % grid_fname)

    # Run fit to GRID file conversion 
    status = fit_to_grid(fit_fname, grid_fname, convert_cmd, clobber=clobber)

    if status == 1:
        return 1

    #print('Trying to produce %s' % out_fname)

    # Check the grid file is big enough to be worth bothering with
    fn_info = os.stat(grid_fname)
    if fn_info.st_size < MIN_FITACF_FILE_SIZE:
        print('\n\n%s %1.1f MB\nFile too small - skipping' % (grid_fname, fn_info.st_size / 1E6))
        return 1

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
        out_vars['mjd_start'] = np.append(out_vars['mjd_start'], 
            jdutil.jd_to_mjd(jdutil.datetime_to_jd(stime)) * shape)
        out_vars['mjd_end'] = np.append(out_vars['mjd_end'], 
            jdutil.jd_to_mjd(jdutil.datetime_to_jd(etime)) * shape)
    
    # Check there's something to write
    if out_vars['mjd_start'] == []:
        print('No valid data in %s - not writing %s' % (grid_fname, out_fname))
        return

    # AACGM to geo
    mlat = out_vars['vector.mlat']
    mlon = out_vars['vector.mlon']
    [out_vars['vector.glat'], out_vars['vector.glon'], alt] = \
        aacgmv2.convert_latlon_arr(mlat, mlon, ref_ht, time, method_code="A2G")
    
    # geographic bearing
    out_vars['vector.g_kvect'] = calc_bearings(
        radar_info_t['glat'], radar_info_t['glon'], out_vars['vector.glat'], 
        out_vars['vector.glon'], ref_ht,
    )

    # geomagnetic bearing (to determine whether velocity oriented  towards/away array) 
    [r_mlat, r_mlon, _] = aacgmv2.convert_latlon_arr(
        radar_info_t['glat'], radar_info_t['glon'], radar_info_t['alt'], 
        stime, method_code="G2A",
    )
    maz = calc_bearings(r_mlat[0], r_mlon[0], mlat, mlon, ref_ht)
    delta_maz = angle_between(maz, out_vars['vector.kvect'])
    dirn = np.ones(maz.shape) 
    dirn[np.abs(delta_maz) > 90.] *= -1
    out_vars['vector.vel.dirn'] = dirn
    out_vars['vector.vel.median'] 

    # Write out to netCDF
    var_defs = def_vars()
    dim_defs = {
        'npts': out_vars['mjd_start'].shape[0],
    }
    hdr_vals = get_hdr_vals(radar_info_t, fitVersion)
    header_info = def_header_info(fit_fname, convert_cmd, hdr_vals)
    write_nc(out_fname, header_info, dim_defs, var_defs, out_vars)

    print('Wrote to %s' % out_fname)


def angle_between(x, y, deg=True):
    if deg:
        x = np.deg2rad(x) 
        y = np.deg2rad(y) 
    angle_rad = np.arctan2(np.sin(x-y), np.cos(x-y))

    if deg:
        return np.rad2deg(angle_rad)
    else:
        return angle_rad


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
    stdin_int = {'type': 'i1', 'dims': 'npts'} 
    var_defs = { 
        'mjd_start': dict({'units': 'days', 'long_name': 'Modified Julian Date (start of window)'}, **stdin_dbl),
        'mjd_end': dict({'units': 'days', 'long_name': 'Modified Julian Date (end of window)'}, **stdin_dbl),
        'vector.glat': dict({'units': 'deg.', 'long_name': 'Geographic Latitude'}, **stdin_flt),
        'vector.glon': dict({'units': 'deg.', 'long_name': 'Geographic Longitude'}, **stdin_flt),
        'vector.g_kvect': dict({'units': 'deg.', 'long_name': 'Geographic Azimuth angle'}, **stdin_flt),
        'vector.mlat': dict({'units': 'deg.', 'long_name': 'AACGM Latitude'}, **stdin_flt),
        'vector.mlon': dict({'units': 'deg.', 'long_name': 'AACGM Longitude'}, **stdin_flt),
        'vector.kvect': dict({'units': 'deg.', 'long_name': 'AACGM Azimuth angle'}, **stdin_flt),
        'vector.vel.median': dict({'units': 'm/s', 'long_name': 'Weighted mean velocity magnitude'}, **stdin_flt),
        'vector.vel.sd': dict({'units': 'm/s', 'long_name': 'Velocity standard deviation'}, **stdin_flt),
        'vector.vel.dirn': dict({'units': 'None', 'long_name': 'Velocity direction (+1 away from radar, -1 towards)'}, **stdin_int),
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
        'description': 'Gridded, median-filtered "line-of-sight" ExB velocities and related parameters from SuperDARN. Reference altitude of 300 km assumed. Ground scatter removed.',
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
    #print(convert_cmd % (fit_fname, grid_fname))
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
    if len(sys.argv) < 2:
        print("Usage: python3 convert_fitacf_to_netcdf.py YYYYMMDD")
        sys.exit(1)

    # Extract the day argument in 'YYYYMMDD' format
    date_string = sys.argv[1]

    # Check if the day argument is in the correct format
    if not date_string.isdigit() or len(date_string) != 8:
        print("Date argument must be in 'YYYYMMDD' format.")
        sys.exit(1)

    main(date_string)
