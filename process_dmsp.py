#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jul 15 11:56:13 2021

@author: sitardp1
"""



import numpy as np
import h5py
import pickle
import time
import matplotlib.pyplot as plt
import os
from os import path


def read_data(
    directory="data/dmsp/",
):
    for entry in os.scandir(directory):
        print(entry)
        picklename = entry.name.replace(".hdf5","") + ".pkl"
        
        if entry.path.endswith(".hdf5") and not(path.exists(picklename)):
            with h5py.File(entry, "r") as f:
                # Get the metadata
                parameters = f.get('Metadata')['Data Parameters'][...]
                
                # Get the data
                dataTable = f.get('Data').get('Table Layout')[...]
            breakpoint()
                    
            dmsp_data = {"UT1_UNIX":np.array([]), "MLAT":np.array([]), 
                         "GDLAT":np.array([]), "GLON":np.array([]), "ION_V_SAT_FOR":np.array([]), 
                         "ION_V_SAT_LEFT":np.array([]), "ION_V_LEFT_FLAG":np.array([]), 
                         "ION_V_FOR_FLAG":np.array([])}


           indices = [9, 12, 13, 14, 16, 17, 19, 20]
            if str(parameters[19][0]) == "b'ION_V_FOR_FLAG'": 
                for index, line in enumerate(dataTable):
                    for var in indices:
                        key = str(parameters[var][0])
                        key = key.replace("b'", "") 
                        key = key.replace("'", "") 
                        dmsp_data[key] = np.append(dmsp_data[key], line[var])
                        
            with open(picklename, "wb") as f:
                pickle.dump(dmsp_data, f)
                            


if __name__ == '__main__':
    read_data()


