from datetime import datetime, timedelta, timezone
import os, sys, netCDF4

def main(fn):
    epoch0 = datetime(1970, 1, 1, tzinfo=timezone.utc)
    to_dt = lambda val: epoch0 + timedelta(days=val - 40587.0)

    with netCDF4.Dataset(fn) as ds: 
        var = ds.variables['mjd'][...]
    print(to_dt(float(var[0])))

if __name__ == '__main__':
    fn = sys.argv[1] 
    main(fn)
