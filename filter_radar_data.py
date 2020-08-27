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
import julian as jd
import matplotlib.pyplot as plt
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
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
    smoothedData = median_filter(removedScatter)

    for key, value in smoothedData.items():
        smoothedData[key] = np.array(value)

    return smoothedData


def flag_interference(data):
    """
    Flag any interference and mark as 3 "other"
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
            # Flag velocities > 800 m/s out from the beam median   
            beamFlag = data["bm"] == beam
            fsFlag = data["gs"] == 0
            timeBeamFsFlag = timeIndex & beamFlag & fsFlag 
            if len(data["vel"][timeBeamFsFlag]) != 0:
                beamVelMedian = statistics.median(data["vel"][timeBeamFsFlag])
                medianFlag1 = data["vel"] >= beamVelMedian + 800          
                medianFlag2 = data["vel"] <= beamVelMedian - 800
                data["gs"][timeBeamFsFlag & (medianFlag1 | medianFlag2)] = 3
            
            # Flag beams with too large a standard deviation    
            fsFlag = data["gs"] == 0
            beamVelStDev = np.std(data["vel"][timeIndex & beamFlag])
            if beamVelStDev >= 435:
                data["gs"][timeIndex & beamFlag] = 3

    return data


def scatter_filter(data): 
    
    """
    Ground Scatter flagged via min velocity of 50 m/s
    E region Scatter flagged via min range of 400 km
    
    """
    fsFlag = data["gs"] == 0
    gsList = list(data["gs"])
    
    minVelFlag1 = data["vel"] <= 50 
    minVelFlag2 = data["vel"] >= -50
    minRangeFlag = data["km"] <= 400
    
    data["gs"][minVelFlag1 & minVelFlag2 & fsFlag] = 1
    data["gs"][fsFlag & minRangeFlag] = 2    
 
    gsList = list(data["gs"])

    return data


def median_filter(data):
    """
    smooths data with boxcar averages
    """
    
    variables = ["geolon", "geolat", "mjd", "vel", "bm", "km"]
    fsFlag = data["gs"] == 0
    fsData = {}
    gateSize = 150
    
    # isolating the F scatter data
    for var in variables:
        fsData[var] = data[var][fsFlag]
        
    uniqueTimes = np.unique(fsData["mjd"])   
    avgFsData = {"geolon":[], "geolat":[], "mjd":[], "vel":[]}
    
    print("# of timecodes: %i" % len(uniqueTimes))
    
    #parsing through timecodes
    for index in range(len(uniqueTimes)):
        currentTime = uniqueTimes[index]
        timeIndex = fsData["mjd"] == currentTime
        
        # parsing through beams
        for beam in range(16):
            beamFlag = fsData["bm"] == beam
            
            if len(fsData["geolon"][timeIndex & beamFlag]) != 0:
            
                minKm = min(fsData["km"][timeIndex & beamFlag])
                maxKm = max(fsData["km"][timeIndex & beamFlag])
                rangeKm = maxKm - minKm
                
                # parsing through the range gates and averaging the data
                for gate in range(math.ceil(rangeKm / gateSize) + 1):
                    gateFlag1 = fsData["km"] >= minKm + gate * gateSize
                    gateFlag2 = fsData["km"] < minKm + gate * gateSize + gateSize

                    idx = [timeIndex & beamFlag & gateFlag1 & gateFlag2]
                    
                    gatedLons = fsData["geolon"][idx]              
                    gatedLats = fsData["geolat"][idx] 
                    gatedVels = fsData["vel"][idx] 
                    
                    # adding averaged data to the new dictionary
                    if len(gatedLons) != 0:
                        avgFsData["geolon"].append(np.average(gatedLons))
                        avgFsData["geolat"].append(np.average(gatedLats))
                        avgFsData["vel"].append(np.average(gatedVels))
                        avgFsData["mjd"].append(currentTime)

    return avgFsData    


