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
import cartopy.crs as ccrs


#read data
day = 23
pot_file = "sami3_may%i_phi.nc" % (day)
vel_file = "sami3_may%ia.nc" % (day)

pot_data = nc_utils.ncread_vars(pot_file)
vel_data = nc_utils.ncread_vars(vel_file)


date = pot_file.split("_")[1]
modTimeIndex = 0
phi = pot_data["phi"][modTimeIndex,:,:]
hour = str(pot_data["time"][modTimeIndex])
dmspTindex = int(float(hour)*3600)




#plot model velocity data
fig, ax = plt.subplots(1, 1, subplot_kw=dict(projection='polar'))

#change model velocity data to polar
poleIndex = vel_data["lat0"] >= 70
adjVelLats = (90 - vel_data["lat0"][poleIndex]).flatten()
adjVelLons = np.deg2rad(vel_data["lon0"][poleIndex]).flatten()

#more polar conversions
mod_vertical = vel_data["u1p0"][modTimeIndex][poleIndex]
mod_horizontal = vel_data["u3h0"][modTimeIndex][poleIndex]


#plot model velocity data
vel = ax.quiver(adjVelLons, adjVelLats, mod_horizontal, mod_vertical)
ax.set_rlabel_position(50) 
title = ("AMPERE/SAMI3 %s %s UT" % (date, hour))
plt.suptitle(title)

fig.tight_layout()

plt.savefig("test_vel.png", dpi = 300)
plt.show()
plt.close()




#change potential data to polar and plot
adjPotLats = 90 - pot_data["lat"]
adjPotLons = np.deg2rad(pot_data["lon"])

# subplot_kw=dict(projection='polar')
fig, ax = plt.subplots(1, 1, subplot_kw=dict(projection='polar'))

pot = ax.contour(adjPotLons, adjPotLats, phi, cmap='hot')
ax.set_theta_zero_location("E")
ax.set_rlabel_position(50)
cbar = fig.colorbar(pot)


plt.show()
plt.close()

colors = ["red", "orange", "green", "blue", "magenta"]
fig, ax = plt.subplots(1, 1)

#compare data
for sat in range(16,19):
    
    print(sat)

    sat_file = "dms_ut_201405%i_%i.002.p" % (day, sat)
    dmsp_data = pickle.load( open(sat_file, "rb"))
    
    satLat = dmsp_data["GDLAT"][dmspTindex]
    satLon = dmsp_data["GLON"][dmspTindex]
    forward = dmsp_data["ION_V_SAT_FOR"][dmspTindex]
    left = dmsp_data["ION_V_SAT_LEFT"][dmspTindex]
    
    #create vectors based on satellite direction
    wgs84 = nv.FrameE(name='WGS84')
    init = wgs84.GeoPoint(dmsp_data["GDLAT"][dmspTindex], 
                          dmsp_data["GLON"][dmspTindex], 0, degrees=True)
    
    final = wgs84.GeoPoint(dmsp_data["GDLAT"][dmspTindex + 1], 
                          dmsp_data["GLON"][dmspTindex + 1], 0, degrees=True)
    
    p_AB_N = init.delta_to(final) 
    azimuth = p_AB_N.azimuth_deg
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
    interp_mod_x = griddata((vel_data["lon0"].flatten(), vel_data["lat0"].flatten()), 
                            vel_data["u3h0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")
    interp_mod_y = griddata((vel_data["lon0"].flatten(), vel_data["lat0"].flatten()), 
                            vel_data["u1p0"][modTimeIndex].flatten(), (satLon, satLat), method = "linear")
    

    print(interp_mod_x)
    print(interp_mod_y)
    print(dmsp_east)
    print(dmsp_north)
    
    #ax.quiver(dmsp_data["GLON"][dmspTindex], dmsp_data["GDLAT"][dmspTindex], 
    #          interp_mod_x, interp_mod_y, color = colors[sat -15])
    

    
    

title = ("AMPERE/SAMI3 %s %s UT" % (date, hour))
plt.suptitle(title)

fig.tight_layout()

plt.savefig("test_pot.png", dpi = 300)
plt.show()
plt.close()








