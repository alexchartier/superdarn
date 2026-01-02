"""
Scan fit_nc_3 NetCDF files and report those whose mjd range
falls outside the filename day or more than one day away.
"""

import glob
import os
from datetime import datetime, timedelta, timezone

import netCDF4


def file_time_bounds(fn):
    """Return (min_dt, max_dt, count) for mjd in a NetCDF file."""
    with netCDF4.Dataset(fn) as ds:
        if 'mjd' not in ds.variables:
            return None, None, 0
        var = ds.variables['mjd']
        if var.size == 0:
            return None, None, 0
        mn = float(var[0])
        mx = float(var[-1]) if var.size > 1 else mn
        n = var.size
    epoch0 = datetime(1970, 1, 1, tzinfo=timezone.utc)
    to_dt = lambda val: epoch0 + timedelta(days=val - 40587.0)
    return to_dt(mn), to_dt(mx), n


def main():
    bad = []
    files = glob.glob('/project/superdarn/data/fit_nc_3/*/*/*.nc')
    for fn in files:
        base = os.path.basename(fn)
        try:
            date_str = base.split('.')[0][:8]
            day = datetime.strptime(date_str, '%Y%m%d').replace(tzinfo=timezone.utc)
        except Exception:
            continue
        day_start = day
        day_end = day + timedelta(days=1)
        res = file_time_bounds(fn)
        if res[0] is None:
            continue
        mn, mx, n = res
        all_outside = (mx < day_start) or (mn >= day_end)
        far = (mn < day_start - timedelta(days=1)) or (mx >= day_end + timedelta(days=1))
        if all_outside or far:
            bad.append((fn, mn.isoformat(), mx.isoformat(), n, all_outside, far))

    for rec in sorted(bad):
        fn, mn, mx, n, all_outside, far = rec
        print(fn)
        print('  npts=', n, 'min=', mn, 'max=', mx, 'all_outside_day=', all_outside, 'any_gt1day=', far)
    print('Total flagged:', len(bad))


if __name__ == '__main__':
    main()
