from nc_utils import ncread_vars
import numpy as np

fn = '20210906.sye.v2.5.nc'

mjds = ncread_vars(fn)
assert len(np.unique(mjds)) == 1, 'Multiple days found in file'


