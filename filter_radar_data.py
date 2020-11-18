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
import pdb

VEL_RANGE = 800
VEL_STDEV = 435
MIN_VEL = 80
MIN_RANGE = 500

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
        
        for beam in range(data['bm'].max() + 1):
            beamFlag = data["bm"] == beam
            fsFlag = data["gs"] == 0

            combInd = timeIndex & fsFlag & beamFlag
            if len(data["vel"][combInd]) != 0:
                beamVelMedian = np.median(data["vel"][combInd])
                medianFlag1 = data["vel"] >= beamVelMedian + VEL_RANGE          
                medianFlag2 = data["vel"] <= beamVelMedian - VEL_RANGE
                outlierFlag = combInd & (medianFlag1 | medianFlag2) 
                if np.sum(outlierFlag) > 0:
                    #print('Flagging %i outliers' % np.sum(outlierFlag))
                    data["gs"][outlierFlag] = 3
                
            fsFlag = data["gs"] == 0
            beamVelStDev = np.std(data["vel"][timeIndex & beamFlag])
            
            if beamVelStDev >= VEL_STDEV:
                #print('Flagging beam %i for high Std. Dev' % beam)
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
    
    minVelFlag1 = data["vel"] <= MIN_VEL 
    minVelFlag2 = data["vel"] >= -MIN_VEL
    minRangeFlag = data["km"] <= MIN_RANGE
    
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

    
    return data
