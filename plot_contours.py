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
import scipy.interpolate 
import nvector as nv
import datetime as dt
import aacgmv2
import calendar
import cartopy.crs as ccrs
import sys
import os
import spatial_interpolators
from sknni import SkNNI
from pylab import *


def main(
    startTime, endTime, sat, potFnFmt, velFnFmt, satFnFmt,
):
    
    assert startTime.day == endTime.day, 'Cannot handle multi-day events yet'

    samiTime = dt.datetime(
        startTime.year, startTime.month, startTime.day, startTime.hour, 
        int(np.round(startTime.minute / 10) * 10),
    )
    # Filenames 
    potFile = os.path.expanduser(samiTime.strftime(potFnFmt))
    velFile = os.path.expanduser(samiTime.strftime(velFnFmt))
    satFile = os.path.expanduser(satFnFmt) % (startTime.day, sat)

    # load data
    potData = nc_utils.ncread_vars(potFile)
    # plot_potential(potData, startTime)
    modVelData = nc_utils.ncread_vars(velFile)
    dmspData = proc_dmsp.load(satFile)

    # pre-processing 
    modVelData = reformat_modvels(startTime, modVelData) 
    dmspData = preproc_dmsp(startTime, endTime, dmspData)

    # loop through the data and interpolate the model to each space/time location  
    modEArray = np.array([])
    modNArray = np.array([])
    
    # idx = velData["lat0"].flatten() > 0
    lons = modVelData["lon0"].flatten()
    lats = modVelData["lat0"].flatten()

    intFn = scipy.interpolate.LinearNDInterpolator((lons, lats), np.ones(lons.shape))

    for tind in range(len(dmspData['UT1_UNIX']) - 1):
        print(tind)
        dataTime = dmspData["UT1_UNIX"][tind]
        modVelE, modVelN = interp_sami3(
            dataTime, dmspData["GDLAT"][tind], dmspData["GLON"][tind], modVelData, intFn,
        )
        modEArray = np.append(modEArray, modVelE)
        modNArray = np.append(modNArray, modVelN)
    
    # plot velocities vs time and on contour map
    #plot_velocities(dmspData["UT1_UNIX"][:len(dmspData["UT1_UNIX"]) -1], 
    #                modEArray, modNArray, dmspEArray, dmspNArray)
    
    plot_potential(potData, dt.datetime(2014, 5, 23, 20, 30, 0), dmspData, modEArray, modNArray)
    #plot_polar(potData, dmspData, modEArray, modNArray, modVelData)

def preproc_dmsp(startTime, endTime, dmspData):

    # Downsample
    for k, v in dmspData.items():
        dmspData[k] = v[::10]

    # indexing with start time and end time. adds one index to make up for off by one error
    endTimeIndex = nearest_index(calendar.timegm(endTime.timetuple()), dmspData["UT1_UNIX"])
    dmsp_idx = np.logical_and( 
        dmspData["UT1_UNIX"] > calendar.timegm(startTime.timetuple()),
        dmspData["UT1_UNIX"] < dmspData["UT1_UNIX"][endTimeIndex + 1],
    )
    
    # Select relevant parts of DMSP data
    for k, v in dmspData.items():
        dmspData[k] = v[dmsp_idx]
        
    # Setup DMSP vel storage
    cardDirs = 'E', 'N'
    for d in cardDirs:
        dmspData[d] = np.array([])
    
    # Calculate DMSP vels (need 2-point location of DMSP, so will be one less than length of dmsp array)
    for tindex in range(len(dmspData["UT1_UNIX"])-1):
        satLatI, satLonI, satLatF, satLonF, forward, left = get_sat_data_t1t2(dmspData, tindex)
        dmspEast, dmspNorth = transform_satellite_vectors(satLatI, satLonI, satLatF, satLonF, forward, left)
        dmspData['E'] = np.append(dmspData['E'], dmspEast)
        dmspData['N'] = np.append(dmspData['N'], dmspNorth)

    return dmspData


