"""

raw_to_fit.py

Turn rawACF into fitACF files

Terms:
    iq.dat - raw in-phase and quadrature samples recorded by superdarn radars
    .rawacf - autocorrelation of the iq to the pulse sequence produced by the radar (C binary)
    .fitacf - fitted autocorrelation function containing parameters in local reference frame (range, doppler, azimuth, elevation etc.) (C binary)
              Typically 2-hour files, one per radar
    .cfit - subset of the fitacf (saves on space)  (C binary)
            Typically daily, one per radar
    .nc - netCDF output file (self-describing platform-independent file suitable for sharing with users outside the community)
          Daily, one per radar
    fittotxt - Takes a fitacf or a cfit and prints out specified parameters to ascii text. 
               Importantly, this program also geolocates the data in AACGM/geographic coords
    
    fittotxt output has dimensions: time x returns at time t
    netCDF output has dimension npts, where npts is the total number of returns across all the beams 
    "ideal" format is a sparse matrix, ntimes x nbeams x nranges for each variable

author: A.T. Chartier, 5 February 2020
"""
import os
import sys
import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

UTILS_DIR = Path(__file__).resolve().parent.parent / "utils"
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

import glob
import shutil
import datetime as dt
from dateutil.relativedelta import relativedelta
from sd_utils import get_radar_params, id_hdw_params_t, get_random_string
import pickle

DELETE_PROCESSED_RAWACFS = False
SAVE_OUTPUT_TO_LOGFILE = False
MULTIPLE_BEAM_DEFS_ERROR_CODE = 1
MAKE_FIT_VERSIONS = [3.0]
APPLY_FIT_SPECK_REMOVAL = False
MIN_FITACF_FILE_SIZE = 1E5  # bytes


def _make_run_dir(run_dir_base):
    os.makedirs(run_dir_base, exist_ok=True)
    run_dir = os.path.join(
        run_dir_base, "run_{pid}_{suffix}".format(
            pid=os.getpid(),
            suffix=get_random_string(6),
        )
    )
    os.makedirs(run_dir, exist_ok=False)
    return run_dir


def _proc_radar_wrapper(args):
    in_fname_fmt, out_fname, fit_version, run_dir_base, apply_speck_removal = args
    try:
        status = proc_radar(
            in_fname_fmt,
            out_fname,
            fit_version,
            run_dir_base,
            apply_speck_removal=apply_speck_removal,
        )
    except Exception as exc:
        print("Error processing {0}: {1}".format(in_fname_fmt, exc))
        return 1, in_fname_fmt, fit_version
    return status, in_fname_fmt, fit_version


def get_make_fit_flag(fit_version):
    if fit_version == 2.5:
        return "-fitacf2"
    if fit_version == 3.0:
        return "-fitacf3"
    raise ValueError(
        'fit version must be 2.5 or 3.0 - {0} fit version specified'.format(fit_version)
    )


def get_rawacf_radar_list(in_dir):
    print('Calculating list of radars')
    assert os.path.isdir(in_dir), 'Directory not found: %s' % in_dir
    flist = glob.glob(os.path.join(in_dir, '*.rawacf'))
    flist.extend(glob.glob(os.path.join(in_dir, '*.rawacf.bz2')))

    if len(flist) == 0:
        print('No rawACF files in %s' % in_dir)
        return []

    radar_list = []
    for f in flist:
        items = os.path.basename(f).split('.')
        if items[-1] == 'bz2':
            items = items[:-1]
        if len(items) < 5 or items[-1] != 'rawacf':
            raise ValueError('filename does not match expectations: %s' % f)
        radarn = '.'.join(items[3:-1])
        if radarn and radarn not in radar_list:
            radar_list.append(radarn)
            print(radarn)
    return radar_list


