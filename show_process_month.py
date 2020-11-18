# -*- coding: utf-8 -*-

"""
Created on Sat Jun 13 19:48:06 2020

@author: Devasena
"""

import numpy as np
import matplotlib.pyplot as plt
import pickle
import filter_radar_data
import nc_utils
import os
import datetime as dt
import sys
import copy
import pdb


def main( 
    time = dt.datetime(2014, 5, 1),
    directory = "C:/Users/sitardp1/netcdf/%Y/%m/",
    radarName = "Inuvik",
):
    radarCodes = radar_codes() 
    try:
        with open('tmp.pkl', 'rb') as f:
            monthData = pickle.load(f)
    except:
        monthData = radarbymonth(radarCodes[radarName], time.strftime(directory))    
        with open('tmp.pkl', 'wb') as f:
            pickle.dump(monthData, f)

    print(len(monthData[0]))
    histogram(monthData[0], monthData[1], monthData[2], "%s: %s" % (radarName, time.strftime('%Y/%m')))


def radar_codes():
    return {
        "Inuvik": "inv",
        "Saskatoon": "sas",
        "Wallops": "wal",
        "Kapuskasing": "kap",
        "Blackstone": "blk",
    }


def radarbymonth(radar_code, directory): 
    unfilteredMonth = []
    outlierMonth = []
    scatterMonth = []
         
    for entry in os.scandir(directory):
        if radar_code in str(entry):
            
            print(entry)
            
            unfiltered = nc_utils.ncread_vars(entry.path)
            dataLen = len(unfiltered["vel"][unfiltered["gs"] == 0])
            
            if dataLen > 0:
                outlier = filter_radar_data.flag_interference(copy.deepcopy(unfiltered))
                scatter = filter_radar_data.scatter_filter(copy.deepcopy(outlier))
                unfilteredMonth += list(unfiltered["vel"][unfiltered["gs"] == 0])
                outlierMonth += list(outlier["vel"][outlier["gs"] == 0])
                scatterMonth += list(scatter["vel"][scatter["gs"] == 0])
        
    monthData = [unfilteredMonth, outlierMonth, scatterMonth]
   
    return monthData 
    

def histogram(unfiltered, outlier, scatter, title):
        
    fig, ax = plt.subplots(1,1, constrained_layout = "true")
        
    plt.hist(unfiltered, bins = 30, range = [-1500, 1500], label = "Unfiltered")
    plt.hist(outlier, bins = 30, range = [-1500, 1500], label = "Outlier Filter")
    plt.hist(scatter, bins = 30, range = [-1500, 1500], label = "E & Ground Scatter Filter")
    plt.legend(loc='upper right')

    ax.set_xlim(-1500, 1500)    
    #ax.set_ylim(0,80000)

    plt.suptitle("F Region Scatter: " + title, fontsize=16)
    plt.show()
    plt.close()


if __name__ == '__main__':
    args = sys.argv
    
    """
    assert len(args) == 4, 'Should have 3x args, e.g.:\n' + \
        'python3 show_process_month.py 2016,1  ' + \
        '/Users/sitardp1/superdarn/data/netcdf/%Y/%m/  ' + \
        'Inuvik \n'
    """
    #time = dt.datetime.strptime(args[1], '%Y,%m')

    main()   

    



