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
import nvector as nv
from datetime import datetime
import time

def main():
    #initial start times
    day = 22
    startHour = 12
    startMin = 0
    
    #read data
    pot_file = "sami3_may%i_phi.nc" % (day)
    vel_file = "sami3_may%ia.nc" % (day)
    
    pot_data = nc_utils.ncread_vars(pot_file)
    vel_data = nc_utils.ncread_vars(vel_file)
    
    mod_timeArray = vel_data["time"]*60
    startModTime = startHour*60 + startMin
    modTimeIndex = nearest_index(startModTime, mod_timeArray)
    
    #plot sami3 velocities, potential contours, and transform dmsp vector data
    plot_model_vel(vel_data, day, modTimeIndex)
    plot_model_contour(pot_data, day, modTimeIndex)
    vector_transform(vel_data, modTimeIndex, day, 15)

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
    
    pdb.set_trace()
    
    #plot model velocity data
    vel = ax.quiver(modLons.flatten(), modLats.flatten(), 
                    mod_horizontal.flatten(), mod_vertical.flatten())
    
    title_plot(hour, day, "mod_vel")
    


#plot SAMI3 contour data in polar
def plot_model_contour(pot_data, day, modTimeIndex):

    hour = str(pot_data["time"][modTimeIndex])
    phi = pot_data["phi"][modTimeIndex,:,:]
    
    
    #adjust data for polar
    adjPotLats = 90 - pot_data["lat"]
    adjPotLons = np.deg2rad(pot_data["lon"])
    
    fig, ax = plt.subplots(1, 1, subplot_kw=dict(projection='polar'))
    
    pot = ax.contour(adjPotLons, adjPotLats, phi, cmap='hot')
    ax.set_theta_zero_location("E")
    ax.set_rlabel_position(50)
    cbar = fig.colorbar(pot)
    
    
    title_plot(hour, day, "mod_contour")




def vector_transform(vel_data, modTimeIndex, day, sat):

    fig, ax = plt.subplots(1, 1)
    
    #read data
    sat_file = "dms_ut_201405%i_%i.002.p" % (day, sat)
    dmsp_data = pickle.load( open(sat_file, "rb"))
    
    #quality flags for data
    forQualIndex = dmsp_data["ION_V_FOR_FLAG"] == 1
    leftQualIndex = dmsp_data["ION_V_LEFT_FLAG"] == 1
    qualFlag = forQualIndex & leftQualIndex
    
    #set time index for dmsp data
    startDay = datetime(2014, 5, day)
    dayUnix = time.mktime(startDay.timetuple())
    timeUnix = dayUnix + vel_data["time"][modTimeIndex]*3600
    dmspTindex = nearest_index(timeUnix, dmsp_data["UT1_UNIX"][qualFlag])
    
    #read satellite data
    satLat = dmsp_data["GDLAT"][qualFlag][dmspTindex]
    satLon = dmsp_data["GLON"][qualFlag][dmspTindex]
    forward = dmsp_data["ION_V_SAT_FOR"][qualFlag][dmspTindex]
    left = dmsp_data["ION_V_SAT_LEFT"][qualFlag][dmspTindex]
    
    #create north/east vectors based on satellite direction
    wgs84 = nv.FrameE(name='WGS84')
    init = wgs84.GeoPoint(satLat, 
                          satLon, 0, degrees=True)
    
    final = wgs84.GeoPoint(dmsp_data["GDLAT"][qualFlag][dmspTindex + 1], 
                          dmsp_data["GLON"][qualFlag][dmspTindex + 1], 0, degrees=True)
    
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
    

    #interpolate model data between satellite coordinates
    interp_mod_east = griddata((vel_data["lon0"].flatten(), vel_data["lat0"].flatten()), 
                            vel_data["u3h0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")
    interp_mod_north = griddata((vel_data["lon0"].flatten(), vel_data["lat0"].flatten()), 
                            vel_data["u1p0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")
    

    
    #ax.quiver(dmsp_data["GLON"][dmspTindex], dmsp_data["GDLAT"][dmspTindex], 
    #          interp_mod_x, interp_mod_y, color = colors[sat -15])
    

        
        
    
    title_plot(str(vel_data["time"][modTimeIndex]), day, "comparison")

main()
    







