"""
map_to_nc.py

Convert map to netCDF files

Terms:
    .map - Hemispheric convection map
    .nc  - netCDF output file (self-describing platform-independent file suitable 
           for sharing with users outside the community)
            Daily, one per hemisphere
"""  
# !/usr/bin/env python
import os
import sys
import numpy as np
import nvector as nv
import pydarn
import datetime as dt
import aacgmv2
import netCDF4
    
__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2021, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"


def main(
    in_filename = '/project/superdarn/data/map/2014/05/20140524.map',
    out_filename = '/homes/superdarn/output.nc',
    AtoGHeight = 300
):
    data = get_data(in_filename, AtoGHeight)
    attributes = get_attributes()
    save_data(data, attributes, AtoGHeight, in_filename, out_filename)


def save_data(data, attributes, AtoGHeight, in_filename, out_filename):    
    print('Saving data to %s' % out_filename)
    with netCDF4.Dataset(out_filename, 'w') as nc: 
        set_header(nc, AtoGHeight, in_filename)

        nc.createDimension('numPoints', len(data['times']))
        for k, v in data.items():
            var_attributes = attributes[k]
            if k == 'times':
                #NOTE(ATC) F4 doesn't have 1-sec precision for 1970 timestamps, need to use i4
                var = nc.createVariable(k, 'i4', 'numPoints')  
            else:
                var = nc.createVariable(k, 'f4', 'numPoints')
            var[:] = v
            var.units = var_attributes['units']
            var.long_name = var_attributes['long_name']


def get_data(in_filename, AtoGHeight):
    print('Processing %s' % in_filename)
    map_data = pydarn.SuperDARNRead(in_filename).read_map()
    latMagVector = []
    lonMagVector = []
    azimuthMagVector = []

    latGeoVector = []
    lonGeoVector = []
    azimuthGeoVector = []

    velocityVector = []
    sdVector = []
    timeVector = []
    
    for entry in map_data: 
        numPoints = len(entry['vector.vel.median'])
        t = dt.datetime(
            int(entry['start.year']), int(entry['start.month']), int(entry['start.day']),
            int(entry['start.hour']), int(entry['start.minute']), int(entry['start.second']),
        )  
        # Convert time to seconds since 1970-01-01 00:00
        times = [t.timestamp()] * numPoints
        timeVector.append(times)
        azM = entry['vector.kvect']
        
        velocityVector.append(entry['vector.vel.median'])
        sdVector.append(entry['vector.vel.sd'])
        latMagVector.append(entry['vector.mlat'])
        lonMagVector.append(entry['vector.mlon'])
        azimuthMagVector.append(azM)    
        
        latG, lonG, heightG = aacgmv2.convert_latlon_arr(
            entry['vector.mlat'], entry['vector.mlon'], AtoGHeight, t, method_code='A2G',
        )
        latGeoVector.append(latG)
        lonGeoVector.append(lonG)
        
        azG = convert_azm_aacgm2geo(azM, latG, lonG, t, refAlt=AtoGHeight)
        azimuthGeoVector.append(azG)
    
    data = {}
    data['times'] = np.array(np.concatenate(timeVector))
    data['mLat'] = np.array(np.concatenate(latMagVector))
    data['mLon'] = np.array(np.concatenate(lonMagVector))
    data['mAz'] = np.array(np.concatenate(azimuthMagVector))
    data['gAz'] = np.array(np.concatenate(azimuthGeoVector))
    data['gLat'] = np.array(np.concatenate(latGeoVector))
    data['gLon'] = np.array(np.concatenate(lonGeoVector))
    data['vel'] = np.array(np.concatenate(velocityVector))
    data['sd'] = np.array(np.concatenate(sdVector))
    
    return data
    

def set_header(ncObject, in_fname, conversionAltitude):
    
    ncObject.description = 'Hemispherical gridded velocity vectors'
    ncObject.source = in_fname
    ncObject.history = 'Created on %s' % dt.datetime.now()
    ncObject.aacgmConversionAltitude = '%s km' % conversionAltitude 
    # TODO: add IMF data to header 
    
    return ncObject


def get_attributes():
    
    attributes = {
        'times': dict({'units': 'seconds since 1970-01-01 00:00 UTC', 'long_name': 'Epoch Time'}),
        'mLat': dict({'units':'degrees', 'long_name': 'Magnetic Latitude'}),
        'mLon': dict({'units': 'degrees','long_name': 'Magnetic Longitude'}),
        'mAz': dict({'units': 'degrees', 'long_name': 'Magnetic Azimuth'}),
        'gLat': dict({'units': 'degrees', 'long_name': 'Geographic Latitude'}),
        'gLon': dict({'units': 'degrees', 'long_name': 'Geographic Longitude'}),
        'gAz': dict({'units': 'degrees', 'long_name': 'Geographic Azimuth'}),
        'vel': dict({'units': 'm/s', 'long_name': 'Velocity'}),
        'sd': dict({'units': 'm/s', 'long_name': 'Velocity Standard Deviation'}),
    }   
    return attributes


def convert_azm_aacgm2geo(azM, latG, lonG, dTime, refAlt=300):
    # Convert azimuths from AACGM to geodetic

    refZ = -refAlt * 1E3  # nvector uses z = height in metres down
    wgs84 = nv.FrameE(name='WGS84')
    nPole = aacgmv2.convert_latlon(90, 0, refAlt, dTime, method_code="A2G")

    geoAzimuths = np.ones(azM.shape) * np.nan

    for ind, mAzm in enumerate(azM):

        pointA = wgs84.GeoPoint(
            latitude=latG[ind], longitude=lonG[ind], z=refZ, degrees=True,
        )
        pointPole = wgs84.GeoPoint(
            latitude=nPole[0], longitude=nPole[1], z=refZ, degrees=True,
        )

        p_AB_N = pointA.delta_to(pointPole)
        azimuth_offset = p_AB_N.azimuth_deg[0]
        geoAzimuths[ind] = mAzm + azimuth_offset

    geoAzimuths[geoAzimuths > 180] -= 360.
    geoAzimuths[geoAzimuths < -180] += 360.

    return geoAzimuths



if __name__ == '__main__':
    args = sys.argv
    
    assert len(args) >= 3, 'Should have 2-3 arguments:\n' + \
        ' -  Input filename\n' + \
        ' -  Output filename\n' + \
        ' -  AACGM to Geo conversion height (km)\n' + \
        '\ne.g.: python3 map_to_nc.py  ' + \
        '/project/superdarn/data/map/2014/05/20140524.map  ' + \
        '/homes/superdarn/output.nc  300'
    
    in_fname = args[1]
    out_fname = args[2]
    if len(args) == 4:
        args[3] = float(args[3])
    
    main(*args[1:])









