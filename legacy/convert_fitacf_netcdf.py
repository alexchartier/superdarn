#!/usr/bin/env python3
# coding: utf-8
"""
Converts fitACF files to netCDF files
"""
import os
import sys
from glob import glob
import shutil
import netCDF4
import jdutil
from datetime import datetime
import calendar
import numpy as np
from sd_utils import get_radar_params, id_hdw_params_t, get_random_string, get_radar_list
import pydarn
import radFov
import pickle
import helper
import concurrent.futures

MULTIPLE_BEAM_DEFS_ERROR_CODE = 1
SHAPE_MISMATCH_ERROR_CODE = 2
MIN_FITACF_FILE_SIZE = 1E5 # bytes
MAKE_FIT_VERSIONS = [3.0, 2.5]
FIT_EXT = '*.fit'
SKIP_EXISTING = True

# Global date variable
date = None

def main(date_string):
    print(f'\n{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - Starting to convert {date_string} fitACFs to netCDF')
    print("===================================================")
    rstpath = os.getenv('RSTPATH')
    assert rstpath, 'RSTPATH environment variable needs to be set'
    
    global date
    date = datetime.strptime(date_string, '%Y%m%d')
    helper.PROCESSING_ISSUE_DIR = '/Users/chartat1/Downloads/' 
    #fitacf_dir = date.strftime(helper.FITACF_DIR_FMT)
    #fitacf_nc_dir = date.strftime(helper.FIT_NC_DIR_FMT)
    fitacf_nc_dir = '/Users/chartat1/Downloads/'
    #os.makedirs(fitacf_nc_dir, exist_ok=True)
    fitacf_dir = '/Users/chartat1/data/superdarn/fitacf/'

    radar_info = get_radar_params(os.getenv('SD_HDWPATH'))

    # Get all fitACF files for the date
    fitacf2_files = glob(f"{os.path.join(fitacf_dir, date_string)}.*.fitacf2")
    fitacf3_despeck_files = glob(f"{os.path.join(fitacf_dir, date_string)}.*.despeck.fitacf3")
    fitacf_files = fitacf2_files + fitacf3_despeck_files

    for fitacf_file in fitacf_files:

        fn_info = os.stat(fitacf_file)
        if fn_info.st_size < MIN_FITACF_FILE_SIZE:
            print('\n\n%s %1.1f MB\nFile too small - skipping' % (fitacf_file, fn_info.st_size / 1E6))
            continue

        fitacf_filename = os.path.basename(fitacf_file)
        fitacf_nc_filename = fitacf_filename + ".nc"
        netcdf_file = os.path.join(fitacf_nc_dir, fitacf_nc_filename)

        radar_code = fitacf_filename.split('.')[1]
        radar_info_t = id_hdw_params_t(date, radar_info[radar_code])
        convert_fitacf_to_netcdf(date, fitacf_file, netcdf_file, radar_info_t)

    month = date.strftime('%m')
    multiBeamLogDir = date.strftime(helper.FIT_NET_LOG_DIR) + "/" + month
    multiBeamFile = '{0}/multi_beam_defs_{1}.log'.format(multiBeamLogDir, date.strftime('%Y%m'))
    # if os.path.exists(multiBeamFile):
    #     subject = '"Multiple Beam Definitions Found - {date}"'.format(date = date.strftime('%Y/%m'))
    #     body = 'Files with multiple beam definitions have been found. See details in {file}'.format(file = multiBeamFile)
    #     helper.send_email(subject, body)


