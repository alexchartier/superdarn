# -*- coding: utf-8 -*-

"""
Created on Sat Jun 13 19:48:06 2020
@author: Devasena

"""

import numpy as np
from netCDF4 import Dataset
import julian as jd
import matplotlib.pyplot as plt
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import math
import datetime as dt
from scipy.interpolate import griddata
import statistics
import pickle


def main():
    in_fname_fmt = "data/sami_ampere_weimer/sami3_utheta_uphi_300_%m%d.nc"
    time = dt.datetime(2014, 5, 22, 21, 56)
    radar_fname_fmt = '%Y%m%d.inv.nc'

    modData = load_data(time.strftime(in_fname_fmt), ["lat0", "lon0", "utheta", "uphi", "time"])
    radarData = load_data(time.strftime(radar_fname_fmt), ["vel", "km", "bm", "geolon", "geolat",
                                                           "mjd", "gs", "vel_e", "vel_n", "geoazm"])
    
    #interference = flag_interference(radarData)
    #scatter = scatter_filter(interference)
    #boxcar = median_filter(scatter)
    
    pickle_in = open("20140522_pyk.pickle", "rb")
    boxcar = pickle.load(pickle_in)
    
    modNvel, modEvel, index, hrind = interp_model_to_obs(modData, boxcar, time)
    radVel= plot_data(modData, boxcar, time, index, hrind)

#load data out of netCDF file and into python dictionary

def load_data(in_fname, var_names):

    #extracting the data
    fileHandle = Dataset(in_fname, mode="r+")
    print(fileHandle)
    print(fileHandle.variables)    
    
    data = {}

    #putting data into the dictionary
    for var_n in var_names:
        data[var_n] = {
            'units': fileHandle.variables[var_n].units,
            'vals': fileHandle.variables[var_n][...],
        }

    fileHandle.close()
    
    return data


def flag_interference(data):
    
    """
    Median Filter:
        Remove data that is more than 800 m/s away from the median velocity of the beam
    Working Criteria to Remove a Beam:
        velocity standard deviation above 435
    """
    
    uniqueTimes = np.unique(data["mjd"]['vals'])
    
    for index in range(len(uniqueTimes)):
        fsFlag = data["gs"]["vals"] == 0
        timeIndex = data["mjd"]['vals'] == uniqueTimes[index]
        fsBeamsTimed = list(data["bm"]['vals'][timeIndex & fsFlag])
        
        for beam in range(16):
            beamFlag = data["bm"]['vals'] == beam
            fsFlag = data["gs"]["vals"] == 0
                   
            if len(data["vel"]["vals"][timeIndex & fsFlag & beamFlag]) != 0:
                beamVelMedian = statistics.median(data["vel"]["vals"][timeIndex & beamFlag & fsFlag])
                medianFlag1 = data["vel"]["vals"] >= beamVelMedian + 800          
                medianFlag2 = data["vel"]["vals"] <= beamVelMedian - 800
                data["gs"]["vals"][(timeIndex & beamFlag & fsFlag) & (medianFlag1 | medianFlag2)] = 3
                
            fsFlag = data["gs"]["vals"] == 0
            beamVelStDev = np.std(data["vel"]['vals'][timeIndex & beamFlag])
            
            if beamVelStDev >= 435:
                data["gs"]['vals'][timeIndex & beamFlag] = 3

    return data

#removes scatter / outlier contamination
def scatter_filter(data): 
    
    """
    Ground Scatter removed via min velocity of 30 m/s
    E region Scatter removed via min range of 400 km
    
    """
    fsFlag = data["gs"]["vals"] == 0
    gsList = list(data["gs"]["vals"])
    
    print('# of Before 0s: %i' % gsList.count(0))
    print('# of Before 3s: %i' % gsList.count(3))
    print()
    
    minVelFlag1 = data["vel"]["vals"] <= 30 
    minVelFlag2 = data["vel"]["vals"] >= -30
    minRangeFlag = data["km"]["vals"] <= 400
    
    data["gs"]["vals"][minVelFlag1 & minVelFlag2 & fsFlag] = 1
    data["gs"]["vals"][fsFlag & minRangeFlag] = 2    
 
    gsList = list(data["gs"]["vals"])
    
    print('# of After 0s: %i' % gsList.count(0))
    print('# of After 3s: %i' % gsList.count(3))
    return data

