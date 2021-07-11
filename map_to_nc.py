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
    with netCDF4.Dataset(out_filename, 'w') as nc: 
        set_header(nc, AtoGHeight, in_filename)

        mapData = nc.createGroup('Map_data')
        mapData.createDimension('numPoints', len(data['times']))
        for k, v in data.items():
            var_attributes = attributes[k]
            var = mapData.createVariable(k, 'f4', 'numPoints')
            var[:] = v
            var.units = var_attributes['units']
            var.long_name = var_attributes['long_name']

        #nc.close() 


def get_data(in_filename, AtoGHeight):
    map_data = pydarn.SuperDARNRead(in_filename).read_map()

    latMagVector        = []
    lonMagVector        = []
    azimuthMagVector    = []

    latGeoVector        = []
    lonGeoVector        = []
    azimuthGeoVector    = []

    velocityVector      = []
    timeVector          = []

    for entry in map_data: 
        numPoints = len(entry['vector.vel.median'])
        t = dt.datetime(
            int(entry['start.year']), int(entry['start.month']), int(entry['start.day']),
            int(entry['start.hour']), int(entry['start.minute']), int(entry['start.second']),
        )  
        # Convert time to seconds since 1970-01-01 00:00
        times = [t.timestamp()] * numPoints

        timeVector.append(times)
        velocityVector.append(entry['vector.vel.median'])
        latMagVector.append(entry['vector.mlat'])
        lonMagVector.append(entry['vector.mlon'])
        azimuthMagVector.append(entry['vector.kvect'])    
        
        latG, lonG, heightG = aacgmv2.convert_latlon_arr(entry['vector.mlat'], entry['vector.mlon'], AtoGHeight, t, method_code='A2G')
        latGeoVector.append(latG)
        lonGeoVector.append(lonG)
        
        # TODO: convert mAz to gAz
    
    fields = 'times','mLat','mLon','mAz','gLat','gLon','vel'

    data = {}
    for field in fields:
        data[field] = []

    data['times']   = np.array(np.concatenate(timeVector))
    data['mLat']    = np.array(np.concatenate(latMagVector))
    data['mLon']    = np.array(np.concatenate(lonMagVector))
    data['mAz']     = np.array(np.concatenate(azimuthMagVector))
    data['gLat']    = np.array(np.concatenate(latGeoVector))
    data['gLon']    = np.array(np.concatenate(lonGeoVector))
    data['vel']     = np.array(np.concatenate(velocityVector))
    
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
        'vel': dict({'units': 'm/s', 'long_name': 'Velocity Scalar'}),
    }   
    return attributes


if __name__ == '__main__':
    args = sys.argv
    
    assert len(args) == 4, 'Should have 3 arguments:\n' + \
        ' -  Input filename\n' + \
        ' -  Output filename\n' + \
        ' -  AACGM to Geo conversion height (km)\n' + \
        '\ne.g.: python3 map_to_nc.py  ' + \
        '/project/superdarn/data/map/2014/05/20140524.map  ' + \
        '/homes/superdarn/output.nc  300'
    
    in_fname = args[1]
    out_fname = args[2]
    AtoGHeight = float(args[3])
    
    main(in_fname, out_fname, AtoGHeight)









