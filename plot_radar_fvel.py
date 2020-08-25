# -*- coding: utf-8 -*-

"""
Created on Sat Jun 13 19:48:06 2020

@author: Devasena & Alex
"""

import numpy as np
from netCDF4 import Dataset
import julian as jd
import matplotlib.pyplot as plt
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import math
import os
import statistics

def main():
    in_fname = input("netCDF Filename: ")
    data = load_data(in_fname)
    filtered_data = flag_interference(data)
    removed_scatter = scatter_filter(filtered_data)
    smoothed_data = median_filter(removed_scatter)

    plot_data(smoothed_data)


def load_data(in_fname):
    """ load data out of netCDF file and into python dictionary
    """

    # extracting the data
    fileHandle = Dataset(in_fname, mode="r+")
    print(fileHandle)
    print(fileHandle.variables)

    var_names = [
        'vel', 'km', 'gs', 'geolat','geolon', "pwr", "mjd", 
        "bm", "aacgmlat", "aacgmlon", "aacgmazm", "wdt",
    ]
    data = {}
    
    # putting data into the dictionary
    for var_n in var_names:
        data[var_n] = {
            'long_name': fileHandle.variables[var_n].long_name,
            'units': fileHandle.variables[var_n].units,
            'vals': fileHandle.variables[var_n][...],
        }
    fileHandle.close()
    
    return data


def flag_interference(data):
    """
    Flag any interference and mark as 3 "other"
    Median Filter:
        Remove data that is more than 800 m/s away from the median velocity of the beam
    Working Criteria to Remove a Beam:
        velocity standard deviation above 435
    """
    
    uniqueTimes = np.unique(data["mjd"]['vals'])
    
    for index in range(len(uniqueTimes)):
        fsFlag = data["gs"]["vals"] == 0
        timeIndex = data["mjd"]['vals'] == uniqueTimes[index]
        fsBeamsTimed = list(data["bm"]['vals'][timeIndex & fsFlag])
        
        for beam in range(16):
            # Flag velocities > 800 m/s out from the beam median   
            beamFlag = data["bm"]['vals'] == beam
            fsFlag = data["gs"]["vals"] == 0
            timeBeamFsFlag = timeIndex & beamFlag & fsFlag 
            if len(data["vel"]["vals"][timeBeamFsFlag]) != 0:
                beamVelMedian = statistics.median(data["vel"]["vals"][timeBeamFsFlag])
                medianFlag1 = data["vel"]["vals"] >= beamVelMedian + 800          
                medianFlag2 = data["vel"]["vals"] <= beamVelMedian - 800
                data["gs"]["vals"][timeBeamFsFlag & (medianFlag1 | medianFlag2)] = 3
            
            # Flag beams with too large a standard deviation    
            fsFlag = data["gs"]["vals"] == 0
            beamVelStDev = np.std(data["vel"]['vals'][timeIndex & beamFlag])
            if beamVelStDev >= 435:
                data["gs"]['vals'][timeIndex & beamFlag] = 3

    return data


def scatter_filter(data): 
    
    """
    Ground Scatter flagged via min velocity of 30 m/s
    E region Scatter flagged via min range of 400 km
    
    """
    fsFlag = data["gs"]["vals"] == 0
    gsList = list(data["gs"]["vals"])
    
    print('# of Before 0s: %i' % gsList.count(0))
    print('# of Before 3s: %i' % gsList.count(3))
    print()
    
    minVelFlag1 = data["vel"]["vals"] <= 30 
    minVelFlag2 = data["vel"]["vals"] >= -30
    minRangeFlag = data["km"]["vals"] <= 400
    
    data["gs"]["vals"][minVelFlag1 & minVelFlag2 & fsFlag] = 1
    data["gs"]["vals"][fsFlag & minRangeFlag] = 2    
 
    gsList = list(data["gs"]["vals"])
    
    print('# of After 0s: %i' % gsList.count(0))
    print('# of After 3s: %i' % gsList.count(3))

    return data


