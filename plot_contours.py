#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jul  9 17:41:37 2021

@author: sitardp1
"""
import proc_dmsp
import nc_utils
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import griddata
import nvector as nv
import datetime as dt
import aacgmv2
import calendar
import cartopy.crs as ccrs
import sys
import os

def main(
    startTime, endTime, sat, velFnFmt, potFnFmt, satFnFmt,
):
    
    assert startTime.day == endTime.day, 'Cannot handle multi-day events yet'
    
    # load data
    velFile = os.path.expanduser(velFnFmt) % startTime.day
    potFile = os.path.expanduser(potFnFmt) % startTime.day
    satFile = os.path.expanduser(satFnFmt) % (startTime.day, sat)

    modVelData = nc_utils.ncread_vars(velFile)
    potData = nc_utils.ncread_vars(potFile)
    dmspData = proc_dmsp.load(satFile)
    
    #various adjustments of data: change model times to unix, adjust model longitude and velocity
    day = dt.datetime(startTime.year, startTime.month, startTime.day)
    dayUnix = calendar.timegm(day.timetuple())
    modVelData["time"] = dayUnix + modVelData["time"] * 3600
    modVelData["lon0"][modVelData["lon0"] > 180] -= 360   
    modVelData["u1p0"] /= 100  # cm/s -> m/s
    modVelData["u3h0"] /= 100  # cm/s -> m/s

    #indexing with start time and end time. adds one index to make up for off by one error
    endTimeIndex = nearest_index(calendar.timegm(endTime.timetuple()), dmspData["UT1_UNIX"])
    dmsp_idx = np.logical_and( 
        dmspData["UT1_UNIX"] > calendar.timegm(startTime.timetuple()),
        dmspData["UT1_UNIX"] < dmspData["UT1_UNIX"][endTimeIndex + 1],
    )
    
    # Select relevant parts of DMSP data
    for k, v in dmspData.items():
        dmspData[k] = v[dmsp_idx]
        
    # calculate DMSP vels
    dmspEArray = np.array([])
    dmspNArray = np.array([])
    
    # will be one less than length of dmsp array
    for tindex in range(len(dmspData["UT1_UNIX"])-1):
        satLatI, satLonI, satLatF, satLonF, forward, left = sat_data(dmspData, tindex)
        dmspEast, dmspNorth = transform_satellite_vectors(satLatI, satLonI, satLatF, satLonF, forward, left)
        dmspEArray = np.append(dmspEArray, dmspEast)
        dmspNArray = np.append(dmspNArray, dmspNorth)     
    
    # loop through the data and interpolate the model to each space/time location  
    modEArray = np.array([])
    modNArray = np.array([])
    
    print(len(dmspData['UT1_UNIX'])-1)

    for tind in range(len(dmspData['UT1_UNIX'])-1):
        print(tind)
        unix = dmspData["UT1_UNIX"][tind]
        satData = sat_data(dmspData, tind)
        modVelE, modVelN = interp_sami3(unix, satData[0], satData[1], modVelData)
        modEArray = np.append(modEArray, modVelE)
        modNArray = np.append(modNArray, modVelN)
    
    #plot velocities vs time and on contour map
    plot_velocities(dmspData["UT1_UNIX"][:len(dmspData["UT1_UNIX"]) -1], 
                    modEArray, modNArray, dmspEArray, dmspNArray)
    
    plot_polar(potData, dmspData, dmspEArray, dmspNArray, modEArray, modNArray, modVelData)

    

def plot_polar(potData, dmspData, dmspEArray, dmspNArray, modEArray, modNArray, modVelData):
    plt.figure(figsize=(8, 10))
    ax1 = plt.subplot(1, 1, 1, projection=ccrs.AzimuthalEquidistant(central_latitude= 90))
    
    
    ax1.set_extent([-180, 180, 45, 90], ccrs.PlateCarree())
    ax1.coastlines('50m')
    ax1.gridlines()
    modIndex = nearest_index(dmspData["UT1_UNIX"][0], modVelData["time"])
    
    dmspLons = dmspData["GLON"][:len(dmspData["UT1_UNIX"]) -1]
    dmspLats = dmspData["GDLAT"][:len(dmspData["UT1_UNIX"]) -1]
    
    #plot contours
    ax1.contour(potData["Geographic Longitude"],
                potData["Geographic Latitude"], 
                potData["Potential"], cmap = "hot", transform = ccrs.PlateCarree())
    
    #plot dmsp velocity data
    ax1.quiver(dmspLons, dmspLats, 
               dmspEArray, dmspNArray, color = "blue", width = .002, label = "dmsp data",
               transform=ccrs.PlateCarree())
    
    #plot interpolated model data
    ax1.quiver(dmspLons, dmspLats, 
               modEArray, modNArray, color = "green", width = .002, label = "model data",
               transform=ccrs.PlateCarree())

    #if this ends up being permanent, create new function, and process in beginning
    #process gridded model data
    latIndex = modVelData["lat0"] >=45
    modVelData["lat0"] = modVelData["lat0"][latIndex]
    modVelData["lon0"] = modVelData["lon0"][latIndex]
    
    modEVels = modVelData["u3h0"][modIndex][latIndex]
    modNVels = modVelData["u1p0"][modIndex][latIndex]
 
    for index in range(len(modEVels)):
        
        theta = calc_theta(modVelData["lat0"][index], modVelData["lon0"][index], 
                           dt.datetime.utcfromtimestamp(modVelData["time"][modIndex]))
        
        modEVels[index] += np.cos(theta) * modNVels[index]
        modNVels[index] = np.sin(theta) * modNVels[index]
    
    #plot gridded model data    
    ax1.quiver(modVelData["lon0"], modVelData["lat0"], modEVels, modNVels, transform = ccrs.PlateCarree())
    
    startTime = dt.datetime.utcfromtimestamp(dmspData["UT1_UNIX"][0]).strftime( "%H:%M:%S")
    endTime = dt.datetime.utcfromtimestamp(dmspData["UT1_UNIX"][len(dmspData["UT1_UNIX"])-1]).strftime( "%H:%M:%S")
    
    plt.legend()
    plt.suptitle("%s - %s" % (startTime, endTime))
    plt.savefig("/Users/sitardp1/Documents/data/contour_plot.png", dpi=300)

    plt.show()
    
    

# returns the index of an array which is closest to value    
def nearest_index(value, array):
    
    index = (np.abs(array - value)).argmin()
    return index
 

# returns coordinates and velocity of measurement at a certain time    
def sat_data(dmspData, dmspTindex):
    
    # read satellite data
    satLatI = dmspData["GDLAT"][dmspTindex]
    satLonI = dmspData["GLON"][dmspTindex]
    
    satLatF = dmspData["GDLAT"][dmspTindex + 1]
    satLonF = dmspData["GLON"][dmspTindex + 1]
    
    forward = dmspData["ION_V_SAT_FOR"][dmspTindex]
    left = dmspData["ION_V_SAT_LEFT"][dmspTindex]
    
    return satLatI, satLonI, satLatF, satLonF, forward, left


def transform_satellite_vectors(satLatI, satLonI, satLatF, satLonF, forward, left):
    """ return east/north components of velocity measurement """ 
    
    # create north/east vectors based on satellite direction
    wgs84 = nv.FrameE(name='WGS84')
    init = wgs84.GeoPoint(satLatI, satLonI, 0, degrees=True)
    
    final = wgs84.GeoPoint(satLatF, satLonF, 0, degrees=True)
    
    p_AB_N = init.delta_to(final) 
    north, east, z = p_AB_N.pvector.ravel()
    
    # use geometry to find components of dmsp measurement velocity
    thetaForward = np.arctan2(north, east)  # Angle between geographic East and the satellite's direction
    alpha = np.arctan(abs(forward) / abs(left))  # Angle between satellite left and velocity direction
    theta = thetaForward + np.pi / 2 - alpha   #Angle between velocity direction and East
    mag = np.hypot(forward, left)  # magnitude of velocity

    # dmsp measurement components
    dmspEast = mag * np.cos(theta)
    dmspNorth = mag * np.sin(theta)
    
    return dmspEast, dmspNorth
 
 
def interp_mod_spatial(velData, modTimeIndex, satLat, satLon, dTime):
    """ interpolate model data between satellite coordinates """

    #interpolate model data between satellite coordinates

    interpModN = griddata(
        (velData["lon0"].flatten(), velData["lat0"].flatten()), 
        velData["u1p0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")
    interpModE = griddata(
        (velData["lon0"].flatten(), velData["lat0"].flatten()), 
        velData["u3h0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")

    
    # Convert from Magnetic-oriented to geographic-oriented velocities 
    theta = calc_theta(satLat, satLon, dTime, refAlt=400)

    geoNorth = np.sin(theta) * interpModN
    geoEast = interpModE +  np.cos(theta) * interpModE

    return geoNorth, geoEast


def calc_theta(
        satLat, satLon, dTime, 
        refAlt = 400,
):
    """ theta is the angle between the vector and the x axis """

    # Calculates the angle between geographic and magnetic pole
    mPole = aacgmv2.convert_latlon(90, 0, refAlt, dTime, method_code="A2G")
    wgs84 = nv.FrameE(name='WGS84')
    polePoint = wgs84.GeoPoint(mPole[0], 
                          mPole[1], -refAlt * 1E3, degrees=True)
    
    modelPoint = wgs84.GeoPoint(satLat, satLon, -refAlt * 1E3, degrees =True)
    
    p_AB_N = modelPoint.delta_to(polePoint)
    north, east, z = p_AB_N.pvector.ravel()
    theta = np.arctan2(north, east)
    return theta 


def interp_mod_temporal(dataTime, modT1Unix, modT2Unix, geoNorthT1, geoEastT1, geoNorthT2, geoEastT2):
    """ interpolate model data between two model timestamps """

    interpE = np.interp(dataTime, [modT1Unix, modT2Unix], [geoEastT1, geoEastT2])    
    interpN = np.interp(dataTime, [modT1Unix, modT2Unix], [geoNorthT1, geoNorthT2])
    
    return interpE, interpN


def interp_sami3(dataTime, dataLat, dataLon, modVel):
    
    #1 Find model times bracketing the relevant data time
    lowerGateFlag = modVel["time"] <= dataTime

    modT1 = nearest_index(dataTime, modVel["time"][lowerGateFlag])
    modT2 = modT1 + 1
    
    #2 Spatially interpolate model to the data location at modT1 and modT2
    dTimeT1 = dt.datetime.utcfromtimestamp(modVel["time"][modT1])
    dTimeT2 = dt.datetime.utcfromtimestamp(modVel["time"][modT2])
   
        
    geoNorthT1, geoEastT1 = interp_mod_spatial(modVel, modT1, dataLat, dataLon, dTimeT1)
    geoNorthT2, geoEastT2 = interp_mod_spatial(modVel, modT2, dataLat, dataLon, dTimeT2)
    
    #3 Temporally interpolate the model to dataTime
    interpTempE, interpTempN = interp_mod_temporal(dataTime, modVel["time"][modT1], modVel["time"][modT2], 
                                                geoNorthT1, geoEastT1, geoNorthT2, geoEastT2)
    
    return interpTempE, interpTempN


def plot_velocities(timeRange, interpEArray, interpNArray, dmspEArray, dmspNArray):
    """ plot the comparison velocities """
    
    startTime = dt.datetime.utcfromtimestamp(timeRange[0]).strftime( "%H:%M:%S")
    endTime = dt.datetime.utcfromtimestamp(timeRange[len(timeRange)-1]).strftime( "%H:%M:%S")
    
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    modE = ax1.plot(timeRange, interpEArray, label = "model E")
    dmspE = ax1.plot(timeRange, dmspEArray, label = "dmsp E")
    ax1.set_ylabel(" Velocity m/s")
    ax1.legend()
    ax1.set_title("East Component")
    
    modN = ax2.plot(timeRange, interpNArray, label = "model N")
    dmspN = ax2.plot(timeRange, dmspNArray, label = "dmsp N")
    ax2.set_ylabel(" Velocity m/s")
    ax2.set_xlabel("UNIX Seconds")
    ax2.legend()
    ax2.set_title("North Component")
    
    plt.suptitle("DMSP vs. SAMI3: %s - %s" % (startTime, endTime))
    
    plt.show()
    plt.close()


if __name__ == "__main__": 

    args = sys.argv
    assert len(args) == 7, 'Should have 6 arguments:\n' + \
        ' -  starttime\n' + \
        ' -  endtime\n' + \
        ' - satellite\n' + \
        ' - potential file\n' + \
        ' - velocity file\n' + \
        ' - satellite file\n' + \
        '\ne.g.:\n python3 plot_contours.py  ' + \
        '2014,5,23,20,15 2014,5,23,20,20 ' + \
        'F16 ' + \
        '/Users/sitardp1/Documents/data/sami3_may%ia.nc ' + \
        '/Users/sitardp1/Documents/data/sami3_may%i_phi.nc ' + \
        '/Users/sitardp1/Documents/Madrigal/dms_ut_201405%i_%i.002.hdf5 '

    timeStr = '%Y,%m,%d,%H,%M' 
    sTime = dt.datetime.strptime(args[1], timeStr)  
    eTime = dt.datetime.strptime(args[2], timeStr)  
    sat = int(args[3][1:])
    breakpoint()
    main(
        startTime=sTime,
        endTime=eTime,
        sat=16,
        velFnFmt=args[4],
        potFnFmt=args[5],
        satFnFmt=args[6],
    )





