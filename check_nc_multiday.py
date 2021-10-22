from nc_utils import ncread_vars
import numpy as np

fn = '/project/superdarn/data/netcdf/2021/07/20210721.san.v2.5.nc'

data = ncread_vars(fn)
assert len(np.unique(data['mjd'])) == 1, 'Multiple days found in file'