def reformat_modvels(startTime, modVelData):
    #various adjustments of data: change model times to unix, adjust model longitude and velocity
    day = dt.datetime(startTime.year, startTime.month, startTime.day)
    dayUnix = calendar.timegm(day.timetuple())
    modVelData["time"] = dayUnix + modVelData["time"] * 3600
    modVelData["lon0"][modVelData["lon0"] > 180] -= 360   
    modVelData["u1p0"] /= 100  # cm/s -> m/s
    modVelData["u3h0"] /= 100  # cm/s -> m/s
    return modVelData
    
    
def adjust_model_vels(modVelData, dmspData):
    
    modIndex = nearest_index(dmspData["UT1_UNIX"][0], modVelData["time"])
    latIndex = modVelData["lat0"] >=45
    lats = modVelData["lat0"][latIndex]
    lons = modVelData["lon0"][latIndex]
    
    modEVels = modVelData["u3h0"][modIndex][latIndex]
    modNVels = modVelData["u1p0"][modIndex][latIndex]
 
    for index in range(len(modEVels)):
        theta = calc_theta(lats[index], lons[index], 
                           dt.datetime.utcfromtimestamp(modVelData["time"][modIndex]))
        
        modEVels[index] += np.cos(theta) * modNVels[index]
        modNVels[index] = np.sin(theta) * modNVels[index]
    
    return lats, lons, modEVels, modNVels
    
def nearest_index(value, array):
# returns the index of an array which is closest to value    
    
    index = (np.abs(array - value)).argmin()
    return index
 

def get_sat_data_t1t2(dmspData, dmspTindex):
# returns coordinates and velocity of measurement at a certain time    
    
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
    forAngle = np.arctan2(north, east)  # Angle between geographic East and the satellite's direction
    leftAngle = forAngle + np.pi/2 #Angle between geographic East and the crosstrack direction
    
    forX = forward * np.cos(forAngle)
    leftX = left * np.cos(leftAngle)
    forY = forward * np.sin(forAngle)
    leftY = left * np.sin(leftAngle)
    
    # dmsp measurement components
    dmspEast = forX + leftX
    dmspNorth = forY + leftY
    
    return dmspEast, dmspNorth
 
 
def interp_mod_spatial(intFn, modVelN, modVelE, satLat, satLon, dTime):
    """ interpolate model data between satellite coordinates """

    #interpolate model data between satellite coordinates
    intFn.values = np.expand_dims(modVelN, axis=1).astype('float64')
    interpModN = intFn((satLon, satLat))
    intFn.values = np.expand_dims(modVelE, axis=1).astype('float64')
    interpModE = intFn((satLon, satLat))

    # Convert from Magnetic-oriented to geographic-oriented velocities 
    theta = calc_theta(satLat, satLon, dTime, refAlt=400)

    geoNorth = np.sin(theta) * interpModN
    geoEast = interpModE +  np.cos(theta) * interpModE

    return geoNorth, geoEast


def calc_theta(
        satLat, satLon, dTime, 
        refAlt = 400,
):
    """ theta is the angle between the vector from the satellite to the magnetic pole and the x axis """

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


def interp_sami3(dataTime, satLat, satLon, modVel, intFn):
    
    # Find model times bracketing the relevant data time
    modTI = nearest_index(dataTime, modVel["time"][modVel["time"] <= dataTime])  # First model time index

    # Interpolate t1
    modVelN = modVel["u1p0"][modTI].flatten()
    modVelE = modVel["u3h0"][modTI].flatten()
    geoNorthT1, geoEastT1 = interp_mod_spatial(intFn, modVelN, modVelE, satLat, satLon, dt.datetime.fromtimestamp(dataTime))

    # Interpolate t2
    modVelN = modVel["u1p0"][modTI + 1].flatten()
    modVelE = modVel["u3h0"][modTI + 1].flatten()
    geoNorthT2, geoEastT2 = interp_mod_spatial(intFn, modVelN, modVelE, satLat, satLon, dt.datetime.fromtimestamp(dataTime))
    
    # Temporally interpolate the model to dataTime
    interpModE = np.interp(dataTime, [modVel["time"][modTI], modVel["time"][modTI + 1]], [geoEastT1, geoEastT2])    
    interpModN = np.interp(dataTime, [modVel["time"][modTI], modVel["time"][modTI + 1]], [geoNorthT1, geoNorthT2])    
    
    return interpModE, interpModN


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
    #plt.close()


