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


def main():
    in_fname = input("netCDF Filename: ")

    unfiltered = load_data(in_fname)

    outlier = filter_radar_data.flag_interference(unfiltered)
    scatter = filter_radar_data.scatter_filter(outlier)

    print(len(unfiltered["vel"][unfiltered["gs"] == 0]))
    print(len(outlier["vel"][unfiltered["gs"] == 0]))

    histogram(unfiltered["vel"][unfiltered["gs"] == 0],
              outlier["vel"][outlier["gs"] == 0],
              scatter["vel"][scatter["gs"] == 0], in_fname)


# load data out of netCDF file and into python dictionary
def load_data(in_fname):

    data = nc_utils.ncread_vars(in_fname)
    return data


def histogram(unfiltered, outlier, scatter, title):

    fig, ax = plt.subplots(1, 1, constrained_layout="true")

    plt.hist(unfiltered, bins=30, range=[-1500, 1500], label="Unfiltered")
    plt.hist(outlier, bins=30, range=[-1500, 1500], label="Outlier Filter")
    plt.hist(scatter, bins=30, range=[-1500, 1500],
             label="E & Ground Scatter Filter")
    plt.legend(loc='upper right')

    ax.set_xlim(-1500, 1500)
    # ax.set_ylim(0,80000)

    plt.suptitle("F Region Scatter: " + title, fontsize=16)
    plt.show()
    plt.close()


if __name__ == '__main__':
    main()
