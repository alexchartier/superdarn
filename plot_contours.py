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
import pickle
from scipy import interpolate
import cartopy.crs as ccrs
import pdb

def main(
    startTime = dt.datetime(2014, 5, 23, 20, 30, 0),
    endTime = dt.datetime(2014, 5, 23, 20, 30, 30),
    modTimeStep = 15, 
    sat = 16,
    potFnFmt="/Users/sitardp1/Documents/data/sami3_may%i_phi.nc",
    velFnFmt="/Users/sitardp1/Documents/data/sami3_may%ia.nc",
    satFnFmt="/Users/sitardp1/Documents/data/dms_ut_201405%i_%i.002.hdf5",
):
    
    assert startTime.day == endTime.day, 'Cannot handle multi-day events yet'
    
    # load data
    pot_file = potFnFmt % (startTime.day)
    vel_file = velFnFmt % (startTime.day)
    sat_file = satFnFmt % (startTime.day, sat)
    
    dmsp_data = proc_dmsp.load(sat_file)
    pot_data = nc_utils.ncread_vars(pot_file)
    modVelData = nc_utils.ncread_vars(vel_file)
    
    #various adjustments of data: change model times to unix, adjust model longitude and velocity
    day = dt.datetime(startTime.year, startTime.month, startTime.day)
    dayUnix = calendar.timegm(day.timetuple())
    modVelData["time"] = dayUnix + modVelData["time"]*3600
    pot_data["time"] = dayUnix + pot_data["time"]*3600
    modVelData["lon0"] -= 180
    modVelData["u1p0"] /= 100
    modVelData["u3h0"] /= 100


    #indexing with start time and end time. adds one index to make up for off by one error
    endTimeIndex = nearest_index(calendar.timegm(endTime.timetuple()), dmsp_data["UT1_UNIX"])
    dmsp_idx = np.logical_and( 
        dmsp_data["UT1_UNIX"] > calendar.timegm(startTime.timetuple()),
        dmsp_data["UT1_UNIX"] < dmsp_data["UT1_UNIX"][endTimeIndex + 1],
    )
    
    # Select relevant parts of DMSP data
    for k, v in dmsp_data.items():
        dmsp_data[k] = v[dmsp_idx]
        
    # calculate DMSP vels
    dmspEArray = np.array([])
    dmspNArray = np.array([])
    
    #will be one less than length of dmsp array
    for tindex in range(len(dmsp_data["UT1_UNIX"])-1):
        satLatI, satLonI, satLatF, satLonF, forward, left = sat_data(dmsp_data, tindex)
        dmsp_east, dmsp_north = transform_satellite_vectors(satLatI, satLonI, satLatF, satLonF, forward, left)
        dmspEArray = np.append(dmspEArray, dmsp_east)
        dmspNArray = np.append(dmspNArray, dmsp_north)     
    
    # loop through the data and interpolate the model to each space/time location  
    modEArray = np.array([])
    modNArray = np.array([])
    
    print(len(dmsp_data['UT1_UNIX'])-1)
    """
    latInd = modVelData["lat0"] >= 60
    modVelData["lon0"] = modVelData["lon0"][latInd]
    modVelData["lat0"] = modVelData["lat0"][latInd]

    interpolant = interpolate.interp2d(modVelData["lon0"].flatten(), 
                                       modVelData["lat0"].flatten(), modVelData["u1p0"][0][latInd].flatten())
    """
    for tind in range(len(dmsp_data['UT1_UNIX'])-1):
        print(tind)
    
        unix = dmsp_data["UT1_UNIX"][tind]
        satData = sat_data(dmsp_data, tind)
        modVelE, modVelN = interp_sami3(unix, satData[0], satData[1], modVelData)
        modEArray = np.append(modEArray, modVelE)
        modNArray = np.append(modNArray, modVelN)
    
    pdb.set_trace()
    
    #plot velocities vs time and on contour map
    plot_velocities(dmsp_data["UT1_UNIX"][:len(dmsp_data["UT1_UNIX"]) -1], 
                    modEArray, modNArray, dmspEArray, dmspNArray)
    
    plot_polar(pot_data, dmsp_data, dmspEArray, dmspNArray, modEArray, modNArray)

    
