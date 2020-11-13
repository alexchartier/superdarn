# -*- coding: utf-8 -*-

"""
Created on Sat Jun 13 19:48:06 2020

@author: Devasena & Alex

flag definitions:
    0 - F
    1 - ground
    2 - coll
    3 - other
"""

import numpy as np
from netCDF4 import Dataset
import nc_utils
import math
import os
import statistics
import pdb


def filter_sd_file(in_fname):
    data = nc_utils.ncread_vars(in_fname)    
    return flag_data(data)
    
    
def flag_data(data):
    filteredData = flag_interference(data)
    removedScatter = scatter_filter(filteredData)

    for key, value in removedScatter.items():
        removedScatter[key] = np.array(value)

    return removedScatter


#flag any interference and mark as 3 "other"
def flag_interference(data):
    
    """
    Median Filter:
        Remove data that is more than 800 m/s away from the median velocity of the beam
    Working Criteria to Remove a Beam:
        velocity standard deviation above 435
    """
    
    uniqueTimes = np.unique(data["mjd"])
    
    for index in range(len(uniqueTimes)):
        fsFlag = data["gs"] == 0
        timeIndex = data["mjd"] == uniqueTimes[index]
        fsBeamsTimed = list(data["bm"][timeIndex & fsFlag])
        
        for beam in range(16):
            beamFlag = data["bm"] == beam
            fsFlag = data["gs"] == 0
                   
            if len(data["vel"][timeIndex & fsFlag & beamFlag]) != 0:
                beamVelMedian = statistics.median(data["vel"][timeIndex & beamFlag & fsFlag])
                medianFlag1 = data["vel"] >= beamVelMedian + 800          
                medianFlag2 = data["vel"] <= beamVelMedian - 800
                data["gs"][(timeIndex & beamFlag & fsFlag) & (medianFlag1 | medianFlag2)] = 3
                
            fsFlag = data["gs"] == 0
            beamVelStDev = np.std(data["vel"][timeIndex & beamFlag])
            
            if beamVelStDev >= 435:
                data["gs"][timeIndex & beamFlag] = 3

    return data

#removes scatter / outlier contamination
def scatter_filter(data): 
    
    """
    Ground Scatter removed via min velocity of 80 m/s
    E region Scatter removed via min range of 400 km
    
    """
    fsFlag = data["gs"] == 0
    gsList = list(data["gs"])
    
    minVelFlag1 = data["vel"] <= 80 
    minVelFlag2 = data["vel"] >= -80
    minRangeFlag = data["km"] <= 500
    
    data["gs"][minVelFlag1 & minVelFlag2 & fsFlag] = 1
    data["gs"][fsFlag & minRangeFlag] = 2    
 
    gsList = list(data["gs"])

    return data


#smooths data with boxcar averages
def median_filter(data):
    
    variables = ["geolon", "geolat", "mjd", "vel", "bm", "km", "geoazm"]
    fsFlag = data["gs"] == 0
    fsData = {}
    gateSize = 150
    
    # isolating the F scatter data
    for var in variables:
        fsData[var] = data[var][fsFlag]
        
    uniqueTimes = np.unique(fsData["mjd"])   
    avgFsData = {"geolon":[], "geolat":[], "vel":[], "geoazm":[]}
    
    print('# of After 0s: %i' % gsList.count(0))
    print('# of After 3s: %i' % gsList.count(3))

    
    return data
