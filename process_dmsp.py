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

def read_data():
    
    
    directory = "/Users/sitardp1/Documents/Madrigal"
    
    for entry in os.scandir(directory):
        print(entry)
        picklename = entry.name.replace(".hdf5","")+".p"
        
        if entry.path.endswith(".hdf5") and not(path.exists(picklename)):

            with h5py.File(entry, "r") as f:
                 
                # Get the metadata
                vn = f.get('Metadata')
                parameters = vn['Data Parameters']
                #print(vn['Data Parameters'][...])
                
                    
                # Get the data
                data = f.get('Data')
                dataTable = data.get('Table Layout')[...]
                        
                dmsp_data = {"UT1_UNIX":np.array([]), "MLAT":np.array([]), 
                             "GDLAT":np.array([]), "GLON":np.array([]), "ION_V_SAT_FOR":np.array([]), 
                             "ION_V_SAT_LEFT":np.array([]), "ION_V_LEFT_FLAG":np.array([]), 
                             "ION_V_FOR_FLAG":np.array([])}
                
                #put data in a dictionary
                """
                9: UT1_UNIX
                12: GDLAT
                13: GLON
                14: MLAT
                16: ION_V_SAT_FOR :direction of space craft
                17: ION_V_SAT_LEFT: left of direction of spacecraft
                19: ION_V_FOR_FLAG
                20: ION_V_LEFT_FLAG
                """
                indices = [9, 12, 13, 14, 16, 17, 19, 20]
                try:
                    if str(parameters[19][0]) == "b'ION_V_FOR_FLAG'": 
                        
                        
                        for index, line in enumerate(dataTable):
                    
                            for var in indices:
                                
                                key = str(parameters[var][0])
                                key = key.replace("b'", "")
                                key = key.replace("'", "")
                                dmsp_data[key] = np.append(dmsp_data[key], line[var])
                        
                        pickle.dump(dmsp_data, open( picklename, "wb" ) )
                                    
                except IndexError or ValueError:
                    print("eh not a file we want")

    
def main():
    read_data()    
    
    
main()


