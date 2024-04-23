# -*- coding: utf-8 -*-

"""
Created on Sat Jun 13 19:48:06 2020
@author: Devasena

"""

import numpy as np
from netCDF4 import Dataset
import julian as jd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import math
import datetime as dt
from scipy.interpolate import griddata
import statistics
import pickle


def main():
    time = dt.datetime(2014, 5, 22, 10, 18)

    in_fname_fmt = "data/sami_ampere_weimer/sami3_utheta_uphi_300_%m%d.nc"
    radar_fname_fmt = '%Y%m%d.inv.nc'
    radarDict = "%Y%m%d.inv.pickle"

    modData = load_data(time.strftime(in_fname_fmt), [
                        "lat0", "lon0", "utheta", "uphi", "time"])
    radarData = load_data(time.strftime(radar_fname_fmt), ["vel", "km", "bm", "geolon", "geolat",
                                                           "mjd", "gs", "vel_e", "vel_n", "geoazm"])
    """
    interference = flag_interference(radarData)
    scatter = scatter_filter(interference)
    boxcar = median_filter(scatter)
    
    #save dictionary data in a pickle file
    pickle_out = open(radarDict, "wb")
    pickle.dump(boxcar, pickle_out)
    pickle_out.close()
    """
    pickle_in = open(radarDict, "rb")
    radarFiltered = pickle.load(pickle_in)

    modNvel, modEvel, index, hrind = interp_model_to_obs(
        modData, radarFiltered, time)
    radVel, radLon, radLat, degs = plot_data(
        modData, radarFiltered, time, index, hrind)

    data_analysis(modNvel, modEvel, radVel, radLon, radLat, degs)

# load data out of netCDF file and into python dictionary


def load_data(in_fname, var_names):

    # extracting the data
    fileHandle = Dataset(in_fname, mode="r+")
    print(fileHandle)
    print(fileHandle.variables)

    data = {}

    # putting data into the dictionary
    for var_n in var_names:
        data[var_n] = {
            'units': fileHandle.variables[var_n].units,
            'vals': fileHandle.variables[var_n][...],
        }

    fileHandle.close()

    return data


def flag_interference(data):
    """
    Median Filter:
        Remove data that is more than 800 m/s away from the median velocity of the beam
    Working Criteria to Remove a Beam:
        velocity standard deviation above 435
    """

    uniqueTimes = np.unique(data["mjd"]['vals'])

    # parse through time codes
    for index in range(len(uniqueTimes)):
        fsFlag = data["gs"]["vals"] == 0
        timeIndex = data["mjd"]['vals'] == uniqueTimes[index]

        # parse through individual beams
        for beam in range(16):
            beamFlag = data["bm"]['vals'] == beam
            fsFlag = data["gs"]["vals"] == 0

            beamTimed = beamFlag & timeIndex

            # median filter
            if len(data["vel"]["vals"][beamTimed & fsFlag]) != 0:
                beamVelMedian = statistics.median(
                    data["vel"]["vals"][beamTimed & fsFlag])
                medianFlag1 = data["vel"]["vals"] >= beamVelMedian + 800
                medianFlag2 = data["vel"]["vals"] <= beamVelMedian - 800
                data["gs"]["vals"][(beamTimed & fsFlag) & (
                    medianFlag1 | medianFlag2)] = 3

            fsFlag = data["gs"]["vals"] == 0
            beamVelStDev = np.std(data["vel"]['vals'][beamTimed])

            # standard deviation filter
            if beamVelStDev >= 435:
                data["gs"]['vals'][beamTimed] = 3

    return data

# removes scatter / outlier contamination


def scatter_filter(data):
    """
    Ground Scatter removed via min velocity of 30 m/s
    E region Scatter removed via min range of 400 km

    """
    fsFlag = data["gs"]["vals"] == 0

    minVelFlag1 = data["vel"]["vals"] <= 30
    minVelFlag2 = data["vel"]["vals"] >= -30
    minRangeFlag = data["km"]["vals"] <= 400

    data["gs"]["vals"][minVelFlag1 & minVelFlag2 & fsFlag] = 1
    data["gs"]["vals"][fsFlag & minRangeFlag] = 2

    return data

# smooths data with boxcar averages