def convert_fitacf_to_netcdf(date, in_fname, out_fname, radar_info):
    # print(f"Converting {in_fname}...")
    # fitACF to netCDF using davitpy FOV calc  - no dependence on fittotxt
    fit_version = "2.5" if in_fname.endswith("2") else "3.0 (despeckled)"
    out_vars, hdr_vals = convert_fitacf_data(date, in_fname, radar_info, fit_version)

    if out_vars == MULTIPLE_BEAM_DEFS_ERROR_CODE or out_vars == SHAPE_MISMATCH_ERROR_CODE:
        return out_vars

    var_defs = def_vars()
    dim_defs = {
        'npts': out_vars['mjd'].shape[0], 
    } 
    header_info = def_header_info(in_fname, hdr_vals)
    
    # Write out the netCDF 
    with netCDF4.Dataset(out_fname, 'w') as nc: 
        set_header(nc, header_info)
        for k, v in dim_defs.items():
            nc.createDimension(k, size=v)
        for k, v in out_vars.items():
            defs = var_defs[k]
            var = nc.createVariable(k, defs['type'], defs['dims'])
            try:
                var[:] = v
            except Exception as e:
                print(e)
                os.remove(out_fname)
                moved_out_fn = os.path.join(date.strftime(helper.PROCESSING_ISSUE_DIR), os.path.basename(in_fname))
                os.makedirs(date.strftime(helper.PROCESSING_ISSUE_DIR), exist_ok=True)
                shutil.move(in_fname, moved_out_fn)                
                return SHAPE_MISMATCH_ERROR_CODE

            var.units = defs['units']
            var.long_name = defs['long_name']
    
    print(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - Created {out_fname}')

    return 0


def convert_fitacf_data(date, in_fname, radar_info, fitVersion):
    try:
        day = in_fname.split('.')[0].split('/')[-1]
        month = day[-4:-2] 
        
        # Keep track of fitACF files that have multiple beam definitions in a
        # monthly log file
        multiBeamLogDir = date.strftime(helper.FIT_NET_LOG_DIR) + "/" + month
        multiBeamLogfile = '{0}/multi_beam_defs_{1}.log'.format(multiBeamLogDir, date.strftime("%Y%m"))
        
        # Store conversion info like returns outside FOV, missing slist, etc 
        # for each conversion
        conversionLogDir = '{dir}/{d}'.format(dir = multiBeamLogDir, d = day)
        fName = in_fname.split('/')[-1]
        conversionLogfile = '{dir}/{fit}_to_nc.log'.format(dir = conversionLogDir, fit = fName)

        # Define the name of the file holding the list of rawACFs used to 
        # create the fitACF
        #fitacfListFilename = '.'.join(in_fname.split('.')[:-1]) + '.fitacfList.txt'

        SDarn_read = pydarn.SuperDARNRead(in_fname)
        data = SDarn_read.read_fitacf()

        # add slice index for conversion back to DMAP format if necessary
        for ind, rec in enumerate(data):
            data[ind]['rec_id'] = np.ones_like(rec['v']) * ind

        bmdata = {
            'rsep': [],
            'frang': [],
        }
        for rec in data:
            for k, v in bmdata.items():
                bmdata[k].append(rec[k])
            if 'slist' in rec.keys():
                if radar_info['maxrg'] < rec['slist'].max():
                    radar_info['maxrg'] = rec['slist'].max() + 5
        
        for k, v in bmdata.items():
            val = np.unique(v)
            if len(val) > 1:        
                os.makedirs(conversionLogDir, exist_ok=True)
                os.makedirs(multiBeamLogDir, exist_ok=True)
                
                # Log the multiple beams error in the monthly mutli beam def log
                logText = f'{in_fname} has {len(val)} beam definitions - skipping file conversion.\n'
                print(logText)
                
                with open(multiBeamLogfile, "a+") as fp: 
                    fp.write(logText)

                # Log the multiple beams error in this fitACF's conversion log
                with open(conversionLogfile, "a+") as fp: 
                    fp.write(logText)

                return MULTIPLE_BEAM_DEFS_ERROR_CODE, MULTIPLE_BEAM_DEFS_ERROR_CODE
            
            bmdata[k] = int(val)

        # Define FOV
        fov = radFov.fov(
            frang=bmdata['frang'], rsep=bmdata['rsep'], site=None, nbeams=int(radar_info['maxbeams']),
            ngates=int(radar_info['maxrg']), bmsep=radar_info['beamsep'], recrise=radar_info['risetime'], siteLat=radar_info['glat'],
            siteLon=radar_info['glon'], siteBore=radar_info['boresight'], siteAlt=radar_info['alt'], siteYear=date.year,
            elevation=None, altitude=300., hop=None, model='IS',
            coords='geo', date_time=date, coord_alt=0., fov_dir='front',
        )

        # Define fields 
        short_flds = 'tfreq', 'noise.sky', 'cp',
        fov_flds = 'mjd', 'beam', 'range', 'lat', 'lon', 
        data_flds = 'p_l', 'v', 'v_e', 'w_l', 'w_l_e', 'gflg', 
        elv_flds = 'elv', 'elv_low', 'elv_high',

        # Figure out if we have elevation information
        elv_exists = True
        for rec in data:
            if 'elv' not in rec.keys():
                elv_exists = False
        if elv_exists:
            data_flds += elv_flds

        # Set up data storage
        out = {}
        for fld in (fov_flds + data_flds + short_flds):
            out[fld] = []
    
        # Run through each beam record and store 
        for rec in data:
            time = datetime(rec['time.yr'], rec['time.mo'], rec['time.dy'], rec['time.hr'], rec['time.mt'], rec['time.sc'])
            # slist is the list of range gates with backscatter
            if 'slist' not in rec.keys():
                os.makedirs(conversionLogDir, exist_ok=True)
                logText = 'Could not find slist in record {recordTime} - skipping\n'.format(recordTime = time.strftime('%Y-%m-%d %H:%M:%S'))
                with open(conversionLogfile, "a+") as fp: 
                    fp.write(logText)

                continue

            # Can't deal with returns outside of FOV
            if rec['slist'].max() >= fov.slantRCenter.shape[1]:
                os.makedirs(conversionLogDir, exist_ok=True)

                # Log returns outside of FOV
                logText = 'Record {recordTime} found to have a max slist of {maxSList} - skipping record/n'.format(recordTime = time.strftime('%Y-%m-%d %H:%M:%S'), maxSList = rec['slist'].max())
                with open(conversionLogfile, "a+") as fp: 
                    fp.write(logText)

                continue

            time = datetime(rec['time.yr'], rec['time.mo'], rec['time.dy'], rec['time.hr'], rec['time.mt'], rec['time.sc'])
            one_obj = np.ones(len(rec['slist'])) 
            mjd = jdutil.jd_to_mjd(jdutil.datetime_to_jd(time))
            bmnum = one_obj * rec['bmnum']
            fovi = fov.beams == rec['bmnum']
            out['mjd'] += (one_obj * mjd).tolist()
            out['beam'] += bmnum.tolist()
            out['range'] += fov.slantRCenter[fovi, rec['slist']].tolist()
            out['lat'] += fov.latCenter[fovi, rec['slist']].tolist()
            out['lon'] += fov.lonCenter[fovi, rec['slist']].tolist()

            for fld in data_flds:
                out[fld] += rec[fld].tolist()
            for fld in short_flds:  # expand out to size
                out[fld] += (one_obj * rec[fld]).tolist()

        # Convert to numpy arrays 
        for k, v in out.items():
            out[k] = np.array(v)

        # Calculate beam azimuths assuming 15 degrees elevation
        beam_off = radar_info['beamsep'] * (fov.beams - (radar_info['maxbeams'] - 1) / 2.0)
        el = 15.
        brng = np.zeros(beam_off.shape)
        for ind, beam_off_elzero in enumerate(beam_off):
            brng[ind] = radFov.calcAzOffBore(el, beam_off_elzero, fov_dir=fov.fov_dir) + radar_info['boresight']
        
        hdr = {
            'lat': radar_info['glat'],
            'lon': radar_info['glon'],
            'alt': radar_info['alt'],
            'rsep': bmdata['rsep'],
            'maxrg': radar_info['maxrg'],
            'bmsep': radar_info['beamsep'],
            'boresight': radar_info['boresight'],
            'beams': fov.beams,
            'brng_at_15deg_el': brng,
            'fitacf_version': fitVersion
        }
    except Exception as e:
        print(e)
        moved_out_fn = os.path.join(date.strftime(helper.PROCESSING_ISSUE_DIR), os.path.basename(in_fname))
        os.makedirs(date.strftime(helper.PROCESSING_ISSUE_DIR), exist_ok=True)
        shutil.move(in_fname, moved_out_fn)                
        return SHAPE_MISMATCH_ERROR_CODE, SHAPE_MISMATCH_ERROR_CODE

    return out, hdr


def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year,month)[1])
    return datetime(year, month, day, sourcedate.hour, sourcedate.minute, sourcedate.second)


