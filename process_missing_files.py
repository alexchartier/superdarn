import datetime as dt
import glob
import helper
import os
import subprocess
import json

START_DATE = dt.datetime(2017,5,5)#.now()
END_DATE = dt.datetime(1993, 9, 1)

def getLocalFileList(date):
    file_list = {}

    rawacf_dir = date.strftime(helper.RAWACF_DIR_FMT)
    fitacf_dir = date.strftime(helper.FITACF_DIR_FMT)
    netcdf_dir = date.strftime(helper.NETCDF_DIR_FMT)
    meteorwind_dir = date.strftime(helper.METEORWIND_DIR_FMT)
    meteorwindnc_dir = date.strftime(helper.METEORWINDNC_DIR_FMT)
    grid_dir = date.strftime(helper.GRID_DIR_FMT)
    gridnc_dir = date.strftime(helper.GRIDNC_DIR_FMT)

    day_string = date.strftime('%Y%m%d')
    day_string_two = date.strftime('%Y%b%d')
    
    rawacf_files = glob.glob(f'{rawacf_dir}/*{day_string}*')
    if not rawacf_files or not os.path.isdir(rawacf_dir):
        file_list['rawACF'] = []

    fitacf_files = glob.glob(f'{fitacf_dir}/*{day_string}*')
    if not fitacf_files or not os.path.isdir(fitacf_dir):
        file_list['fitACF'] = []

    netcdf_files = glob.glob(f'{netcdf_dir}/*{day_string}*')
    if not netcdf_files or not os.path.isdir(netcdf_dir):
        file_list['netCDF'] = []

    meteorwind_files = glob.glob(f'{meteorwind_dir}/*{day_string_two}*')
    if not meteorwind_files or not os.path.isdir(meteorwind_dir):
        file_list['meteorwind'] = []

    meteorwindnc_files = glob.glob(f'{meteorwindnc_dir}/*{day_string_two}*')
    if not meteorwindnc_files or not os.path.isdir(meteorwindnc_dir):
        file_list['meteorwind_nc'] = []

    grid_files = glob.glob(f'{grid_dir}/*{day_string}*')
    if not grid_files or not os.path.isdir(grid_dir):
        file_list['grid'] = []

    gridnc_files = glob.glob(f'{gridnc_dir}/*{day_string}*')
    if not gridnc_files or not os.path.isdir(gridnc_dir):
        file_list['grid_nc'] = []

    file_list['rawACF'] = rawacf_files
    file_list['fitACF'] = fitacf_files
    file_list['netCDF'] = netcdf_files
    file_list['meteorwind'] = meteorwind_files
    file_list['meteorwind_nc'] = meteorwindnc_files
    file_list['grid'] = grid_files
    file_list['grid_nc'] = gridnc_files

    return file_list


def getGlobusFileList(date):

    day = date.strftime('%Y%m%d')
    f = open('{0}/globus_data_inventory.json'.format(helper.GLOBUS_FILE_LIST_DIR))
    remoteData = json.load(f)
    return remoteData.get(day, [])

date = START_DATE
while date >= END_DATE:
    print(f'Checking files for {date.strftime("%Y-%m-%d")}...')
    
    breakpoint()
    globus_files = getGlobusFileList(date)
    local_files = getLocalFileList(date)
    missing_files = {}
    for file_type, files in local_files.items():
        missing_files[file_type] = []
        for globus_file in globus_files:
            file_exists = False
            for local_file in files:
                if globus_file in local_file:
                    file_exists = True
                    break
            if not file_exists:
                missing_files[file_type].append(globus_file)
        
    if missing_files:
        print(f'Missing files for {date.strftime("%Y-%m-%d")} on the local system:')
        for file_type, files in missing_files.items():
            if files:
                print(f'{file_type}: {files}')
    
    date -= dt.timedelta(days=1)
