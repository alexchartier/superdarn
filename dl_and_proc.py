"""
Download and process data one day at a time
"""
import raw_to_nc
import datetime as dt
import os


def main():
    dirs = {
        'bas': 'apl@bslsuperdarnb.nerc-bas.ac.uk:/sddata/raw/%Y/%m/',
        'dat': '/project/superdarn/data/dat/%Y/%m/',
        'rawacf': '/project/superdarn/data/rawacf/%Y/%m/',
        'fitacf': '/project/superdarn/data/fitacf/%Y/%m/',
        'netcdf': '/project/superdarn/data/netcdf/%Y/%m/',
        'log': 'logs/',
    }

    times = get_times()

    for time in times:
        dl_one_day(dirs, time)
        raw_to_nc.main(time, time, dirs['rawacf'],
                       dirs['fitacf'], dirs['netcdf'])

    # TODO: Delete old rawACF files


def dl_one_day(dirs, time):
    tdirs = {}
    for key, dirn in dirs.items():
        tdirs[key] = time.strftime(dirn)
        if key != 'bas':
            os.makedirs(tdirs[key], exist_ok=True)

    dateString = time.strftime('%Y%m%d')
    os.system("rsync -avhe ssh --include '*$/' --include '%s*' --exclude '*' %s %s" %
              (dateString, tdirs['bas'], tdirs['rawacf']))


def get_times():
    return [
        dt.datetime(2015, 3, 18),
    ]


if __name__ == '__main__':
    main()
