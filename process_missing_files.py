import argparse
import datetime as dt
import glob
import helper
import os
import subprocess
import json

START_DATE = dt.datetime(2017, 5, 5)
END_DATE = dt.datetime(1993, 9, 1)
VALID_FILE_TYPES = ['rawacf', 'fitacf', 'fit_nc', 'meteorwind', 'meteorwind_nc', 'grid', 'grid_nc']


def getLocalFileList(date):
    file_list = {}
    rawacf_dir = date.strftime(helper.RAWACF_DIR_FMT)
    fitacf_dir = date.strftime(helper.FITACF_DIR_FMT)
    fit_nc_dir = date.strftime(helper.FIT_NC_DIR_FMT)
    meteorwind_dir = date.strftime(helper.METEORWIND_DIR_FMT)
    meteorwind_nc_dir = date.strftime(helper.METEORWIND_NC_DIR_FMT)
    grid_dir = date.strftime(helper.GRID_DIR_FMT)
    grid_nc_dir = date.strftime(helper.GRID_NC_DIR_FMT)

    day_string = date.strftime('%Y%m%d')
    day_string_two = date.strftime('%Y%b%d')

    rawacf_files = glob.glob(f'{rawacf_dir}/*{day_string}*')
    if not rawacf_files or not os.path.isdir(rawacf_dir):
        file_list['rawacf'] = []

    fitacf_files = glob.glob(f'{fitacf_dir}/*{day_string}*')
    if not fitacf_files or not os.path.isdir(fitacf_dir):
        file_list['fitacf'] = []

    fitnc_files = glob.glob(f'{fit_nc_dir}/*{day_string}*')
    if not fitnc_files or not os.path.isdir(fit_nc_dir):
        file_list['fit_nc'] = []

    meteorwind_files = glob.glob(f'{meteorwind_dir}/*{day_string_two}*')
    if not meteorwind_files or not os.path.isdir(meteorwind_dir):
        file_list['meteorwind'] = []

    meteorwindnc_files = glob.glob(f'{meteorwind_nc_dir}/*{day_string_two}*')
    if not meteorwindnc_files or not os.path.isdir(meteorwind_nc_dir):
        file_list['meteorwind_nc'] = []

    grid_files = glob.glob(f'{grid_dir}/*{day_string}*')
    if not grid_files or not os.path.isdir(grid_dir):
        file_list['grid'] = []

    gridnc_files = glob.glob(f'{grid_nc_dir}/*{day_string}*')
    if not gridnc_files or not os.path.isdir(grid_nc_dir):
        file_list['grid_nc'] = []

    file_list['rawacf'] = rawacf_files
    file_list['fitacf'] = fitacf_files
    file_list['fit_nc'] = fitnc_files
    file_list['meteorwind'] = meteorwind_files
    file_list['meteorwind_nc'] = meteorwindnc_files
    file_list['grid'] = grid_files
    file_list['grid_nc'] = gridnc_files

    return file_list


def getGlobusFileList(date):
    day = date.strftime('%Y%m%d')
    with open(f'{helper.GLOBUS_FILE_LIST_DIR}/globus_data_inventory.json') as f:
        remote_data = json.load(f)
    return remote_data.get(day, [])


def main(file_types):
    if file_types:
        file_types = [file_type.lower() for file_type in file_types]
        invalid_file_types = set(file_types) - set(VALID_FILE_TYPES)
        if invalid_file_types:
            print(f'\nInvalid file types specified: {", ".join(invalid_file_types)}.')
            print('Valid file types are:')
            for file_type in VALID_FILE_TYPES:
                print(f'    {file_type}')            
            print('\nExample usage: python3 process_missing_files.py -t fitacf meteorwind_nc\n')
            return

    date = START_DATE
    while date >= END_DATE:
        print(f'Checking files for {date.strftime("%Y-%m-%d")}...')

        globus_files = getGlobusFileList(date)
        local_files = getLocalFileList(date)
        missing_files = {}

        for file_type, files in local_files.items():
            if file_types and file_type.lower() not in file_types:
                continue

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
        breakpoint()
        date -= dt.timedelta(days=1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--file-types', nargs='*', help='Specify the file types to check (e.g. fitacf, meteorwind_nc, etc)')
    args = parser.parse_args()
    main(args.file_types)

