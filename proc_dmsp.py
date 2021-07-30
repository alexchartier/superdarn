import numpy as np
import h5py
import pickle
import time
import matplotlib.pyplot as plt
import os
from os import path

def main(
    fn = 'data/dmsp/dms_ut_20140523_15.002.hdf5',
):
    flist = get_file_list(data_dir)
    for fn in flist:
        raw_dmsp_data = load_data(fn)
        processed_dmsp_data = proc_data(raw_dmsp_data)


def load_data(fn):
    with h5py.File(fn, "r") as f:
        # Get the metadata
        parameters = f.get('Metadata')['Data Parameters'][...]
        # Get the data
        dataTable = f.get('Data').get('Table Layout')[...]

    vars = {}
    out = {}
    for ind, prm in enumerate(parameters):
        str = prm[0].decode('utf-8')
        vars[str] = ind 
        out[str] = []
    
    for entry in dataTable:
        for k, v in out.items():
            v.append(entry[vars[k]])

    for k, v in out.items():
        out[k] = np.array(v)
    return out


def proc_data(dmsp_data):

    goodind = np.logical_and(dmsp_data['RPA_FLAG_UT'] < 2, dmsp_data['IDM_FLAG_UT'] < 2)
    for k, v in dmsp_data.items():
        dmsp_data[k] = v[goodind]

    out = {}
    vars = 'Time', 'Alt', 'Lat', 'Lon', 'Vel_perp'
    for v in vars:
        out[v] = []
    for ind, yr in enumerate(dmsp_data['YEAR']):
        time = dt.datetime(yr, dmsp_data['MONTH'], dmsp_data['DAY'], dmsp_data['HOUR'], dmsp_data['MIN'], dmsp_data['SEC'])


if __name__ == '__main__':
    main() 