def main(
    start_time=dt.datetime(2005, 12, 1),
    end_time=dt.datetime(2020, 1, 1),
    in_dir_fmt='/project/superdarn/data/rawacf/%Y/%m/',
    fit_dir_fmt='/project/superdarn/data/fitacf/%Y/%m/',
    log_dir='/homes/superdarn/logs/rawACF_to_netCDF_logs/',
    run_dir_base='/project/superdarn/run/',
    make_fit_versions=None,
    apply_speck_removal=APPLY_FIT_SPECK_REMOVAL,
    save_output_to_logfile=SAVE_OUTPUT_TO_LOGFILE,
    delete_processed_rawacfs=DELETE_PROCESSED_RAWACFS,
    clobber=False,
    workers=1,
    step=1,  # month
    skip_existing=True,
    fit_ext='*.fit',
):

    if make_fit_versions is None:
        make_fit_versions = MAKE_FIT_VERSIONS

    run_dir = os.path.join(run_dir_base, get_random_string(4))

    # Send the output to a log file
    original_stdout = sys.stdout
    if save_output_to_logfile:
        f = open(
            '{logDir}/raw_to_fit_to_net_{startDate}-{endDate}.log'.format(
                logDir=log_dir,
                startDate=start_time.strftime("%Y%m%d"),
                endDate=end_time.strftime("%Y%m%d"),
            ), 'w')

        sys.stdout = f

    rstpath = os.getenv('RSTPATH')
    assert rstpath, 'RSTPATH environment variable needs to be set'
    hdw_dat_dir = os.path.join(rstpath, 'tables/superdarn/hdw/')

    # Running raw to fit
    radar_info = get_radar_params(hdw_dat_dir)
    raw_to_fit(
        start_time,
        end_time,
        run_dir,
        in_dir_fmt,
        fit_dir_fmt,
        make_fit_versions,
        apply_speck_removal=apply_speck_removal,
        delete_processed_rawacfs=delete_processed_rawacfs,
        clobber=clobber,
        workers=workers,
    )
    sys.stdout = original_stdout


def raw_to_fit(
    start_time=dt.datetime(2016, 1, 1),
    end_time=dt.datetime(2017, 1, 1),
    run_dir='/project/superdarn/run/',
    in_dir='/project/superdarn/data/rawacf/%Y/%m/',
    out_dir='/project/superdarn/alex/fitacf/%Y/%m/',
    make_fit_versions=[3.0],
    apply_speck_removal=False,
    delete_processed_rawacfs=DELETE_PROCESSED_RAWACFS,
    clobber=False,
    workers=1,
):

    print('%s\n%s\n%s\n%s\n%s\n' % (
        'Converting files from rawACF to fitACF',
        'from: %s to %s' % (start_time.strftime('%Y/%m/%d'),
                            end_time.strftime('%Y/%m/%d')),
        'input e.g.: %s' % start_time.strftime(in_dir),
        'output e.g.: %s' % start_time.strftime(out_dir),
        'Run: %s' % run_dir,
    ))

    run_dir = os.path.abspath(run_dir)

    radar_cache = {}
    empty_dirs = set()
    last_fit_version = make_fit_versions[-1]

    if workers < 1:
        raise ValueError("workers must be >= 1")

    if workers == 1:
        for fit_version in make_fit_versions:
            # Loop over time
            time = start_time
            while time <= end_time:
                in_dir_t = time.strftime(in_dir)
                if in_dir_t in empty_dirs:
                    time += relativedelta(months=1)
                    continue
                if in_dir_t not in radar_cache:
                    if not os.path.isdir(in_dir_t):
                        print('%s not found - skipping' % in_dir_t)
                        empty_dirs.add(in_dir_t)
                        time += relativedelta(months=1)
                        continue
                    radar_cache[in_dir_t] = get_rawacf_radar_list(in_dir_t)
                    if len(radar_cache[in_dir_t]) == 0:
                        empty_dirs.add(in_dir_t)
                        time += relativedelta(months=1)
                        continue
                radar_list = radar_cache[in_dir_t]
                for radar in radar_list:
                    in_fname_fmt = time.strftime(os.path.join(
                        in_dir, '%Y%m%d' + '*{radarName}*.rawacf*'.format(radarName=radar)))
                    fit_fname = time.strftime(
                        out_dir + '/%Y%m%d.' + '{radarName}.v{fitVer}.fit'.format(radarName=radar, fitVer=fit_version))
                    if os.path.isfile(fit_fname):
                        print("File exists: %s" % fit_fname)
                        if clobber:
                            print('overwriting')
                        else:
                            print('skipping')
                            continue
                    status = proc_radar(
                        in_fname_fmt,
                        fit_fname,
                        fit_version,
                        run_dir,
                        apply_speck_removal=apply_speck_removal,
                    )

                    # Only delete the rawACFs if:
                    #   - The rawACF -> fitACF conversion succeeded
                    #   - The user set the flag to delete rawACFs
                    #   - All fitACF versions have been created
                    if (
                        status == 0
                        and delete_processed_rawacfs
                        and fit_version == last_fit_version
                    ):
                        print('Deleting processed rawACFs: {rawacfs}'.format(
                            rawacfs=glob.glob(in_fname_fmt)))
                        os.system('rm {rawacfs}'.format(rawacfs=in_fname_fmt))

                time += dt.timedelta(days=1)
    else:
        max_queue = workers * 4
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for fit_version in make_fit_versions:
                pending = set()
                time = start_time
                while time <= end_time:
                    in_dir_t = time.strftime(in_dir)
                    if in_dir_t in empty_dirs:
                        time += relativedelta(months=1)
                        continue
                    if in_dir_t not in radar_cache:
                        if not os.path.isdir(in_dir_t):
                            print('%s not found - skipping' % in_dir_t)
                            empty_dirs.add(in_dir_t)
                            time += relativedelta(months=1)
                            continue
                        radar_cache[in_dir_t] = get_rawacf_radar_list(in_dir_t)
                        if len(radar_cache[in_dir_t]) == 0:
                            empty_dirs.add(in_dir_t)
                            time += relativedelta(months=1)
                            continue
                    radar_list = radar_cache[in_dir_t]
                    for radar in radar_list:
                        in_fname_fmt = time.strftime(os.path.join(
                            in_dir, '%Y%m%d' + '*{radarName}*.rawacf*'.format(radarName=radar)))
                        fit_fname = time.strftime(
                            out_dir + '/%Y%m%d.' + '{radarName}.v{fitVer}.fit'.format(radarName=radar, fitVer=fit_version))
                        if os.path.isfile(fit_fname):
                            print("File exists: %s" % fit_fname)
                            if clobber:
                                print('overwriting')
                            else:
                                print('skipping')
                                continue
                        args = (
                            in_fname_fmt,
                            fit_fname,
                            fit_version,
                            run_dir,
                            apply_speck_removal,
                        )
                        pending.add(executor.submit(_proc_radar_wrapper, args))
                        if len(pending) >= max_queue:
                            done, pending = wait(pending, return_when=FIRST_COMPLETED)
                            for future in done:
                                status, done_fmt, done_version = future.result()
                                if (
                                    status == 0
                                    and delete_processed_rawacfs
                                    and done_version == last_fit_version
                                ):
                                    print('Deleting processed rawACFs: {rawacfs}'.format(
                                        rawacfs=glob.glob(done_fmt)))
                                    os.system('rm {rawacfs}'.format(rawacfs=done_fmt))

                    time += dt.timedelta(days=1)

                if pending:
                    done, pending = wait(pending)
                    for future in done:
                        status, done_fmt, done_version = future.result()
                        if (
                            status == 0
                            and delete_processed_rawacfs
                            and done_version == last_fit_version
                        ):
                            print('Deleting processed rawACFs: {rawacfs}'.format(
                                rawacfs=glob.glob(done_fmt)))
                            os.system('rm {rawacfs}'.format(rawacfs=done_fmt))


