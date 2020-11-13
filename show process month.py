# -*- coding: utf-8 -*-

"""
Created on Sat Jun 13 19:48:06 2020

@author: Devasena
"""

import numpy as np
from netCDF4 import Dataset
import julian as jd
import matplotlib.pyplot as plt
import statistics
import pickle
import filter_radar_data
import nc_utils
import os

def main(): 
    info = ["Inuvik", "inv", "2014", "05"]
 
    #radarbymonth(info[1], info[2], info[3])    
    pickle_in = open("monthData.pickle", "rb")
 
    filtered = pickle.load(pickle_in)
    print(len(filtered[0]))
            
    histogram(filtered[0], filtered[1], filtered[2], "%s: %s/%s" % (info[0], info[3], info[2]))

def radarbymonth(radar_code, year, month): 
    
    directory = r"C:\Users\sitardp1\netcdf\%s\%s" % (year, month) 
     
    unfilteredMonth = []
    outlierMonth = []
    scatterMonth = []
         
    for entry in os.scandir(directory):
        if radar_code in str(entry):
            
            print(entry)
            
            unfiltered = nc_utils.ncread_vars(entry.path)
            dataLen = len(unfiltered["vel"][unfiltered["gs"] == 0])
            
            if dataLen > 0:
                outlier = filter_radar_data.flag_interference(unfiltered)
                scatter = filter_radar_data.scatter_filter(outlier)
            
                unfilteredMonth = unfilteredMonth + list(unfiltered["vel"][unfiltered["gs"] == 0])
                outlierMonth = outlierMonth + list(outlier["vel"][outlier["gs"] == 0])
                scatterMonth = scatterMonth + list(scatter["vel"][scatter["gs"] == 0])
        
    monthData = [unfilteredMonth, outlierMonth, scatterMonth]
    
    pickle_out = open("monthData.pickle", "wb")
    pickle.dump(monthData, pickle_out)
    pickle_out.close()
    

def histogram(unfiltered, outlier, scatter, title):
        
    fig, ax = plt.subplots(1,1, constrained_layout = "true")
        
    plt.hist(unfiltered, bins = 30, range = [-1500, 1500], label = "Unfiltered")
    plt.hist(outlier, bins = 30, range = [-1500, 1500], label = "Outlier Filter")
    #plt.hist(scatter, bins = 30, range = [-1500, 1500], label = "E & Ground Scatter Filter")
    plt.legend(loc='upper right')

    ax.set_xlim(-1500, 1500)    
    #ax.set_ylim(0,80000)

    plt.suptitle("F Region Scatter: " + title, fontsize=16)
    plt.show()
    plt.close()

if __name__ == '__main__':
    main()



