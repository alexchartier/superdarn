import nc_utils
import os
import datetime as dt
import matplotlib.pyplot as plt
import numpy as np

stime = dt.datetime(2025, 7, 1)
etime = dt.datetime(2025, 11, 1)
in_fn_fmt = os.path.expanduser('~/data/superdarn/netcdf/ksr/%Y%m%d.ksr.a.despeck.fitacf3.nc')
time = stime


out = {'mjd': [], 'tfreq': []}

while time < etime:

    fn = time.strftime(in_fn_fmt)
    try:
        data = nc_utils.ncread_vars(fn)
    except:
        print('Failed to load %s ' % fn)
    
    out['mjd'].append(data['mjd'])
    out['tfreq'].append(data['tfreq'])
    time += dt.timedelta(days=1)

mjds = dt.datetime(1858, 11, 17, 0, 0, 0, tzinfo=dt.timezone.utc)
out['mjd'] = np.concatenate(out['mjd'])
out['tfreq'] = np.concatenate(out['tfreq'])
out['time'] = [mjds + dt.timedelta(days=mjd) for mjd in out['mjd']]
plt.plot(out['time'], out['tfreq'])
plt.ylabel('Freq (kHz)')
plt.show()