def plot_potential(potData, time, dmspData, interpModE, interpModN):

    modIndex = nearest_index(time.hour + time.minute / 60, potData['time'])
    potData["lon"][potData["lon"] > 180] -= 360   
    
    # Interpolate and plot potential contours
    lon, lat, vals = potData["lon"], potData["lat"], potData["phi"][modIndex]
    lon[lon > 180] -= 360
    lons_i = np.linspace(-180, 180, 181)
    lats_i = np.linspace(0, 90, 46)
    X_i, Y_i = np.meshgrid(lats_i, lons_i)
    obs = np.array([lat.flatten(), lon.flatten(), vals.flatten()]).T
    intPts = np.array([X_i.flatten(), Y_i.flatten()]).T
    intObj = SkNNI(obs)
    vals_g = intObj(intPts)

    rad = 90 - np.abs(lats_i)
    theta = np.deg2rad(lons_i)
    vl = np.reshape(vals_g[:, 2], (len(lons_i), len(lats_i)))

    fig, ax = plt.subplots(1, 1, subplot_kw=dict(projection='polar'))
    p = ax.pcolormesh(theta, rad, vl.T, cmap='PuOr', shading='gouraud', vmin=-22, vmax=22)
    p = ax.contour(theta, rad,  vl.T, 7, colors='k')

    ax.clabel(p, fmt='%1.0f', fontsize=9, inline=1)
    ax.set_aspect('equal')
    ax.set_ylim(0, 50)
    #ax.set_yticklabels(['80', '70', '60', '50', '0'])
    ax.grid()

    # plot dmsp velocity data
    dmspLons = dmspData["GLON"][:len(dmspData["UT1_UNIX"]) -1]
    dmspLats = dmspData["GDLAT"][:len(dmspData["UT1_UNIX"]) -1]
    rad = 90 - np.abs(dmspLats)
    theta = np.deg2rad(dmspLons)
    ax.quiver(
        theta, rad, dmspData['E'], dmspData['N'], 
        color="m", width=.005, label="DMSP data", 
    )
        #transform=ccrs.PlateCarree(),


    # plot interpolated model data
    #ax.quiver(
    #    theta, rad, interpModE, interpModN, 
    #    color="green", width=.005, label="model data",
    #)

    plt.show()

   

