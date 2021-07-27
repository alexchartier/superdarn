#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jul 15 11:56:13 2021

@author: sitardp1
"""



import numpy as np
import pdb
import h5py
import pickle
import time
import matplotlib.pyplot as plt
import os
from os import path

def read_data(
    directory = "/Users/sitardp1/Documents/Madrigal"
):
    for entry in os.scandir(directory):
        print(entry)
        picklename = entry.name.replace(".hdf5","") + ".pkl"
        
        if entry.path.endswith(".hdf5") and not(path.exists(picklename)):
            with h5py.File(entry, "r") as f:
                # Get the metadata
                vn = f.get('Metadata')
                    
                # Get the data
                data = f.get('Data')
                dataTable = data.get('Table Layout')[...]
                        
            parameters = vn['Data Parameters']
            dmsp_data = {"UT1_UNIX":np.array([]), "UT2_UNIX":np.array([]), 
                         "GDLAT":np.array([]), "GLON":np.array([]), "HOR_ION_V":np.array([]), 
                         "VERT_ION_V":np.array([])}
            
            #put data in a dictionary
            if str(parameters[20][0]) == "b'VERT_ION_V'": 
                for line in dataTable:
                    if np.isnan(line[20]) == False:
                        for var in range(9, 13):
                            key = str(parameters[var][0])
                            key = key.replace("b'", "")
                            key = key.replace("'", "")
                            dmsp_data[key] = np.append(dmsp_data[key], line[var])
            
                        for var in range(19, 21):
                            key = str(parameters[var][0])
                            key = key.replace("b'", "")
                            key = key.replace("'", "")
                            dmsp_data[key] = np.append(dmsp_data[key], line[var])
                with open(picklename, "wb") as f:
                    pickle.dump(dmsp_data, f)
                            


def plot_satellitedata(dates):
    with open("dms_20140423_18s1.001.p", 'rb') as f:
        data = pickle.load(f)
    breakpoint() 
    
    
if __name__ == '__main__':
    read_data()


