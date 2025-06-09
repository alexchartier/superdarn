from calc_ctmt_winds import calc_alt_at_pressure
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
import scipy as sp

pressures = np.linspace(0.001, 0.002, 11)
alts = np.zeros_like(pressures)
lats = np.linspace(-90, 90, 7)
lons = np.linspace(0, 300, 6)
years = 2003, 2008
months = 3, 6, 9, 12
hours = 0, 6, 12, 18
times = []
for year in years:
    for month in months:
        for hour in hours:
            times.append(dt.datetime(year, month, 1, hour, 0))

for pi, pressure in enumerate(pressures):
    altmap = np.zeros((len(times), len(lats), len(lons)))
    for ti, time in enumerate(times):
        for lati, lat in enumerate(lats):
            for loni, lon in enumerate(lons):
                altmap[ti, lati, loni] = calc_alt_at_pressure(time, lat, lon, pressure)
    alts[pi] = np.mean(altmap.ravel())


pres_at_90 = sp.interpolate.interp1d(alts, pressures)(90.)
fig, ax = plt.subplots()
ax.plot(pressures, alts)
ax.set_title(f'Pressure: {pres_at_90:.4f} hPa')
#ax.set_xscale('log')
plt.show()