def median_filter(data):

    variables = ["geolon", "geolat", "mjd", "vel",
                 "bm", "km", "vel_e", "vel_n", "geoazm"]
    fsFlag = data["gs"]["vals"] == 0
    fsData = {}
    gateSize = 150

    # isolating the F scatter data
    for var in variables:
        fsData[var] = data[var]["vals"][fsFlag]

    uniqueTimes = np.unique(fsData["mjd"])
    avgFsData = {"geolon": [], "geolat": [],
                 "vel": [], "vel_e": [], "vel_n": [], "geoazm": []}

    times = []

    # parsing through timecodes
    for index in range(len(uniqueTimes)):
        currentTime = uniqueTimes[index]
        timeIndex = fsData["mjd"] == currentTime

        # parsing through individual beams within timecodes
        for beam in range(16):
            beamFlag = fsData["bm"] == beam

            if (len(fsData["geolon"][timeIndex & beamFlag])) != 0:

                minKm = min(fsData["km"][timeIndex & beamFlag])
                maxKm = max(fsData["km"][timeIndex & beamFlag])
                rangeKm = maxKm - minKm

                # parsing through the range gates within beam and averaging the data
                for gate in range(math.ceil(rangeKm / gateSize) + 1):
                    gateFlag1 = fsData["km"] >= minKm + gate * gateSize
                    gateFlag2 = fsData["km"] < minKm + \
                        gate * gateSize + gateSize

                    if len(fsData["geolon"][timeIndex & beamFlag & gateFlag1 & gateFlag2]) != 0:
                        for key in avgFsData:
                            gatedVar = fsData[key][timeIndex &
                                                   beamFlag & gateFlag1 & gateFlag2]
                            avgFsData[key].append(np.average(gatedVar))

                        times.append(currentTime)

    avgFsData["mjd"] = times

    # to establish field of view
    print("Longitudes: " +
          str(min(avgFsData["geolon"])) + ", " + str(max(avgFsData["geolon"])))
    print("Latitudes: " +
          str(min(avgFsData["geolat"])) + ", " + str(max(avgFsData["geolat"])))

    return avgFsData


def plot_data(modData, radarData, time, index, hrind, axext=[-140, 6, 68, 88]):

    for key, value in radarData.items():
        radarData[key] = np.array(value)

    uniqueTimes = np.unique(radarData["mjd"])
    timeIndex = radarData["mjd"] == uniqueTimes[index]

    timedData = {}
    for key, value, in radarData.items():
        timedData[key] = radarData["value"][timeIndex]

    # set up the plot
    ax = plt.axes(projection=ccrs.EquidistantConic(
        standard_parallels=(90, 90)))
    ax.coastlines()
    ax.gridlines()
    ax.set_extent(axext, ccrs.PlateCarree())

    plt.quiver(
        modData["lon0"]["vals"].flatten(), modData["lat0"]["vals"].flatten(),
        modData["uphi"]["vals"][hrind, :, :].flatten(),
        modData["utheta"]["vals"][hrind, :, :].flatten(), color="gray",
        transform=ccrs.PlateCarree(), regrid_shape=24, width=.005,
    )

    # make the plot
    plt.quiver(
        timedData["geolon"], timedData["geolat"], timedData["vel_e"], timedData["vel_n"],
        color="magenta",
        transform=ccrs.PlateCarree(),
    )
    plt.plot(-133.772, 68.414, color="red",
             marker="x", transform=ccrs.PlateCarree())

    magenta = mpatches.Patch(color='magenta', label='Radar Velocities')
    gray = mpatches.Patch(color='gray', label='Model Velocities')

    plt.legend(handles=[magenta, gray], bbox_to_anchor=(
        1.05, 1), loc='upper left', borderaxespad=0.)

    plt.suptitle(time.strftime(
        "SAMI/AMPERE ExB drift vels at %H:%M UT on %d %b %Y"))
    plt.savefig("Inuvik_NE_4.png", dpi=300)
    plt.show()
    plt.close()

    return timedData["vel"], timedData["geolon"], timedData["geolat"], timedData["geoazm"]


