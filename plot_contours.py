#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jul  9 17:41:37 2021

@author: sitardp1
"""
import nc_utils
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import griddata
from scipy.interpolate import interp1d
import nvector as nv
import datetime as dt
import aacgmv2
import calendar
import proc_dmsp

def main(
    startTime = dt.datetime(2014, 5, 23, 20, 15),
    endTime = dt.datetime(2014, 5, 23, 20, 30),
    modTimeStep = 15, 
    sat = 16,
    #potFnFmt="sami3_may%i_phi.nc",
    #velFnFmt="sami3_may%ia.nc",
    satFnFmt="data/dmsp/dms_ut_201405%i_%i.002.hdf5",
):

    assert startTime.day == endTime.day, 'Cannot handle multi-day events yet'
    
    # load data
    #pot_file = potFnFmt % (startTime.day)
    #vel_file = velFnFmt % (startTime.day)
    sat_file = satFnFmt % (startTime.day, sat)
    
    dmsp_data = proc_dmsp.load(sat_file)
    breakpoint()
    pot_data = nc_utils.ncread_vars(pot_file)
    vel_data = nc_utils.ncread_vars(vel_file)


    # select the DMSP data of interest
    goodTimes = np.logical_and(dmsp_data['Time'] >= startTime, dmsp_data['Time'] <= endTime)
    for k, v in dmsp_data.items():
        dmsp_data[k] = v[goodTimes]


    for tind, dmspTime in enumerate(dmsp_data['Time']):
        """ do the model interpolation at each time/lat-lon location """

        dmsp_data['UT1_UNIX'][tind]



    # calculate modTimeIndex
    mod_timeArray = vel_data["time"]*60
    startModTime = startHour*60 + startMin
    modTimeIndex = nearest_index(startModTime, mod_timeArray)

    # starting time and end time of data comparison
    satStartTime = dmspTindex
    satEndTime = nearest_index(dayUnix + vel_data["time"][modTimeIndex+1]*3600, dmsp_data["UT1_UNIX"])
    timeRange = dmsp_data["UT1_UNIX"][satStartTime:satEndTime]

    
    # interpolation of model data to satellite coordinates and times in time range
    satLatI, satLonI, satLatF, satLonF, forward, left = sat_data(dmsp_data, qualFlag, dmspTindex)
    modEStart, modNStart = interp_mod_spatial(vel_data, modTimeIndex, satLatI, satLonI, day, startHour, startMin)
    modEEnd, modNEnd = interp_mod_spatial(vel_data, modTimeIndex +1, satLatI, satLonI, day, startHour, startMin)
    
    interpEArray, interpNArray = interp_mod_temporal(timeRange, timeUnix, vel_data["time"][modTimeIndex+1]*3600, 
                                                     modEStart, modNStart, modEEnd, modNEnd)
    
    # create array of dmsp data in time range
    dmspEArray = np.array([])
    dmspNArray = np.array([])
    for timeCode in timeRange:

        dmspTindex = np.where(dmsp_data["UT1_UNIX"][qualFlag] == timeCode)[0]
        satLatI, satLonI, satLatF, satLonF, forward, left = sat_data(dmsp_data, qualFlag, dmspTindex)
        dmsp_east, dmsp_north = transform_satellite_vectors(satLatI, satLonI, satLatF, satLonF, forward, left)
        
        dmspEArray = np.append(dmspEArray, dmsp_east)
        dmspNArray = np.append(dmspNArray, dmsp_north)
        
    
    pdb.set_trace()
    
    plot_velocities(timeRange, interpEArray, interpNArray, dmspEArray, dmspNArray)
    
    


# returns the index of an array which is closest to value    
def nearest_index(value, array):
    
    index = (np.abs(array - value)).argmin()
    return index

# titles the plots with date
def title_plot(hour, day, filename):
    
    date = "May" + day
    title = ("AMPERE/SAMI3 %s %s UT" % (date, hour))
    plt.suptitle(title)
      
    plt.savefig(filename+".png", dpi = 300)
    plt.show()
    plt.close()
    
# plot SAMI3 velocity data in a cartesian projection
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
    


# plot SAMI3 contour data in polar
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
        
        startDay = dt.datetime(2014, 5, day)
        
        dayUnix = calendar.timegm(startDay.timetuple())
        timeUnix = dayUnix + float(hour)*3600
        dmspTindex = nearest_index(timeUnix, dmsp_data["UT1_UNIX"])                        
        
        for x in range(0, 20):
            adjLon = np.deg2rad(180 + dmsp_data["GLON"][dmspTindex])
            adjLat = 90 - dmsp_data["GDLAT"][dmspTindex]
            ax.scatter(adjLon, adjLat, color = colors[sat - 16])
            
            dmspTindex += 20
    

# returns coordinates and velocity of measurement at a certain time    
def sat_data(dmsp_data, qualFlag, dmspTindex):
    
    # read satellite data
    satLatI = dmsp_data["GDLAT"][qualFlag][dmspTindex]
    satLonI = dmsp_data["GLON"][qualFlag][dmspTindex]
    
    satLatF = dmsp_data["GDLAT"][qualFlag][dmspTindex + 1]
    satLonF = dmsp_data["GLON"][qualFlag][dmspTindex + 1]
    
    forward = dmsp_data["ION_V_SAT_FOR"][qualFlag][dmspTindex]
    left = dmsp_data["ION_V_SAT_LEFT"][qualFlag][dmspTindex]
    
    return satLatI, satLonI, satLatF, satLonF, forward, left

#return east/north components of velocity measurement    
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
def interp_mod_spatial(vel_data, modTimeIndex, satLat, satLon, day, startHour, startMin):
    
    refAlt = 400
    dTime = dt.datetime(2014, 5, day, startHour, startMin)
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


#interpolate model data between two model timestamps    
def interp_mod_temporal(timeRange, modStartTimeUnix, modEndTimeUnix, modEStart, modNStart, modEEnd, modNEnd):

    interpEArray = np.interp(timeRange, [modStartTimeUnix, modEndTimeUnix], [modEStart, modEEnd])    
    interpNArray = np.interp(timeRange, [modStartTimeUnix, modEndTimeUnix], [modNStart, modNEnd])
    
    return interpEArray, interpNArray


# plot the comparison velocities
def plot_velocities(timeRange, interpEArray, interpNArray, dmspEArray, dmspNArray):
    
    startTime = dt.datetime.utcfromtimestamp(timeRange[0]).strftime( "%H:%M:%S")
    endTime = dt.datetime.utcfromtimestamp(timeRange[len(timeRange)-1]).strftime( "%H:%M:%S")
    
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    modE = ax1.plot(timeRange, interpEArray, label = "model E")
    dmspE = ax1.plot(timeRange, dmspEArray, label = "dmsp E")
    ax1.set_ylabel(" Velocity m/s")
    ax1.set_title("East Component")
    
    modN = ax2.plot(timeRange, interpNArray, label = "model N")
    dmspN = ax2.plot(timeRange, dmspNArray, label = "dmsp N")
    ax2.set_xlabel("UNIX Seconds")
    ax2.set_title("North Component")
    
    plt.suptitle("DMSP vs. SAMI3: %s - %s" % (startTime, endTime))
    
    plt.show()
    plt.close()


if __name__ == "__main__": 
    main()
    







