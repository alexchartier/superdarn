#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jul  9 17:41:37 2021

@author: sitardp1
"""
import nc_utils
import matplotlib.pyplot as plt
import numpy as np
import pdb
import pickle
from scipy.interpolate import griddata
from scipy.interpolate import interp1d
import nvector as nv
from datetime import datetime
import time
import aacgmv2
import calendar

def main():
    #initial start times
    day = 23
    startHour = 19
    startMin = 0
    sat = 16
    
    #read data
    pot_file = "sami3_may%i_phi.nc" % (day)
    vel_file = "sami3_may%ia.nc" % (day)
    sat_file = "dms_ut_201405%i_%i.002.p" % (day, sat)
    
    pot_data = nc_utils.ncread_vars(pot_file)
    vel_data = nc_utils.ncread_vars(vel_file)
    dmsp_data = pickle.load( open(sat_file, "rb"))

    #calculate modTimeIndex
    mod_timeArray = vel_data["time"]*60
    startModTime = startHour*60 + startMin
    modTimeIndex = nearest_index(startModTime, mod_timeArray)
    
    
    #quality flags for dmsp data
    forQualIndex = dmsp_data["ION_V_FOR_FLAG"] == 1
    leftQualIndex = dmsp_data["ION_V_LEFT_FLAG"] == 1
    qualFlag = forQualIndex & leftQualIndex
    
    #set initial time index for dmsp data
    startDay = datetime(2014, 5, day)
    dayUnix = calendar.timegm(startDay.timetuple())
    timeUnix = dayUnix + vel_data["time"][modTimeIndex]*3600
    dmspTindex = nearest_index(timeUnix, dmsp_data["UT1_UNIX"][qualFlag])
    
    #starting time and end time of data comparison
    satStartTime = dmspTindex
    satEndTime = nearest_index(dayUnix + vel_data["time"][modTimeIndex+1]*3600, dmsp_data["UT1_UNIX"])
    timeRange = dmsp_data["UT1_UNIX"][qualFlag][satStartTime:satEndTime]
    
    
    
    #interpolation of model data to satellite coordinates and times in time range
    satLatI, satLonI, satLatF, satLonF, forward, left = filter_data(dmsp_data, qualFlag, dmspTindex)
    modEStart, modNStart = interp_mod_spatial(vel_data, modTimeIndex, satLatI, satLonI, day, startHour, startMin)
    modEEnd, modNEnd = interp_mod_spatial(vel_data, modTimeIndex +1, satLatI, satLonI, day, startHour, startMin)
    
    interpEArray, interpNArray = interp_mod_temporal(timeRange, timeUnix, vel_data["time"][modTimeIndex+1]*3600, 
                                                     modEStart, modNStart, modEEnd, modNEnd)
    
    #create array of dmsp data in time range
    dmspEArray = np.array([])
    dmspNArray = np.array([])
    for timeCode in timeRange:
        pdb.set_trace()
        dmspTindex = int(np.where(dmsp_data["UT1_UNIX"][qualFlag] == timeCode))
        satLatI, satLonI, satLatF, satLonF, forward, left = filter_data(dmsp_data, qualFlag, dmspTindex)
        dmsp_east, dmsp_north = transform_satellite_vectors(satLatI, satLonI, satLatF, satLonF, forward, left)
        
        dmspEArray = np.append(dmspEArray, dmsp_east)
        dmspNArray = np.append(dmspNArray, dmsp_north)
        
    
    
    pdb.set_trace()

#returns the index of an array which is closest to value    
def nearest_index(value, array):
    
    index = (np.abs(array - value)).argmin()
    return index

#titles the plots with date
def title_plot(hour, day, filename):
    
    date = "May" + day
    title = ("AMPERE/SAMI3 %s %s UT" % (date, hour))
    plt.suptitle(title)
      
    plt.savefig(filename+".png", dpi = 300)
    plt.show()
    plt.close()
    
#plot SAMI3 velocity data in a cartesian projection
def plot_model_vel(vel_data, day, modTimeIndex):
    
    hour = str(vel_data["time"][modTimeIndex])

    #plot model velocity data
    fig, ax = plt.subplots(1, 1)
    
    modLons = vel_data["lon0"]
    modLats = vel_data["lat0"]
    
    #more polar conversions
    mod_vertical = vel_data["u1p0"][modTimeIndex]
    mod_horizontal = vel_data["u3h0"][modTimeIndex]
        
    #plot model velocity data
    vel = ax.quiver(modLons.flatten(), modLats.flatten(), 
                    mod_horizontal.flatten(), mod_vertical.flatten())
    
    title_plot(hour, str(day), "mod_vel")
    


#plot SAMI3 contour data in polar
def plot_model_contour(pot_data, day, modTimeIndex):

    hour = str(pot_data["time"][modTimeIndex])
    phi = pot_data["phi"][modTimeIndex,:,:]
    
    pdb.set_trace()
    #adjust data for polar
    adjPotLats = 90 - pot_data["lat"]
    adjPotLons = np.deg2rad(pot_data["lon"])
    
    for timeCodes in range (0, 12):
        modTimeIndex += 1
        print(modTimeIndex)
        
        hour = str(pot_data["time"][modTimeIndex])
    
        fig, ax = plt.subplots(1, 1, subplot_kw=dict(projection='polar'))
        
        pot = ax.contour(adjPotLons, adjPotLats, phi, cmap='hot')
        ax.set_theta_zero_location("E")
        ax.set_rlabel_position(50)
        cbar = fig.colorbar(pot)
        
        plot_satellite_passes(day, hour, modTimeIndex, ax)
        
        title_plot(hour, str(day), "mod_contour" +str(timeCodes))
        plt.close()


def plot_satellite_passes(day,hour, modTimeIndex, ax):
    colors = ["red", "blue", " green"]
    
    for sat in range(16, 19):
        
        sat_file = "dms_ut_201405%i_%i.002.p" % (day, sat)
        dmsp_data = pickle.load( open(sat_file, "rb"))
        
        startDay = datetime(2014, 5, day)
        
        dayUnix = calendar.timegm(startDay.timetuple())
        timeUnix = dayUnix + float(hour)*3600
        dmspTindex = nearest_index(timeUnix, dmsp_data["UT1_UNIX"])                        
        
        for x in range(0, 20):
            adjLon = np.deg2rad(180 + dmsp_data["GLON"][dmspTindex])
            adjLat = 90 - dmsp_data["GDLAT"][dmspTindex]
            ax.scatter(adjLon, adjLat, color = colors[sat - 16])
            
            dmspTindex += 20
    
   
def filter_data(dmsp_data, qualFlag, dmspTindex):
    
    #read satellite data
    satLatI = dmsp_data["GDLAT"][qualFlag][dmspTindex]
    satLonI = dmsp_data["GLON"][qualFlag][dmspTindex]
    
    satLatF = dmsp_data["GDLAT"][qualFlag][dmspTindex + 1]
    satLonF = dmsp_data["GLON"][qualFlag][dmspTindex + 1]
    
    forward = dmsp_data["ION_V_SAT_FOR"][qualFlag][dmspTindex]
    left = dmsp_data["ION_V_SAT_LEFT"][qualFlag][dmspTindex]
    
    return satLatI, satLonI, satLatF, satLonF, forward, left
    
def transform_satellite_vectors(satLatI, satLonI, satLatF, satLonF, forward, left):
    

    #create north/east vectors based on satellite direction
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
    
def interp_mod_spatial(vel_data, modTimeIndex, satLat, satLon, day, startHour, startMin):
    
    refAlt = 400
    dTime = datetime(2014, 5, day, startHour, startMin)
    mPole = aacgmv2.convert_latlon(90, 0, refAlt, dTime, method_code="A2G")
    wgs84 = nv.FrameE(name='WGS84')
    polePoint = wgs84.GeoPoint(mPole[0], 
                          mPole[1], -refAlt * 1E3, degrees=True)
    

    #interpolate model data between satellite coordinates
    interp_mod_east = griddata((vel_data["lon0"].flatten(), vel_data["lat0"].flatten()), 
                            vel_data["u3h0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")
    interp_mod_north = griddata((vel_data["lon0"].flatten(), vel_data["lat0"].flatten()), 
                            vel_data["u1p0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")
    
    
    modelPoint = wgs84.GeoPoint(satLat, satLon, -refAlt * 1E3, degrees =True)
                    
    p_AB_N = modelPoint.delta_to(polePoint)
    north, east, z = p_AB_N.pvector.ravel()
    theta = np.arctan2(north, east)
    
    vertical = np.sin(theta) * interp_mod_north
    horizontal = interp_mod_east +  np.cos(theta) * interp_mod_north                 

    return horizontal, vertical
    
def interp_mod_temporal(timeRange, modStartTimeUnix, modEndTimeUnix, modEStart, modNStart, modEEnd, modNEnd):

    interpEArray = np.interp(timeRange, [modStartTimeUnix, modEndTimeUnix], [modEStart, modEEnd])    
    interpNArray = np.interp(timeRange, [modStartTimeUnix, modEndTimeUnix], [modNStart, modNEnd])
    
    
    return interpEArray, interpNArray

        
main()
    