def plot_polar(potData, dmspData, interpModE, interpModN, modVelData):
    plt.figure(figsize=(8, 10))
    ax1 = plt.subplot(1, 1, 1, projection=ccrs.AzimuthalEquidistant(central_latitude= 90))
    
    fig, ax = plt.subplots(1, 1, subplot_kw=dict(projection='polar'))
    ax1.set_extent([-180, 180, 45, 90], ccrs.PlateCarree())
    ax1.coastlines('50m')
    ax1.gridlines()
    modIndex = nearest_index(dmspData["UT1_UNIX"][0], modVelData["time"])
    
    dmspLons = dmspData["GLON"][:len(dmspData["UT1_UNIX"]) -1]
    dmspLats = dmspData["GDLAT"][:len(dmspData["UT1_UNIX"]) -1]
    
    potData["lon"][potData["lon"] > 180] -= 360   
    
    # Interpolate and plot potential contours
    lon, lat, vals = potData["lon"], potData["lat"], potData["phi"][modIndex]
    lon[lon > 180] -= 360
    lons_i = np.linspace(-180, 180, 181)
    lats_i = np.linspace(0, 90, 46)
    X_i, Y_i = np.meshgrid(lats_i, lons_i)
    obs = np.array([lat.flatten(), lon.flatten(), vals.flatten()]).T
    intPts = np.array([X_i.flatten(), Y_i.flatten()]).T
    intObj = SkNNI(obs)
    vals_g = intObj(intPts)

    rad = np.deg2rad(90) - np.abs(np.deg2rad(lats_i.flatten()))
    theta = np.deg2rad(lons_i.flatten())
    vl = np.reshape(vals_g[:, 2], (len(lons_i), len(lats_i)))
    ax1.pcolormesh(lons_i, lats_i, vl.T, cmap='PuOr', transform=ccrs.PlateCarree(), shading='gouraud')  
    ax1.contour(lons_i, lats_i, vl.T, 12, colors='k', transform=ccrs.PlateCarree())  

    # plot dmsp velocity data
    ax1.quiver(dmspLons, dmspLats, dmspData['E'], dmspData['N'], 
        color="m", width=.005, label="DMSP data", 
        transform=ccrs.PlateCarree(),
    )
    """ 
    # plot interpolated model data
    ax1.quiver(dmspLons, dmspLats, 
               interpModE, interpModN, color = "green", width = .003, label = "model data",
               transform=ccrs.PlateCarree())
    """ 
    
    startTime = dt.datetime.utcfromtimestamp(dmspData["UT1_UNIX"][0]).strftime( "%H:%M:%S")
    endTime = dt.datetime.utcfromtimestamp(dmspData["UT1_UNIX"][len(dmspData["UT1_UNIX"])-1]).strftime( "%H:%M:%S")
    
    plt.legend()
    plt.suptitle("%s - %s" % (startTime, endTime))

    plt.show()


def interp(vars, varsout, dt=2., dp=2.):
    """ 
    vars    : dictionary of variables, e.g., from nc file. See mixio/read_nc
    varsout : names of vars to save in txt file. See, e.g., top of ampere_mix_nc2txt
    dt      : delta theta on destination grid, in degrees
    dp      : delta phi on destination grid, in degrees
    """

    # get source grid from vars
    t = vars['Colatitude'][:, 0]
    p = vars['Longitude (solar mag)'][0, :]
    p[-1] = abs(p[-1])

    # define destination grid
    dt*=np.pi/180.
    dp*=np.pi/180.
    # note, below arrays include the end point. see comment on 'stop' value in arange help
    new_t = np.arange(t.min(), t.max(), dt) 
    new_p = np.arange(p.min(), p.max(), dp) 

    for varname in varsout:
        f = scipy.interpolate.RectBivariateSpline(t, p, vars[varname], kx=1, ky=1)  # note, assume uniform ampere grid here
        # change vars in place
        vars[varname] = f(new_t, new_p)



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
        '2014,5,23,20,15,0 2014,5,23,20,20,15 ' + \
        'F16 ' + \
        '/Users/sitardp1/Documents/data/sami3_may%ia.nc ' + \
        '~/pymix/data/pot_sami_cond/may14_euvac/ampere_mix/ampere_mix_%Y-%m-%dT%H-%M-%SZ.nc ' + \
        '/Users/sitardp1/Documents/Madrigal/dms_ut_201405%i_%i.002.hdf5 '

    timeStr = '%Y,%m,%d,%H,%M,%S' 
    sTime = dt.datetime.strptime(args[1], timeStr)  
    eTime = dt.datetime.strptime(args[2], timeStr)  
    sat = int(args[3][1:])
    
    main(
        startTime=sTime,
        endTime=eTime,
        sat=16,
        potFnFmt=args[4],
        velFnFmt=args[5],
        satFnFmt=args[6],
    )