def def_vars():
     # netCDF writer expects a series of variable definitions - here they are
    stdin_int = {'units': 'none', 'type': 'u1', 'dims': 'npts'} 
    stdin_int2 = {'units': 'none', 'type': 'u2', 'dims': 'npts'} 
    stdin_flt = {'type': 'f4', 'dims': 'npts'} 
    stdin_dbl = {'type': 'f8', 'dims': 'npts'} 
    var_defs = {
        'mjd': dict({'units': 'days', 'long_name': 'Modified Julian Date'}, **stdin_dbl),
        'beam': dict({'long_name': 'Beam #'}, **stdin_int),
        'range': dict({'units': 'km','long_name': 'Slant range'}, **stdin_int2),
        'lat': dict({'units': 'deg.', 'long_name': 'Geographic Latitude'}, **stdin_flt),
        'lon': dict({'units': 'deg.', 'long_name': 'Geographic Longitude'}, **stdin_flt),
        'p_l': dict({'units': 'dB', 'long_name': 'Lambda fit SNR'}, **stdin_flt),
        'v': dict({'units': 'm/s', 'long_name': 'LOS Vel. (+v = towards the radar)'}, **stdin_flt),
        'v_e': dict({'units': 'm/s', 'long_name': 'LOS Vel. error'}, **stdin_flt),
        'gflg': dict({'long_name': 'Ground scatter flag for ACF, 1 - ground scatter, 0 - other scatter'}, **stdin_int),
        'elv': dict({'units': 'degrees', 'long_name': 'Elevation angle estimate'}, **stdin_flt),
        'elv_low': dict({'units': 'degrees', 'long_name': 'Lowest elevation angle estimate'}, **stdin_flt),
        'elv_high': dict({'units': 'degrees', 'long_name': 'Highest elevation angle estimate'}, **stdin_flt),
        'tfreq': dict({'units': 'kHz','long_name': 'Transmit freq'}, **stdin_int2),
        'noise.sky': dict({'units': 'none','long_name': 'Sky noise'}, **stdin_flt),
        'cp': dict({'units': 'none','long_name': 'Control program ID'}, **stdin_int2),
        'rec_id': dict({'units': 'none','long_name': 'DMAP record ID'}, **stdin_int2),
    }   

    return var_defs


def set_header(rootgrp, header_info) :
    rootgrp.description = header_info['description']
    rootgrp.fitacf_source = header_info['fitacf_source']
    rootgrp.history = header_info['history']
    rootgrp.fitacf_version = header_info['fitacf_version']
    rootgrp.lat = header_info['lat']
    rootgrp.lon = header_info['lon']
    rootgrp.alt = header_info['alt']
    rootgrp.rsep_km = header_info['rsep']
    rootgrp.maxrangegate = header_info['maxrg']
    rootgrp.bmsep = header_info['bmsep']
    rootgrp.boresight = header_info['boresight']
    rootgrp.beams = header_info['beams']
    rootgrp.brng_at_15deg_el = header_info['brng_at_15deg_el']
    return rootgrp


def def_header_info(in_fname, hdr_vals):
    hdr = {
        **{
        'description': 'Geolocated line-of-sight velocities and related parameters from SuperDARN fitACF',
        'fitacf_source': in_fname,
        'history': 'Created on %s' % datetime.now(),
        }, 
        **hdr_vals,
    }

    return hdr


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