def interp_model_to_obs(modData, radarData, time):

    # determine model time index
    hour = time.hour + time.minute / 60
    tdiffs = np.abs(modData["time"]["vals"] - hour)
    hrind = tdiffs == np.min(tdiffs)

    if len(hrind) == 2:
        hrind == hrind[0]

    # determine radar time index
    for key, value in radarData.items():
        radarData[key] = np.array(value)

    timeInts = []
    uniqueTimes = np.unique(radarData["mjd"])

    for element in uniqueTimes:
        readableRadarTime = jd.from_jd(element, fmt="mjd")
        timeInts.append([int(readableRadarTime.strftime('%H')),
                         int(readableRadarTime.strftime('%M'))])

    index = timeInts.index([time.hour, time.minute])
    timeIndex = radarData["mjd"] == uniqueTimes[index]

    print(timeInts)

    lats = modData["lat0"]["vals"].flatten()
    lons = modData["lon0"]["vals"].flatten()
    lons[lons > 180] = lons[lons > 180] - 360

    nvals = modData["utheta"]["vals"][hrind, :, :].flatten()
    evals = modData["uphi"]["vals"][hrind, :, :].flatten()

    radarLats = radarData["geolat"][timeIndex]
    radarLons = radarData["geolon"][timeIndex]

    # interpolate data based on radar coordinates
    nvel = griddata(np.array([lons, lats]).T, nvals, (radarLons, radarLats))
    evel = griddata(np.array([lons, lats]).T, evals, (radarLons, radarLats))

    return nvel, evel, index, hrind


def plot_data(modData, radarData, time, index, hrind,
              axext=[-140, 6, 68, 88], filename="Inuvik.png"):

    # convert data into numpy array
    for key, value in radarData.items():
        radarData[key] = np.array(value)

    uniqueTimes = np.unique(radarData["mjd"])
    timeIndex = radarData["mjd"] == uniqueTimes[index]

    # isolate data for a certain time code
    fsLatTimed = radarData["geolat"][timeIndex]
    fsLonTimed = radarData["geolon"][timeIndex]
    fsVelTimed = radarData["vel"][timeIndex]

    fsVelNTimed = radarData["vel_n"][timeIndex]
    fsVelETimed = radarData["vel_e"][timeIndex]
    fsDegTimed = radarData["geoazm"][timeIndex]

    # set up the plot
    ax = plt.axes(projection=ccrs.EquidistantConic(
        standard_parallels=(90, 90)))
    ax.coastlines()
    ax.gridlines()
    ax.set_extent(axext, ccrs.PlateCarree())

    # plot model data
    plt.quiver(
        modData["lon0"]["vals"].flatten(), modData["lat0"]["vals"].flatten(),
        modData["uphi"]["vals"][hrind, :, :].flatten(),
        modData["utheta"]["vals"][hrind, :, :].flatten(), color="gray",
        transform=ccrs.PlateCarree(), regrid_shape=24, width=.005,
    )

    # plot radar data
    plt.quiver(
        fsLonTimed, fsLatTimed, fsVelETimed, fsVelNTimed, color="magenta",
        transform=ccrs.PlateCarree(),

    )
    # add radar location
    plt.plot(-133.772, 68.414, color="red",
             marker="x", transform=ccrs.PlateCarree())

    # add plot legend
    magenta = mpatches.Patch(color='magenta', label='Radar Velocities')
    gray = mpatches.Patch(color='gray', label='Model Velocities')
    plt.legend(handles=[magenta, gray], bbox_to_anchor=(
        1.05, 1), loc='upper left', borderaxespad=0.)

    # title and save file
    plt.suptitle(time.strftime(
        "SAMI/AMPERE ExB drift vels at %H:%M UT on %d %b %Y"))
    plt.savefig(filename, dpi=300)
    plt.show()
    plt.close()

    return fsVelTimed, fsLonTimed, fsLatTimed, fsDegTimed


def data_analysis(modN, modE, radVel, radLon, radLat, degs):

    ax = plt.axes(projection=ccrs.EquidistantConic(
        standard_parallels=(90, 90)))
    ax.add_feature(cfeature.LAND)
    ax.add_feature(cfeature.OCEAN)

    ax.set_extent([-140, 6, 68, 88], ccrs.PlateCarree())
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(), draw_labels=True,
        linewidth=2, color='gray', alpha=0.5, linestyle='-',
    )

    modVels = [modN * np.cos(np.deg2rad(degs)), modE *
               np.sin(np.deg2rad(degs))]
    radar_los = np.array([np.cos(degs), np.sin(degs)])
    model_los_projections = np.dot(np.array(modVels), radar_los)

    print(model_los_projections)
    difs = radVel - model_los_projections

    plt.scatter(radLon, radLat, c=difs, cmap="PuRd",
                transform=ccrs.PlateCarree())

    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER

    gl.xlabel_style = {'size': 15, 'color': 'gray'}
    gl.ylabel_style = {'size': 15, 'color': 'gray'}
    gl.xlabels_top = False
    gl.ylabels_left = False

    clb = plt.colorbar()
    clb.ax.set_title("Velocity")
    clb.set_label("m/s", rotation=270)

    plt.suptitle("Velocity Differences")

    plt.show()


if __name__ == '__main__':

    main()
