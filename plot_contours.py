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

#read data
pot_file = "sami3_may23_phi.nc"
vel_file = "sami3_may23a.nc"
sat_file = ""

pot_data = nc_utils.ncread_vars(pot_file)
vel_data = nc_utils.ncread_vars(vel_file)

date = pot_file.split("_")[1]
timeIndex = 50
phi = pot_data["phi"][timeIndex,:,:]
hour = str(pot_data["time"][timeIndex])

#change potential data to polar and plot
adjPotLats = 90 - pot_data["lat"]
adjPotLons = np.deg2rad(pot_data["lon"])

fig, ax = plt.subplots(1, 2, subplot_kw=dict(projection='polar'))


pot = ax[0].contour(adjPotLons, adjPotLats, phi, cmap='hot')
ax[0].set_theta_zero_location("E")
ax[0].set_rlabel_position(50)


#change model velocity data to polar
poleIndex = vel_data["lat0"] >= 70
adjVelLats = (90 - vel_data["lat0"][poleIndex]).flatten()
adjVelLons = np.deg2rad(vel_data["lon0"][poleIndex]).flatten()

#more polar conversions
vertical = vel_data["u1p0"][timeIndex][poleIndex]
horizontal = vel_data["u3h0"][timeIndex][poleIndex]
theta = np.arctan2(vertical,horizontal)
mag = np.hypot(vertical, horizontal)

#plot model velocity data
vel = ax[1].quiver(adjVelLons, adjVelLats, mag, theta)
ax[1].set_rlabel_position(50)

cbar = fig.colorbar(pot)
title = ("AMPERE/SAMI3 %s %s UT" % (date, hour))
plt.suptitle(title)

fig.tight_layout()

plt.savefig("test.png", dpi = 300)
plt.show()
plt.close()
