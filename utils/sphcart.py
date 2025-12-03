import nvector as nv
import numpy as np
wgs84 = nvector.FrameE(name='WGS84')

"""
nvector spherical/cartesian transformations 
"""

def cartsph(XYZ):
    """ convert ECEF coordinates (XYZ in km) to geodetic (LLA in deg, deg, km) """
    # TODO: consider replacing with geopack.sphcar  (j>0 for this direction)
    LLA = np.ones_like(XYZ) * np.nan
    for ind in range(XYZ.shape[0]):
        pt_ecef = wgs84.ECEFvector(np.expand_dims(XYZ[ind, :] * 1E3, 0).T)
        pt_geo = pt_ecef.to_geo_point()
        LLA[ind, :] = pt_geo.latlon_deg

    LLA[:, 2] /= -1E3  # convert from depth in m to rad in km

    return LLA 


def sphcart(LLA):
    """ convert geodetic coordinates (LLA in deg, deg, km) to ECEF (XYZ in km) """
    # TODO: consider replacing with geopack.sphcar  (j<0 for this direction)
    XYZ = np.ones_like(LLA) * np.nan
    for ind in range(LLA.shape[0]):
        pt_geo = wgs84.GeoPoint(
            latitude=LLA[ind, 0], longitude=LLA[ind, 1], z=-LLA[ind, 2] * 1E3, degrees=True)
        pt_ecef = pt_geo.to_ecef_vector()
        XYZ[ind, :] = pt_ecef.pvector.ravel() / 1E3 

    return XYZ 