#plot contour map, dmsp data, and interpolated model data
def plot_polar(pot_data, dmsp_data, dmspEArray, dmspNArray, modEArray, modNArray):
    plt.figure(figsize=(8, 10))
    ax1 = plt.subplot(1, 1, 1, projection=ccrs.AzimuthalEquidistant(central_latitude= 90))
    
    
    ax1.set_extent([-180, 180, 45, 90], ccrs.PlateCarree())
    ax1.coastlines('50m')
    ax1.gridlines()
    modIndex = nearest_index(dmsp_data["UT1_UNIX"][0], pot_data["time"])
    
    satLons = dmsp_data["GLON"][:len(dmsp_data["UT1_UNIX"]) -1]
    satLats = dmsp_data["GDLAT"][:len(dmsp_data["UT1_UNIX"]) -1]
    
    ax1.contour(pot_data["lon"] -180, pot_data["lat"], pot_data["phi"][modIndex], cmap = "hot", transform = ccrs.PlateCarree())
    ax1.quiver(satLons, satLats, 
               dmspEArray, dmspNArray, color = "red",
               transform=ccrs.PlateCarree())
    ax1.quiver(satLons, satLats, 
               modEArray, modNArray, color = "blue",
               transform=ccrs.PlateCarree())
    
    startTime = dt.datetime.utcfromtimestamp(dmsp_data["UT1_UNIX"][0]).strftime( "%H:%M:%S")
    endTime = dt.datetime.utcfromtimestamp(dmsp_data["UT1_UNIX"][len(dmsp_data["UT1_UNIX"])-1]).strftime( "%H:%M:%S")
    
    plt.suptitle("%s - %s" % (startTime, endTime))
    plt.savefig("/Users/sitardp1/Documents/data/contour_plot.png", dpi=300)

    plt.show()
    
    

# returns the index of an array which is closest to value    
def nearest_index(value, array):
    
    index = (np.abs(array - value)).argmin()
    return index
 

# returns coordinates and velocity of measurement at a certain time    
def sat_data(dmsp_data, dmspTindex):
    
    # read satellite data
    satLatI = dmsp_data["GDLAT"][dmspTindex]
    satLonI = dmsp_data["GLON"][dmspTindex]
    
    satLatF = dmsp_data["GDLAT"][dmspTindex + 1]
    satLonF = dmsp_data["GLON"][dmspTindex + 1]
    
    forward = dmsp_data["ION_V_SAT_FOR"][dmspTindex]
    left = dmsp_data["ION_V_SAT_LEFT"][dmspTindex]
    
    return satLatI, satLonI, satLatF, satLonF, forward, left

#return east/north components of satellite velocity measurement    
def transform_satellite_vectors(satLatI, satLonI, satLatF, satLonF, forward, left):
    
    # create north/east vectors based on satellite direction
    wgs84 = nv.FrameE(name='WGS84')
    init = wgs84.GeoPoint(satLatI, 
                          satLonI, 0, degrees=True)
    
    final = wgs84.GeoPoint(satLatF, 
                          satLonF, 0, degrees=True)
    
    p_AB_N = init.delta_to(final) 
    north, east, z = p_AB_N.pvector.ravel()
    
    
    #use geometry to find components of dmsp measurement velocity
    theta_for = np.arctan2(north, east)
    alpha = np.arctan(abs(forward) / abs(left))
    theta = theta_for + np.pi/2 - alpha
    mag = np.hypot(forward, left)

    #dmsp measurement components
    dmsp_east = mag * np.cos(theta)
    dmsp_north = mag * np.sin(theta)
    
    return dmsp_east, dmsp_north
 
 
#interpolate model data between satellite coordinates  
def interp_mod_spatial(vel_data, modTimeIndex, satLat, satLon, dTime):

    #interpolate model data between satellite coordinates
    
    """
    interpolant.z = vel_data["u1p0"][modTimeIndex].flatten()
    interpModN = interpolant(satLon, satLat)
    
    interpolant.z = vel_data["u3h0"][modTimeIndex].flatten()
    interpModE = interpolant(satLon, satLat)
    
    """
    interpModN = griddata(
        (vel_data["lon0"].flatten(), vel_data["lat0"].flatten()), 
        vel_data["u1p0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")
    interpModE = griddata(
        (vel_data["lon0"].flatten(), vel_data["lat0"].flatten()), 
        vel_data["u3h0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")

    
    # Convert from Magnetic-oriented to geographic-oriented velocities 
    theta = calc_theta(satLat, satLon, dTime, refAlt=400)

    geoNorth = np.sin(theta) * interpModN
    geoEast = interpModE +  np.cos(theta) * interpModE

    return geoNorth, geoEast

# theta is the angle between the vector and the x axis
def calc_theta(
        satLat, satLon, dTime, 
        refAlt = 400,
):
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


#interpolate model data between two model timestamps    
def interp_mod_temporal(dataTime, modT1Unix, modT2Unix, geoNorthT1, geoEastT1, geoNorthT2, geoEastT2):

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


# plot the comparison velocities
def plot_velocities(timeRange, interpEArray, interpNArray, dmspEArray, dmspNArray):
    
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
    main()
    







