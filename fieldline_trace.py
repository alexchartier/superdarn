import numpy as np
import datetime as dt
from geopack import geopack
import trace
import pdb

"""
For T89
par: A model parameter. It is an integer (1-7) maps to the Kp index
| par |  1   |    2    |    3    |    4    |    5    |    6    |  7   |
| Kp  | 0,0+ | 1-,1,1+ | 2-,2,2+ | 3-,3,3+ | 4-,4,4+ | 5-,5,5+ | > 6- |
 
get from NASA OMNIWeb or similar - download text file + create reader



For T04
par: A model paramter. It is a 10-element array, whose elements are (1-10)
| par |  1   |  2  |     3-4     |   5-10   |
| Var | Pdyn | Dst | ByIMF,BzIMF | W1 to W6 |
where Pdyn is the solar wind dynamic pressure in nPa; 
      Dst is the Dst index in nT; 
       ByImf,BzImf are the y and z components of the IMF (interplanetary magnetif field) in GSM; 
        W1,W2,...,W6 are six indices defined in Tsyganenko (2005).
"""

# From date and time
t1 = dt.datetime(2001, 1, 2, 3, 4, 5)  # year month day hour min sec
t0 = dt.datetime(1970, 1, 1)   # start of epoch
ut = (t1 - t0).total_seconds()
ps = geopack.recalc(ut)

x0gsm = 6.3
y0gsm = 5.3
z0gsm = -2.9
dir = 1
rlim = 1.1
r0 = 1
par = 2
exname = 't04'
inname = 'igrf'
out = geopack.trace(x0gsm, y0gsm, z0gsm, dir)  # , par, exname)#, inname)


pdb.set_trace()