#smooths data with boxcar averages
def median_filter(data):
    
    variables = ["geolon", "geolat", "mjd", "vel", "bm", "km", "vel_e", "vel_n", "geoazm"]
    fsFlag = data["gs"]["vals"] == 0
    fsData = {}
    gateSize = 150
    
    # isolating the F scatter data
    for var in variables:
        fsData[var] = data[var]["vals"][fsFlag]
        
    uniqueTimes = np.unique(fsData["mjd"])   
    avgFsData = {"geolon":[], "geolat":[], "mjd":[], 
                 "vel":[], "vel_e":[], "vel_n":[], "geoazm":[]}
    
    print("# of timecodes:" + str(len(uniqueTimes)))
    
    
    #parsing through timecodes
    for index in range(len(uniqueTimes)):
        currentTime = uniqueTimes[index]
        timeIndex = fsData["mjd"] == currentTime
        
        #parsing through beams
        for beam in range(16):
            beamFlag = fsData["bm"] == beam
            
            if (len(fsData["geolon"][timeIndex & beamFlag])) != 0:
            
                minKm = min(fsData["km"][timeIndex & beamFlag])
                maxKm = max(fsData["km"][timeIndex & beamFlag])
                rangeKm = maxKm- minKm
                
                #parsing through the range gates and averaging the data
                for gate in range(math.ceil(rangeKm/gateSize) + 1):
                    gateFlag1 = fsData["km"] >= minKm + gate *gateSize
                    gateFlag2 = fsData["km"] < minKm + gate*gateSize + gateSize
  
                    gatedLons = fsData["geolon"][timeIndex & beamFlag & gateFlag1 & gateFlag2]                                     
                    gatedLats = fsData["geolat"][timeIndex & beamFlag & gateFlag1 & gateFlag2] 
                    gatedVels = fsData["vel"][timeIndex & beamFlag & gateFlag1 & gateFlag2]
                    
                    gatedEVels = fsData["vel_e"][timeIndex & beamFlag & gateFlag1 & gateFlag2]
                    gatedNVels = fsData["vel_n"][timeIndex & beamFlag & gateFlag1 & gateFlag2]
                    gatedDegs = fsData["geoazm"][timeIndex & beamFlag & gateFlag1 & gateFlag2]
                    
                    
                    #adding averaged data to the new dictionary
                    if (len(gatedLons) != 0):
                        avgFsData["geolon"].append(np.average(gatedLons))
                        avgFsData["geolat"].append(np.average(gatedLats))
                        
                        avgFsData["vel"].append(np.average(gatedVels))
                        avgFsData["vel_e"].append(np.average(gatedEVels))
                        avgFsData["vel_n"].append(np.average(gatedNVels))
                        
                        avgFsData["geoazm"].append(np.average(gatedDegs))
                        avgFsData["mjd"].append(currentTime)
                    
    print(len(avgFsData["geolon"]))
    print(len(np.unique(avgFsData["mjd"])))
    
    print(min(avgFsData["vel"]))
    print(max(avgFsData["vel"]))
    
    print("Longitudes: " + str(min(avgFsData["geolon"])) + ", " + str(max(avgFsData["geolon"])))
    print("Latitudes: " + str(min(avgFsData["geolat"])) + ", " + str(max(avgFsData["geolat"])))
    
    pickle_out = open("20140522_pyk.pickle", "wb")
    pickle.dump(avgFsData, pickle_out)
    pickle_out.close()
    
    return avgFsData    

