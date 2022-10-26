import nvector as nv
import numpy as np
import nc_utils
import os
import matplotlib.pyplot as plt

"""
Demonstrate velocity vector bearing calculation using nvector
"""
fname = os.path.expanduser('~/Downloads/20031029.han.v3.0.despeckled.nc')
depth = 0 # nvector uses depths in m - set to 200E3 to calculate at 200-km altitude

# load the reference ellipsoid and the data
wgs84 = nv.FrameE(name='WGS84')
sd_data = nc_utils.ncread_vars(fname)
sdrad = nc_utils.load_nc(fname)

# get the radar location
rlat = sdrad.lat
rlon = sdrad.lon


# just take the first 100 observations to demonstrate
lats = sd_data['lat'][:100]
lons = sd_data['lon'][:100]
vels = sd_data['v'][:100]

[_, unique_ind_lat] = np.unique(lats, return_index=True)
[_, unique_ind_lon] = np.unique(lons, return_index=True)
unique_ind = unique_ind_lat[np.logical_and(unique_ind_lat, unique_ind_lon)]
lats = lats[unique_ind]
lons = lons[unique_ind]
vels = vels[unique_ind]

brng_deg = np.zeros(len(lats)) * np.nan
for ind, lat in enumerate(lats):
    lon = lons[ind]
    pointA = wgs84.GeoPoint(latitude=lat, longitude=lon, z=3, degrees=True)
    pointB = wgs84.GeoPoint(latitude=rlat, longitude=rlon, z=6, degrees=True)
    p_AB_N = pointA.delta_to(pointB)  # note we want the bearing at point A
    brng_deg[ind] = p_AB_N.azimuth_deg - 180  # ... but away from the radar

brng_rad = np.deg2rad(brng_deg)
plt.plot(lons, lats, '.k', markersize=5)
plt.plot(rlon, rlat, '.r', markersize=20)
plt.quiver(lons, lats, np.sin(brng_rad) * vels / 100, np.cos(brng_rad) * vels / 100)
plt.xlabel('Lon. (deg)')
plt.ylabel('Lat. (deg)')
plt.title('Ion drift vel. components perpendicular to B')
plt.show()
