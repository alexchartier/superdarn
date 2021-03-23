import numpy as np
from netCDF4 import Dataset
import julian as jd
import matplotlib.pyplot as plt 
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import math
import os
import statistics
import filter_radar_data
import nc_utils
import glob
import datetime as dt
from run_meteorproc import get_radar_params, id_hdw_params_t
import sys 
import pdb 

inDir = 'data/netcdf/%Y/%m/'
radarCode = 'kod'
hdwDatDir='../rst/tables/superdarn/hdw/'
radarInfo = get_radar_params(hdwDatDir)
time = dt.datetime(2014, 4, 17)
inFname = os.path.join(time.strftime(inDir), time.strftime('%Y%m%d') + '.%s.nc' % radarCode)
haarp_LL = 62.3019, -145.3019

radarInfo_t = id_hdw_params_t(time, radarInfo[radarCode])
data = nc_utils.ncread_vars(inFname)

bmInd = data['bm'] == 8
db = {}
for k, v in data.items():
    db[k] = v[bmInd]

rg_idx = np.arange(max(db['km']) / 15) 
rg = (rg_idx * 15).astype('int')

times = np.array([jd.from_jd(mjd, fmt="mjd") for mjd in np.unique(db["mjd"])])
pwr = np.zeros((len(times), len(rg)))

for t, mjd in enumerate(np.unique(db["mjd"])):
    ti = db['mjd'] == mjd

    rgi = np.searchsorted(rg, db['km'][ti])
    try:
        pwr[t, rgi] = db['pwr'][ti]
    except:
        pdb.set_trace()

plt.pcolor(times, rg, pwr)
plt.show()








