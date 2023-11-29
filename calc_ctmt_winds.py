"""
Plot the CTMT - Climatological Tidal Model of the Thermosphere
Aim to do SuperDARN winds analysis against it

"""
import nc_utils   # available from github.com/alexchartier/nc_utils
import numpy as np

# diurnal and semidiurnal tidal filenames
in_fn_sd = '~/Downloads/ctmt_semidiurnal_2002_2008.nc'
in_fn_d = '~/Downloads/ctmt_diurnal_2002_2008.nc'

# Location
lat = 50
lon = 30
alt = 100
hour = 12
month = 1

# Load the files
sd_file = nc_utils.ncread_vars(in_fn_sd)
d_file = nc_utils.ncread_vars(in_fn_d)

# Get the dimensions  
# (TODO add support for non-indexed values via interpolation)
mi = d_file['month'] == month
ai = d_file['lev'] == alt
li = d_file['lat'] == lat

# Get the zonal component for DW1 (diurnal westward wavenumber 1, just as an example)
# (TODO loop over all these for diurnal and semidiurnal)
direction = 'w'     # east, west or stationary propagation (e, w, s)
wavenumber = 1      # 0 - 4 (less in some cases)
component = 'u'     # 'u' or 'v' (zonal or meridional aka eastward or northward)
amp = d_file['amp_%s%i_%s' % (direction, wavenumber, component)][mi, ai, li]  #  amplitude (m/s) (east/west/north/up, depending on component)
phase = d_file['phase_w1_u'][mi, ai, li]  # phase (UT of MAX at 0 deg lon)

phase_at_lon = phase - lon / 360 * 24   # Phase (UT of max at the specified lon). - sign used because westward. (eastward -> +, stationary means it doesn't move)
wind = amp * np.cos((phase_at_lon - hour) / 24 * np.pi * 2)  #TODO Add support for wavenumber != 1 here

