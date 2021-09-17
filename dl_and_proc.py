"""
Download and process data one day at a time
"""
import raw_to_nc
import datetime as dt
import os 

def main():
    dirs  = {
        'bas': 'apl@bslsuperdarnb.nerc-bas.ac.uk:/sddata/raw/%Y/%m/',
        'rawacf': '/project/superdarn/data/rawacf/%Y/%Y%m%d/',
        'fitacf': '/project/superdarn/data/fitacf/%Y/%m/',
        'netcdf': '/project/superdarn/data/netcdf/%Y/%m/',
        'log': 'logs/',
    }

    times = get_times()

    for time in times: 
        breakpoint()
        dl_one_day(dirs, time)
        raw_to_nc.main(time, time, dirs['rawacf'], dirs['fitacf'], dirs['netcdf'])
    
    # TODO: Delete old rawACF files


def dl_one_day(dirs, time):
    tdirs = {}
    for key, dirn in dirs.items():
        tdirs[key] = time.strftime(dirn)
        if key != 'bas':
            os.makedirs(tdirs[key], exist_ok=True)

    dateString = time.strftime('%Y%m%d')
    os.system("rsync -avhe ssh --include '*/' --include '%s*' --exclude '*' %s %s" % (dateString, tdirs['bas'], tdirs['rawacf']))


def get_times():
    return [
        dt.datetime(2015, 9, 19),
        dt.datetime(2015, 10, 16),
        dt.datetime(2015, 10, 22),
        dt.datetime(2015, 11, 1),
        dt.datetime(2015, 11, 12),
        dt.datetime(2015, 12, 6),
        dt.datetime(2015, 12, 8),
        dt.datetime(2015, 12, 9),
        dt.datetime(2015, 12, 14),
        dt.datetime(2016, 1, 7),
        dt.datetime(2016, 1, 10),
        dt.datetime(2016, 2, 7),
        dt.datetime(2016, 10, 22),
        dt.datetime(2016, 11, 2),
        dt.datetime(2016, 11, 6),
        dt.datetime(2016, 11, 12),
        dt.datetime(2016, 11, 13),
        dt.datetime(2016, 11, 18),
        dt.datetime(2016, 11, 23),
        dt.datetime(2016, 12, 11),
        dt.datetime(2016, 12, 19),
        dt.datetime(2017, 1, 2),
        dt.datetime(2017, 1, 11),
        dt.datetime(2017, 1, 20),
        dt.datetime(2017, 1, 22),
        dt.datetime(2017, 1, 27),
    ]


if __name__ == '__main__':
    main()