def plot_data(modData, radarData, time, index, hrind, axext=[-140, 6, 68, 88]):
    
    for key, value in radarData.items():
        radarData[key] = np.array(value)

    uniqueTimes = np.unique(radarData["mjd"])
    
    timeIndex = radarData["mjd"] == uniqueTimes[index]

    fsLatTimed = radarData["geolat"][timeIndex]
    fsLonTimed = radarData["geolon"][timeIndex]
    fsVelTimed = radarData["vel"][timeIndex]
    
    fsVelETimed = radarData["vel_e"][timeIndex]
    fsVelNTimed = radarData["vel_n"][timeIndex]
    fsDegTimed = radarData["geoazm"][timeIndex]
    
    vertical = np.cos(np.deg2rad(fsDegTimed)) * fsVelTimed
    horizontal = np.sin(np.deg2rad(fsDegTimed)) * fsVelTimed

    # set up the plot 
    ax = plt.axes(projection=ccrs.EquidistantConic(standard_parallels = (90,90)))
    ax.coastlines()
    ax.gridlines()
    ax.set_extent(axext, ccrs.PlateCarree())
    
    
    plt.quiver(
    modData["lon0"]["vals"].flatten(), modData["lat0"]["vals"].flatten(), 
    modData["uphi"]["vals"][hrind,:,:].flatten(), 
    modData["utheta"]["vals"][hrind,:,:].flatten(), color = "gray",
    transform=ccrs.PlateCarree(), regrid_shape= 24, width=.005, 
    )
    
    # make the plot
    plt.quiver(fsLonTimed, fsLatTimed, fsVelETimed, fsVelNTimed, fsVelTimed, cmap="Spectral_r", 
                transform=ccrs.PlateCarree(),
                )
    plt.plot(-133.772, 68.414, color = "red", marker = "x", transform = ccrs.PlateCarree())
    
    clb = plt.colorbar()
    clb.ax.set_title("Velocity")
    clb.set_label("m/s", rotation=270)
    
    
    plt.suptitle(time.strftime("SAMI/AMPERE ExB drift vels at %H:%M UT on %d %b %Y"))
    plt.savefig("Inuvik_NE.png", dpi = 300)
    plt.show()
    plt.close()
    
    return fsVelTimed
    
    
def interp_model_to_obs(modData, radarData, time):
    
    hour = time.hour + time.minute / 60
    tdiffs = np.abs(modData["time"]["vals"] - hour)
    hrind = tdiffs == np.min(tdiffs) 

    if len(hrind) == 2:
        hrind == hrind[0]
    
    for key, value in radarData.items():
        radarData[key] = np.array(value)
    
    timeInts = []
    uniqueTimes = np.unique(radarData["mjd"])
    
    for element in uniqueTimes:
        readableRadarTime = jd.from_jd(element, fmt="mjd")
        timeInts.append([int(readableRadarTime.strftime('%H')),
                         int(readableRadarTime.strftime('%M'))])
    
    index = timeInts.index([time.hour, time.minute])
    timeIndex = radarData["mjd"] == uniqueTimes[index]
    
    #print(timeInts)
    
    lats = modData["lat0"]["vals"].flatten()
    lons = modData["lon0"]["vals"].flatten()
    lons[lons > 180] = lons[lons > 180] - 360
    
    nvals = modData["utheta"]["vals"][hrind,:,:].flatten()
    evals = modData["uphi"]["vals"][hrind,:,:].flatten()
    
    radarLats = radarData["geolat"][timeIndex]
    radarLons = radarData["geolon"][timeIndex]
    
    nvel = griddata(np.array([lons, lats]).T, nvals, (radarLons, radarLats))
    evel = griddata(np.array([lons, lats]).T, evals, (radarLons, radarLats))

    
    #print(nvel)
    #print(evel)
    
    return nvel, evel, index, hrind

if __name__ == '__main__':

    main()