def median_filter(data):
    """
    smooths data with boxcar averages
    """
    
    variables = ["geolon", "geolat", "mjd", "vel", "bm", "km"]
    fsFlag = data["gs"]["vals"] == 0
    fsData = {}
    gateSize = 150
    
    # isolating the F scatter data
    for var in variables:
        fsData[var] = data[var]["vals"][fsFlag]
        
    uniqueTimes = np.unique(fsData["mjd"])   
    avgFsData = {"geolon":[], "geolat":[], "mjd":[], "vel":[]}
    
    print("# of timecodes: %i" % len(uniqueTimes))
    
    #parsing through timecodes
    for index in range(len(uniqueTimes)):
        currentTime = uniqueTimes[index]
        timeIndex = fsData["mjd"] == currentTime
        
        # parsing through beams
        for beam in range(16):
            beamFlag = fsData["bm"] == beam
            
            if (len(fsData["geolon"][timeIndex & beamFlag])) != 0:
            
                minKm = min(fsData["km"][timeIndex & beamFlag])
                maxKm = max(fsData["km"][timeIndex & beamFlag])
                rangeKm = maxKm - minKm
                
                # parsing through the range gates and averaging the data
                for gate in range(math.ceil(rangeKm/gateSize) + 1):
                    gateFlag1 = fsData["km"] >= minKm + gate * gateSize
                    gateFlag2 = fsData["km"] < minKm + gate * gateSize + gateSize

                    idx = [timeIndex & beamFlag & gateFlag1 & gateFlag2]
                    
                    gatedLons = fsData["geolon"][idx]              
                    gatedLats = fsData["geolat"][idx] 
                    gatedVels = fsData["vel"][idx] 
                    
                    # adding averaged data to the new dictionary
                    if len(gatedLons) != 0:
                        avgFsData["geolon"].append(np.average(gatedLons))
                        avgFsData["geolat"].append(np.average(gatedLats))
                        avgFsData["vel"].append(np.average(gatedVels))
                        avgFsData["mjd"].append(currentTime)
             
    print("Len. lons: %i \nLen unique mjd: %i" % (len(avgFsData["geolon"]), len(np.unique(avgFsData["mjd"]))))
    print("Vels: %1.1f to %1.1f" % (min(avgFsData["vel"]), max(avgFsData["vel"])))
    print("Longitudes: %1.1f to %1.1f" % (min(avgFsData["geolon"]), max(avgFsData["geolon"])))
    print("Latitudes: %1.1f to %1.1f" % (min(avgFsData["geolat"]), max(avgFsData["geolat"])))

    return avgFsData    


def plot_data(fsData):
    """ 
    plot F region scatter on a map
    """
    
    radarInfo = def_radar_info()
    
    radar = input("Enter Radar Code: ")
    
    day = jd.from_jd(fsData["mjd"][0], fmt="mjd")
    folderDir =  day.strftime('%Y%b%d') + radar 
    os.mkdir(folderDir)
    
    for key, value in fsData.items():
            fsData[key] = np.array(value)

    uniqueTimes = np.unique(fsData["mjd"])

    for index in range(len(uniqueTimes)):
        timeIndex = fsData["mjd"] == uniqueTimes[index]
        currentreadableDate = jd.from_jd(uniqueTimes[index], fmt="mjd")

        fsLatTimed = fsData["geolat"][timeIndex]
        fsLonTimed = fsData["geolon"][timeIndex]
        fsVelTimed = fsData["vel"][timeIndex]

        ax = plt.axes(projection=ccrs.EquidistantConic(standard_parallels=(90, 90)))
        ax.add_feature(cfeature.LAND)
        ax.add_feature(cfeature.OCEAN)

        ax.set_extent(radarInfo[radar][0], ccrs.PlateCarree())
        gl = ax.gridlines(
            crs=ccrs.PlateCarree(), draw_labels=True,
            linewidth=2, color='gray', alpha=0.5, linestyle='-',
        )

        plt.scatter(
            fsLonTimed, fsLatTimed, 
            c=fsVelTimed, cmap="Spectral_r", linewidth=1, 
            vmin=-1000, vmax=1000, transform=ccrs.PlateCarree(),
        )

        plt.plot(
            radarInfo[radar][1][0], radarInfo[radar][1][1], 
            color="red", marker="x", transform=ccrs.PlateCarree(),
        )

        clb = plt.colorbar()
        clb.ax.set_title("Velocity")
        clb.set_label("m/s", rotation=270)
        timeStr = currentreadableDate.strftime('%Y%b%d_%H%M')
        plt.suptitle("%s - F Scatter\n%s" % (radarInfo[radar][2], timeStr))

        gl.xformatter = LONGITUDE_FORMATTER
        gl.yformatter = LATITUDE_FORMATTER

        style = {'size': 15, 'color': 'gray'}
        gl.xlabel_style = style 
        gl.ylabel_style = style
        gl.xlabels_top = False
        gl.ylabels_left = False

        plt.savefig(os.path.join(folderDir, "%s.png" % timeStr), dpi = 300)
        plt.close()


def def_radar_info():
    return {
        "pyk" : [[-23, 30, 62, 88], [-20.54, 63.77], "Pykkvibaer"],
        "wal" : [[-88, -21, 43, 60], [-75.47, 37.93], "Wallops"],
        "fhw" : [[-158, -100, 37, 78], [-99.39, 38.86], "Fort Hays West"],
        "ksr" : [[120, 240, 60, 88], [-156.65, 58.68], "King Salmon Radar"],
        "kap" : [[-122, -60, 55, 83], [-82.32, 49.39], "Kapuskasing"],
        "kod" : [[-160, -76, 55, 85], [-152.19, 57.62], "Kodiak"], 
        "inv" : [[-140, 6, 68, 88], [-133.772, 68.414], "Inuvik"],
        "adw" : [[-170, -210, 50, 82], [-176.63, 51.88], "Adak Island West"], 
        "pgr" : [[-180, -100, 55, 82], [-122.59, 53.98], "Prince George Radar"],
    }

if __name__ == '__main__':
    main()



