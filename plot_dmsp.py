#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jul 19 12:06:59 2021

@author: sitardp1
"""

import numpy as np
import pdb
import h5py
import pickle
import time
import matplotlib.pyplot as plt
import os

fn = "dms_20140521_16s1.001.p"

with open(fn, 'rb') as f:
    data = pickle.load(f)
print(data.keys())

fig, ax = plt.subplots(1, 1, subplot_kw=dict(projection='polar'))

timeIndex = data["UT1_UNIX"] <=  data["UT1_UNIX"][2180]
poleIndex = data["GDLAT"] <= 0
adjVelLats = (90 - data["GDLAT"][poleIndex & timeIndex])
adjVelLons = data["GLON"][poleIndex & timeIndex]  + 180

vertical = data["VERT_ION_V"][poleIndex & timeIndex]
horizontal = data["HOR_ION_V"][poleIndex & timeIndex]
theta = np.arctan2(vertical,horizontal)
mag = np.hypot(vertical, horizontal)


ax.quiver(adjVelLons, adjVelLats, theta, mag)

plt.show()
plt.close()

pdb.set_trace()

fig, ax = plt.subplots(1, 1, tight_layout = True)
ax.scatter(data["UT1_UNIX"][timeIndex & poleIndex], data["VERT_ION_V"][timeIndex &poleIndex], 
           linewidths = 0.5)
ax.scatter(data["UT1_UNIX"][timeIndex & poleIndex], data["HOR_ION_V"][timeIndex & poleIndex], 
           linewidths = 0.5)

ax.set_ylim(-2000, 2000)
ax.set_xlabel("time (unix seconds 20:00 - 20:30)")
ax.set_ylabel("velocity m/s")
plt.suptitle("F16 MAY 20 LOW LATS")

plt.show()


#polar conversions