def proc_radar(
    in_fname_fmt,
    out_fname,
    fit_version,
    run_dir_base,
    apply_speck_removal=False,
):

    run_dir = _make_run_dir(run_dir_base)
    prev_cwd = os.getcwd()
    try:
        os.chdir(run_dir)

        # Set up storage directory
        out_dir = os.path.dirname(out_fname)
        os.makedirs(out_dir, exist_ok=True)

        # Make fitacfs for the day
        in_fnames = glob.glob(in_fname_fmt)
        if len(in_fnames) == 0:
            print('No files in %s' % in_fname_fmt)
            return 1

        rawacfFileList = []
        for in_fname in in_fnames:
            rawacfFile = in_fname.split('/')[-1]
            rawacfFileList.append(rawacfFile)

            shutil.copy2(in_fname, run_dir)
            in_fname_t = os.path.join(run_dir, os.path.basename(in_fname))
            if in_fname_t.endswith('.bz2'):
                os.system('bzip2 -d %s' % in_fname_t)
                rawacf_path = in_fname_t[:-4]
            else:
                rawacf_path = in_fname_t

            tmp_fname = '.'.join(rawacf_path.split('.')[:-1]) + '.fitacf'
            fit_flag = get_make_fit_flag(fit_version)
            os.system('make_fit {0} {1} > {2}'.format(
                fit_flag, rawacf_path, tmp_fname))
        os.system('cat *.fitacf > tmp.fitacf')

        # Create a single fitACF at output location
        fn_inf = os.stat('tmp.fitacf')
        if fn_inf.st_size > MIN_FITACF_FILE_SIZE:
            if fit_version == 2.5:
                shutil.move('tmp.fitacf', out_fname)
            elif fit_version == 3.0:
                if apply_speck_removal:
                    os.system('fit_speck_removal tmp.fitacf > {0}'.format(out_fname))
                    fn_inf = os.stat(out_fname)
                else:
                    shutil.move('tmp.fitacf', out_fname)
            else:
                raise ValueError(
                    'fit version must be 2.5 of 3.0 - {0} fit version specified'.format(fit_version))

            print('file created at %s, size %1.1f MB' %
                  (out_fname, fn_inf.st_size / 1E6))

            # Use the fitACF output filename to create a similar filename for the
            # list of rawACFs used to create the fitACF
            rawacfListFilename = '.'.join(
                out_fname.split('.')[:-1]) + '.rawacfList.txt'

            # Save the list of rawACFs used to create the fitACF
            with open(rawacfListFilename, "wb") as fp:
                pickle.dump(rawacfFileList, fp)
        else:
            print('file %s too small, size %1.1f MB' %
                  (out_fname, fn_inf.st_size / 1E6))
        return 0
    finally:
        try:
            os.chdir(prev_cwd)
        except OSError:
            pass
        shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == '__main__':
    def parse_date_arg(value):
        for fmt in ("%Y,%m,%d", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return dt.datetime.strptime(value, fmt)
            except ValueError:
                continue
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}. Use YYYY,MM,DD (e.g., 2014,04,23) or YYYY-MM-DD."
        )

    def parse_fit_versions(value):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if not parts:
            raise argparse.ArgumentTypeError("Fit versions must be comma-separated values, e.g. 3.0,2.5.")
        versions = []
        for part in parts:
            try:
                versions.append(float(part))
            except ValueError as exc:
                raise argparse.ArgumentTypeError(
                    f"Invalid fit version {part!r}. Use numeric versions like 3.0 or 2.5."
                ) from exc
        return versions

    def format_fit_versions(values):
        return ",".join(f"{val:.1f}" for val in values)

    parser = argparse.ArgumentParser(
        description="Convert SuperDARN rawACF files to fitACF files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--start",
        dest="start_time",
        type=parse_date_arg,
        required=True,
        help="Start date (inclusive). Formats: YYYY,MM,DD or YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end",
        dest="end_time",
        type=parse_date_arg,
        required=True,
        help="End date (inclusive). Formats: YYYY,MM,DD or YYYY-MM-DD.",
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        dest="in_dir_fmt",
        default="/project/superdarn/data/rawacf/%Y/%m/",
        help="Path template to rawACF files (strftime-friendly).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        dest="fit_dir_fmt",
        default="/project/superdarn/data/fitacf/%Y/%m/",
        help="Output directory template for fitACF files (strftime-friendly).",
    )
    parser.add_argument(
        "--run-dir-base",
        dest="run_dir_base",
        default="/project/superdarn/run/",
        help="Base directory for per-run scratch folders.",
    )
    parser.add_argument(
        "--versions",
        dest="make_fit_versions",
        type=parse_fit_versions,
        default=MAKE_FIT_VERSIONS,
        help=f"Comma-separated fitACF versions to produce ({format_fit_versions(MAKE_FIT_VERSIONS)} default).",
    )
    parser.add_argument(
        "--speck-removal",
        dest="apply_speck_removal",
        action="store_true",
        help="Enable fit_speck_removal for fitACF v3.0 outputs.",
    )
    parser.add_argument(
        "--delete-rawacfs",
        dest="delete_processed_rawacfs",
        action="store_true",
        help="Delete rawACF inputs after a successful conversion of all versions.",
    )
    parser.add_argument(
        "--save-log",
        dest="save_output_to_logfile",
        action="store_true",
        help="Save stdout to a dated log file in the log directory.",
    )
    parser.add_argument(
        "--log-dir",
        dest="log_dir",
        default="/homes/superdarn/logs/rawACF_to_netCDF_logs/",
        help="Directory for log output when --save-log is set.",
    )
    parser.add_argument(
        "--clobber",
        dest="clobber",
        action="store_true",
        help="Overwrite existing fitACF outputs instead of skipping them.",
    )
    parser.add_argument(
        "--workers",
        dest="workers",
        type=int,
        default=1,
        help="Number of worker processes for parallel conversion.",
    )

    args = parser.parse_args()
    main(
        args.start_time,
        args.end_time,
        args.in_dir_fmt,
        args.fit_dir_fmt,
        log_dir=args.log_dir,
        run_dir_base=args.run_dir_base,
        make_fit_versions=args.make_fit_versions,
        apply_speck_removal=args.apply_speck_removal,
        save_output_to_logfile=args.save_output_to_logfile,
        delete_processed_rawacfs=args.delete_processed_rawacfs,
        clobber=args.clobber,
        workers=args.workers,
    )
