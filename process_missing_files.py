import argparse
import datetime as dt
import glob
import helper
import os
import subprocess
import json

VALID_FILE_TYPES = ['rawacf', 'fitacf', 'fit_nc', 'meteorwind', 'meteorwind_nc', 'grid', 'grid_nc']


def get_local_file_list(date, file_types=None):
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

    if file_types is None:
        file_types = VALID_FILE_TYPES

    if 'rawacf' in file_types:
        rawacf_files = glob.glob(f'{rawacf_dir}/*{day_string}*')
        if not rawacf_files or not os.path.isdir(rawacf_dir):
            file_list['rawacf'] = []
        else:
            file_list['rawacf'] = rawacf_files

    if 'fitacf' in file_types:
        fitacf_files = glob.glob(f'{fitacf_dir}/*{day_string}*')
        if not fitacf_files or not os.path.isdir(fitacf_dir):
            file_list['fitacf'] = []
        else:
            file_list['fitacf'] = fitacf_files

    if 'fit_nc' in file_types:
        fitnc_files = glob.glob(f'{fit_nc_dir}/*{day_string}*')
        if not fitnc_files or not os.path.isdir(fit_nc_dir):
            file_list['fit_nc'] = []
        else:
            file_list['fit_nc'] = fitnc_files

    if 'meteorwind' in file_types:
        meteorwind_files = glob.glob(f'{meteorwind_dir}/*{day_string_two}*')
        if not meteorwind_files or not os.path.isdir(meteorwind_dir):
            file_list['meteorwind'] = []
        else:
            file_list['meteorwind'] = meteorwind_files

    if 'meteorwind_nc' in file_types:
        meteorwindnc_files = glob.glob(f'{meteorwind_nc_dir}/*{day_string_two}*')
        if not meteorwindnc_files or not os.path.isdir(meteorwind_nc_dir):
            file_list['meteorwind_nc'] = []
        else:
            file_list['meteorwind_nc'] = meteorwindnc_files

    if 'grid' in file_types:
        grid_files = glob.glob(f'{grid_dir}/*{day_string}*')
        if not grid_files or not os.path.isdir(grid_dir):
            file_list['grid'] = []
        else:
            file_list['grid'] = grid_files

    if 'grid_nc' in file_types:
        gridnc_files = glob.glob(f'{grid_nc_dir}/*{day_string}*')
        if not gridnc_files or not os.path.isdir(grid_nc_dir):
            file_list['grid_nc'] = []
        else:
            file_list['grid_nc'] = gridnc_files

    return file_list


def get_globus_file_list(date):
    day = date.strftime('%Y%m%d')
    with open(f'{helper.GLOBUS_FILE_LIST_DIR}/globus_data_inventory.json') as f:
        remote_data = json.load(f)
    return remote_data.get(day, [])


def produce_missing_files(missing_files):
    return


def main(start_date, end_date, file_types):
    if file_types is None:
        file_types = VALID_FILE_TYPES
    elif not file_types:
        print('\nFile type flag is used, but no file types are specified.\nExample usage:\n')
        print('   python3 process_missing_files.py 20221022 20220901')
        print('   python3 process_missing_files.py 20221022 20220901 -t fitacf meteorwind_nc\n')
        return
    else:
        file_types = [file_type.lower() for file_type in file_types]
        invalid_file_types = set(file_types) - set(VALID_FILE_TYPES)
        if invalid_file_types:
            print(f'\nInvalid file types specified: {", ".join(invalid_file_types)}')
            print('Valid file types are:')
            for file_type in VALID_FILE_TYPES:
                print(f'  {file_type}')
            print('\nExample usage: python3 process_missing_files.py -t fitacf meteorwind_nc\n')
            return

    date = start_date
    while date >= end_date:
        print(f'Checking files for {date.strftime("%Y-%m-%d")}...')

        globus_files = get_globus_file_list(date)
        local_files = get_local_file_list(date, file_types)
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

        produce_missing_files(missing_files)

        date -= dt.timedelta(days=1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('start_date', help='Specify the start date (YYYYMMDD)')
    parser.add_argument('end_date', help='Specify the end date (YYYYMMDD)')
    parser.add_argument('-t', '--file-types', nargs='*', help='Specify the file types to check (e.g. fitacf, meteorwind_nc, etc)')
    args = parser.parse_args()

    start_date = dt.datetime.strptime(args.start_date, '%Y%m%d')
    end_date = dt.datetime.strptime(args.end_date, '%Y%m%d')

    main(start_date, end_date, args.file_types)
