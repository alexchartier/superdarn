"""

fit_to_fitnc.py

Turn fitacf/cfit into netCDF files

Terms:
    iq.dat - raw in-phase and quadrature samples recorded by superdarn radars
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

HELP_TEXT = """
Convert SuperDARN fitacf/cfit files to daily netCDF.

Usage:
  python3 fit_to_nc.py --start YYYY-MM-DD --end YYYY-MM-DD [options]

Key options:
  -i / --input-dir   Path template to fitACF files (strftime-friendly, e.g. /project/superdarn/data/fitacf/%Y/%m/)
  -o / --output-dir  Output netCDF path template (strftime-friendly)
  -v / --fit-version FitACF version to process: 3.0 or 2.5
  -r / --radars      Comma-separated radar codes to include (default: all)
  -p / --parallel-jobs  Number of files to convert in parallel
  -f / --force       Overwrite existing outputs

Notes:
  - Requires RSTPATH to be set.
  - Existing netCDF files are skipped by default.
"""

import argparse
import os
import sys
import datetime as dt
import inspect
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


def parse_date(val: str) -> dt.datetime:
    for fmt in ('%Y,%m,%d', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(val, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f'invalid date format: {val} (expected YYYY,MM,DD or YYYY-MM-DD)')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert SuperDARN fitacf/cfit files to daily netCDF.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--start', required=True, type=parse_date, help='Start date (YYYY,MM,DD or YYYY-MM-DD)')
    parser.add_argument('--end', required=True, type=parse_date, help='End date inclusive (YYYY,MM,DD or YYYY-MM-DD)')
    parser.add_argument(
        '-i',
        '--input-dir',
        dest='input_dir',
        default='/project/superdarn/data/fitacf/%Y/%m/',
        help='Path template to fitacf files (strftime-friendly)',
    )
    parser.add_argument(
        '-o',
        '--output-dir',
        dest='output_dir',
        default='/project/superdarn/data/netcdf/%Y/%m/',
        help='Output netCDF path template (strftime-friendly)',
    )
    parser.add_argument(
        '-v',
        '--fit-version',
        dest='fit_version',
        type=float,
        choices=[3.0, 2.5],
        default=3.0,
        help='FitACF version to process',
    )
    parser.add_argument(
        '-r',
        '--radars',
        default='',
        help='Comma-separated radar codes to include; if omitted, process all radars',
    )
    parser.add_argument(
        '-p',
        '--parallel-jobs',
        dest='parallel_jobs',
        type=int,
        default=1,
        help='Number of files to convert in parallel',
    )
    parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='Overwrite existing netCDF outputs instead of skipping them',
    )
    parser.add_argument(
        '--delete-input',
        action='store_true',
        help='Delete input .fit/.fitacf file after a successful conversion',
    )
    return parser.parse_args()

UTILS_DIR = Path(__file__).resolve().parent.parent / "utils"
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

import glob
# import bz2
import netCDF4
import jdutil
from dateutil.relativedelta import relativedelta
import calendar
import numpy as np
from sd_utils import get_radar_params, id_hdw_params_t, get_radar_list
import radFov
import pickle
import helper
import pydarnio

MULTIPLE_BEAM_DEFS_ERROR_CODE = 1
SHAPE_MISMATCH_ERROR_CODE = 2
MIN_FITACF_FILE_SIZE = 1E5  # bytes
MAKE_FIT_VERSIONS = [3.0, 2.5]
# Accept both legacy .fit and newer .fitacf extensions.
FIT_EXTS = ('*.fit', '*.fitacf')
SKIP_EXISTING = True
# Limit per-record logging to avoid massive log files when data are bad.
LOG_SAMPLE_LIMIT = 20


def _normalize_fitacf_records(obj):
    """Normalize fitacf reader outputs to a list of dicts."""
    if isinstance(obj, tuple) and len(obj) == 2 and isinstance(obj[0], list):
        obj = obj[0]
    if isinstance(obj, dict):
        return [obj]
    if not isinstance(obj, list):
        raise ValueError(f"Unexpected fitacf data type {type(obj)}")
    return obj


def load_fitacf_records(path: str):
    """
    Compatibility loader for fitacf files that works with both new (read_fitacf)
    and older pydarnio releases (and direct dmap bindings).
    Returns a list of record dicts.
    """
    errors: list[str] = []

    reader = getattr(pydarnio, "read_fitacf", None)
    if reader:
        try:
            sig = inspect.signature(reader)
            kwargs = {}
            if "mode" in sig.parameters:
                kwargs["mode"] = "lax"
            recs = reader(path, **kwargs)
            return _normalize_fitacf_records(recs)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"pydarnio.read_fitacf: {exc}")

    dmap_reader = getattr(pydarnio, "read_dmap", None)
    if dmap_reader:
        try:
            sig = inspect.signature(dmap_reader)
            kwargs = {}
            if "fmt" in sig.parameters:
                kwargs["fmt"] = "fitacf"
            if "mode" in sig.parameters:
                kwargs["mode"] = "lax"
            recs = dmap_reader(path, **kwargs)
            return _normalize_fitacf_records(recs)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"pydarnio.read_dmap: {exc}")

    try:
        import pydarn  # type: ignore

        try:
            reader = pydarn.SuperDARNRead(path)  # type: ignore[attr-defined]
            recs = reader.read_fitacf()
            return _normalize_fitacf_records(recs)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"pydarn.SuperDARNRead.read_fitacf: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pydarn import: {exc}")

    try:
        from pydarnio.dmap_wrapper import read_dispatcher  # type: ignore

        recs = read_dispatcher(path, "fitacf", "lax")
        return _normalize_fitacf_records(recs)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"dmap_wrapper.read_dispatcher: {exc}")

    try:
        import dmap  # type: ignore

        if hasattr(dmap, "read_fitacf_lax"):
            recs = dmap.read_fitacf_lax(path)
        else:
            recs = dmap.read_fitacf(path)
        return _normalize_fitacf_records(recs)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"dmap: {exc}")

    raise RuntimeError(f"Unable to read fitacf file {path}; tried: {'; '.join(errors)}")


def parse_fit_date_from_filename(fit_fn: str) -> dt.datetime:
    stem = Path(fit_fn).name.split('.')[0]
    return dt.datetime.strptime(stem, '%Y%m%d')


def process_single_file(
    fit_fn: str,
    out_fn: str,
    file_date: dt.datetime,
    radar_info_entry,
    fitVersion: float,
    skip_existing: bool,
    delete_input: bool,
):
    if skip_existing and os.path.isfile(out_fn):
        return 'skip', fit_fn

    try:
        os.makedirs(os.path.dirname(out_fn), exist_ok=True)
        radar_info_t = id_hdw_params_t(file_date, radar_info_entry)
        status = fit_to_nc(file_date, fit_fn, out_fn, radar_info_t, fitVersion)
        if status == 0:
            if delete_input:
                try:
                    os.remove(fit_fn)
                except OSError as exc:  # noqa: BLE001
                    print(f'Converted but could not delete input {fit_fn}: {exc}', file=sys.stderr)
            return 'ok', fit_fn
        return 'fail', fit_fn
    except Exception as exc:  # noqa: BLE001
        print(f'Failed to convert {fit_fn}: {exc}', file=sys.stderr)
        return 'fail', fit_fn


def main(args: argparse.Namespace) -> int:
    global SKIP_EXISTING
    SKIP_EXISTING = not args.force

    rstpath = os.getenv('RSTPATH')
    if not rstpath:
        print('RSTPATH environment variable needs to be set', file=sys.stderr)
        return 1
    if args.parallel_jobs < 1:
        print(f'Parallel jobs must be a positive integer: {args.parallel_jobs}', file=sys.stderr)
        return 1

    hdw_dat_dir = os.path.join(rstpath, 'tables/superdarn/hdw/')

    radar_allow = [r for r in args.radars.split(',') if r]

    # Running fit to NC
    radar_info = get_radar_params(hdw_dat_dir)

    # this does the bzipping
    #combine_fitacfs(startTime, endTime, fitDir, fitVersion)

    # Loop over fit files in the monthly directories
    time = args.start
    total_converted = 0
    total_failed = 0
    total_skipped = 0
    total_small = 0

    banner = (
        f"Starting fit_to_fitnc at {dt.datetime.now():%Y-%m-%d %H:%M:%S} "
        f"(pid={os.getpid()}), range {args.start:%Y-%m-%d} to {args.end:%Y-%m-%d}, "
        f"input={args.input_dir}, output={args.output_dir}, parallel_jobs={args.parallel_jobs}"
    )
    print(banner, flush=True)

    while time <= args.end:
        fitDir_t = time.strftime(args.input_dir)
        month_label = time.strftime('%Y/%m')
        month_small = 0

        print(f'--- Starting month {month_label} (input: {fitDir_t}) ---')

        bzips = glob.glob(os.path.join(fitDir_t, '*.bz2'))
        if bzips:
            print(f'bzips found - run concat_fitacf_daily.py first ({fitDir_t})', file=sys.stderr)
            return 1

        # Loop over the files
        fitFnames: list[str] = []
        for pat in FIT_EXTS:
            fitFnames.extend(glob.glob(os.path.join(fitDir_t, pat)))
        print('Processing %i fit files in %s on %s (patterns: %s)' %
              (len(fitFnames), fitDir_t, time.strftime('%Y/%m'), ','.join(FIT_EXTS)))

        jobs = []

        for fit_fn in fitFnames:

            # Check the file is big enough to be worth bothering with
            fn_info = os.stat(fit_fn)
            if fn_info.st_size < MIN_FITACF_FILE_SIZE:
                print('\n\n%s %1.1f MB\nFile too small - skipping' %
                      (fit_fn, fn_info.st_size / 1E6))
                month_small += 1
                continue

            try:
                file_date = parse_fit_date_from_filename(fit_fn)
            except Exception:
                print(f'Could not parse date from {fit_fn} - skipping', file=sys.stderr)
                continue

            radar_parts = os.path.basename(fit_fn).split('.')
            if len(radar_parts) < 2:
                print(f'Could not parse radar code from {fit_fn} - skipping', file=sys.stderr)
                continue
            radar_code = radar_parts[1]
            if radar_allow and radar_code not in radar_allow:
                continue
            if radar_code not in radar_info:
                print(f'Radar code {radar_code} not found in hardware params - skipping {fit_fn}', file=sys.stderr)
                continue

            fn_head = '.'.join(os.path.basename(fit_fn).split('.')[:-1])
            netDir_t = file_date.strftime(args.output_dir)
            out_fn = os.path.join(netDir_t, '{0}.nc'.format(fn_head))
            if os.path.isfile(out_fn):
                if SKIP_EXISTING:
                    print('%s exists - skipping' % out_fn)
                    total_skipped += 1
                    continue
                else:
                    print('%s exists - deleting' % out_fn)
                    os.remove(out_fn)

            jobs.append((fit_fn, out_fn, file_date, radar_info[radar_code]))

        if not jobs:
            time += relativedelta(months=1)
            continue

        print(f'Queued {len(jobs)} files for conversion from {fitDir_t}')
        actual_workers = max(1, min(args.parallel_jobs, len(jobs), os.cpu_count() or args.parallel_jobs))
        print(f'Using up to {actual_workers} parallel workers this month')

        converted = 0
        failed = 0
        skipped_existing = 0

        if actual_workers == 1:
            for job in jobs:
                status, fname = process_single_file(*job, args.fit_version, SKIP_EXISTING, args.delete_input)
                if status == 'ok':
                    converted += 1
                elif status == 'skip':
                    skipped_existing += 1
                else:
                    failed += 1
        else:
            with ProcessPoolExecutor(max_workers=actual_workers) as executor:
                future_map = {
                    executor.submit(process_single_file, *job, args.fit_version, SKIP_EXISTING, args.delete_input): job[0]
                    for job in jobs
                }
                for future in as_completed(future_map):
                    try:
                        status, fname = future.result()
                    except Exception as exc:  # noqa: BLE001
                        print(f'Failed to convert {future_map[future]}: {exc}', file=sys.stderr)
                        failed += 1
                        continue
                    if status == 'ok':
                        converted += 1
                    elif status == 'skip':
                        skipped_existing += 1
                    else:
                        failed += 1

        total_converted += converted
        total_failed += failed
        total_skipped += skipped_existing
        total_small += month_small

        month = time.strftime('%m')
        multiBeamLogDir = time.strftime(helper.FIT_NET_LOG_DIR) + month
        multiBeamFile = '{dir}/multi_beam_defs_{m}.log'.format(
            dir=multiBeamLogDir, m=month)
        if os.path.exists(multiBeamFile):
            subject = '"Multiple Beam Definitions Found - {date}"'.format(
                date=month_label)
            body = 'Files with multiple beam definitions have been found. See details in {file}'.format(
                file=multiBeamFile)
            helper.send_email(subject, body)

        time += relativedelta(months=1)
        print(f'Month summary ({month_label}): converted {converted}, failed {failed}, skipped existing {skipped_existing}, small files {month_small}')

    print(f'Total summary: converted {total_converted}, failed {total_failed}, skipped existing {total_skipped}, small files {total_small}')
    return 1 if total_failed > 0 else 0


def fit_to_nc(date, in_fname, out_fname, radar_info, fitVersion):
    # fitACF to netCDF using davitpy FOV calc  - no dependence on fittotxt
    out_vars, hdr_vals = convert_fitacf_data(
        date, in_fname, radar_info, fitVersion)
    if out_vars == MULTIPLE_BEAM_DEFS_ERROR_CODE or out_vars == SHAPE_MISMATCH_ERROR_CODE:
        return out_vars

    var_defs = def_vars()
    dim_defs = {
        'npts': out_vars['mjd'].shape[0],
    }
    header_info = def_header_info(in_fname, hdr_vals)

    # Write out the netCDF
    with netCDF4.Dataset(out_fname, 'w') as nc:
        set_header(nc, header_info)
        for k, v in dim_defs.items():
            nc.createDimension(k, size=v)
        for k, v in out_vars.items():
            defs = var_defs[k]
            var = nc.createVariable(
                k,
                defs['type'],
                defs['dims'],
                zlib=True,
                complevel=6,
                shuffle=True,
            )
            try:
                var[:] = v
            except Exception as e:
                print(e)
                try:
                    os.remove(out_fname)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    print(f'Could not remove partial output {out_fname}: {exc}', file=sys.stderr)
                print(
                    f'Keeping source file {in_fname} in place after shape mismatch; logged partial output cleanup.',
                    file=sys.stderr,
                )
                return SHAPE_MISMATCH_ERROR_CODE

            var.units = defs['units']
            var.long_name = defs['long_name']

    return 0


def convert_fitacf_data(date, in_fname, radar_info, fitVersion):
    try:
        day = in_fname.split('.')[0].split('/')[-1]
        month = day[:-2]

        # Keep track of fitACF files that have multiple beam definitions in a
        # monthly log file
        multiBeamLogDir = date.strftime(helper.FIT_NET_LOG_DIR) + month
        multiBeamLogfile = '{dir}/multi_beam_defs_{m}.log'.format(
            dir=multiBeamLogDir, m=month)

        # Store conversion info like returns outside FOV, missing slist, etc
        # for each conversion
        #conversionLogDir = '{dir}/{d}'.format(dir=multiBeamLogDir, d=day)
        conversionLogDir = 'run/'
        fName = in_fname.split('/')[-1]
        conversionLogfile = '{dir}/{fit}_to_nc.log'.format(
            dir=conversionLogDir, fit=fName)

        # Define the name of the file holding the list of rawACFs used to
        # create the fitACF
        # fitacfListFilename = '.'.join(in_fname.split('.')[:-1]) + '.fitacfList.txt'

        try:
            data = load_fitacf_records(in_fname)
        except Exception as exc:
            os.makedirs(conversionLogDir, exist_ok=True)
            logText = f'Unable to read {in_fname}: {exc}\n'
            with open(conversionLogfile, "a+") as fp:
                fp.write(logText)
            return SHAPE_MISMATCH_ERROR_CODE, SHAPE_MISMATCH_ERROR_CODE
    
        bmdata = {
            'rsep': [],
            'frang': [],
        }
        beam_outside_range = False
        beams_outside: set[int] = set()
        for rec in data:
            for k, v in bmdata.items():
                bmdata[k].append(rec[k])
            if 'slist' in rec.keys():
                if radar_info['maxrg'] < rec['slist'].max():
                    radar_info['maxrg'] = rec['slist'].max() + 5
            try:
                bm_val = int(rec['bmnum'])
            except Exception:
                bm_val = None
            if bm_val is not None:
                if bm_val >= radar_info['maxbeams']:
                    beam_outside_range = True
                    beams_outside.add(bm_val)

        if beam_outside_range:
            os.makedirs(conversionLogDir, exist_ok=True)
            logText = f'Beam numbers {sorted(beams_outside)} exceed configured maxbeams ({radar_info["maxbeams"]}) - skipping file conversion.\n'
            with open(conversionLogfile, "a+") as fp:
                fp.write(logText)
            return SHAPE_MISMATCH_ERROR_CODE, SHAPE_MISMATCH_ERROR_CODE

        for k, v in bmdata.items():
            val_arr = np.unique(v)
            if len(val_arr) > 1:
                os.makedirs(conversionLogDir, exist_ok=True)
                os.makedirs(multiBeamLogDir, exist_ok=True)

                # Log the multiple beams error in the monthly mutli beam def log
                logText = '{fitacfFullFile} has {numBeamDefs} beam definitions - skipping file conversion.\n'.format(
                    fitacfFullFile=in_fname, numBeamDefs=len(val_arr))

                with open(multiBeamLogfile, "a+") as fp:
                    fp.write(logText)

                # Log the multiple beams error in this fitACF's conversion log
                with open(conversionLogfile, "a+") as fp:
                    fp.write(logText)

                return MULTIPLE_BEAM_DEFS_ERROR_CODE, MULTIPLE_BEAM_DEFS_ERROR_CODE

            bmdata[k] = int(val_arr.item())

        # Define FOV
        fov = radFov.fov(
            frang=bmdata['frang'], rsep=bmdata['rsep'], site=None, nbeams=int(radar_info['maxbeams']),
            ngates=int(radar_info['maxrg']), bmsep=radar_info['beamsep'], recrise=radar_info['risetime'], siteLat=radar_info['glat'],
            siteLon=radar_info['glon'], siteBore=radar_info['boresight'], siteAlt=radar_info['alt'], siteYear=date.year,
            elevation=None, altitude=300., hop=None, model='C',
            coords='geo', date_time=date, coord_alt=0., fov_dir='front',
        )
        fov_beams = set(np.atleast_1d(fov.beams).tolist())

        # Define fields
        short_flds = 'tfreq', 'noise.sky', 'cp',
        fov_flds = 'mjd', 'beam', 'range', 'lat', 'lon',
        data_flds = 'p_l', 'v', 'v_e', 'w_l', 'w_l_e', 'gflg', 
        elv_flds = 'elv', 'elv_low', 'elv_high',

        """
        elv_flds = 'elv', 'elv_low', 'elv_high',
        # Figure out if we have elevation information
        elv_exists = True
        for rec in data:
            if 'elv' not in rec.keys():
                elv_exists = False
        if elv_exists:
            data_flds += elv_flds
        """

        # Set up data storage
        out = {}
        for fld in (fov_flds + data_flds + short_flds + elv_flds):
            out[fld] = []

        records_seen = 0
        skipped_missing_slist = 0
        skipped_outside_fov = 0
        skipped_invalid_beam = 0

        # Run through each beam record and store
        for rec in data:
            records_seen += 1
            time = dt.datetime(rec['time.yr'], rec['time.mo'], rec['time.dy'],
                               rec['time.hr'], rec['time.mt'], rec['time.sc'])
            # slist is the list of range gates with backscatter
            if 'slist' not in rec.keys():
                os.makedirs(conversionLogDir, exist_ok=True)
                if skipped_missing_slist < LOG_SAMPLE_LIMIT:
                    logText = 'Could not find slist in record {recordTime} - skipping\n'.format(
                        recordTime=time.strftime('%Y-%m-%d %H:%M:%S'))
                    with open(conversionLogfile, "a+") as fp:
                        fp.write(logText)

                skipped_missing_slist += 1
                continue

            # Can't deal with returns outside of FOV
            if rec['slist'].max() >= fov.slantRCenter.shape[1]:
                os.makedirs(conversionLogDir, exist_ok=True)

                # Log returns outside of FOV
                if skipped_outside_fov < LOG_SAMPLE_LIMIT:
                    logText = 'Record {recordTime} found to have a max slist of {maxSList} - skipping record/n'.format(
                        recordTime=time.strftime('%Y-%m-%d %H:%M:%S'), maxSList=rec['slist'].max())
                    with open(conversionLogfile, "a+") as fp:
                        fp.write(logText)

                skipped_outside_fov += 1
                continue

            try:
                beam_num = int(rec['bmnum'])
            except Exception:
                beam_num = None
            time_str = time.strftime('%Y-%m-%d %H:%M:%S')
            if beam_num is None or beam_num not in fov_beams:
                os.makedirs(conversionLogDir, exist_ok=True)
                if skipped_invalid_beam < LOG_SAMPLE_LIMIT:
                    logText = (
                        f"Record {time_str} has beam {rec.get('bmnum')} outside available beams "
                        f"{sorted(fov_beams)} - skipping file conversion.\n"
                    )
                    with open(conversionLogfile, "a+") as fp:
                        fp.write(logText)

                skipped_invalid_beam += 1
                return SHAPE_MISMATCH_ERROR_CODE, SHAPE_MISMATCH_ERROR_CODE

            one_obj = np.ones(len(rec['slist']))
            mjd = jdutil.jd_to_mjd(jdutil.datetime_to_jd(time))
            bmnum = one_obj * beam_num
            fovi = fov.beams == beam_num
            out['mjd'] += (one_obj * mjd).tolist()
            out['beam'] += bmnum.tolist()
            out['range'] += fov.slantRCenter[fovi, rec['slist']].tolist()
            out['lat'] += fov.latCenter[fovi, rec['slist']].tolist()
            out['lon'] += fov.lonCenter[fovi, rec['slist']].tolist()

            for fld in data_flds:
                out[fld] += rec[fld].tolist()
            for fld in short_flds:  # expand out to size
                out[fld] += (one_obj * rec[fld]).tolist()
            for fld in elv_flds:
                try:  
                    out[fld] += rec[fld].tolist()
                except:
                    out[fld] += (one_obj * 0).tolist()

        total_points = len(out['mjd'])
        if records_seen > 0:
            os.makedirs(conversionLogDir, exist_ok=True)
            summary = (
                f'Records: seen={records_seen}, converted_points={total_points}, '
                f'skipped_missing_slist={skipped_missing_slist}, '
                f'skipped_outside_fov={skipped_outside_fov}, '
                f'skipped_invalid_beam={skipped_invalid_beam}\n'
            )
            with open(conversionLogfile, "a+") as fp:
                fp.write(summary)
        if total_points == 0:
            return SHAPE_MISMATCH_ERROR_CODE, SHAPE_MISMATCH_ERROR_CODE

        # Convert to numpy arrays
        for k, v in out.items():
            out[k] = np.array(v)

        # Calculate beam azimuths assuming 15 degrees elevation
        beam_off = radar_info['beamsep'] * \
            (fov.beams - (radar_info['maxbeams'] - 1) / 2.0)
        el = 15.
        brng = np.zeros(beam_off.shape)
        for ind, beam_off_elzero in enumerate(beam_off):
            brng[ind] = radFov.calcAzOffBore(
                el, beam_off_elzero, fov_dir=fov.fov_dir) + radar_info['boresight']

        hdr = {
            'lat': radar_info['glat'],
            'lon': radar_info['glon'],
            'alt': radar_info['alt'],
            'rsep': bmdata['rsep'],
            'maxrg': radar_info['maxrg'],
            'bmsep': radar_info['beamsep'],
            'boresight': radar_info['boresight'],
            'beams': fov.beams,
            'brng_at_15deg_el': brng,
            'fitacf_version': fitVersion
        }
    except Exception as e:
        print(e)
        print(
            f'Fit conversion failed for {in_fname}; source file left untouched (no move to processing issues dir).',
            file=sys.stderr,
        )
        return SHAPE_MISMATCH_ERROR_CODE, SHAPE_MISMATCH_ERROR_CODE

    return out, hdr


def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return dt.datetime(year, month, day, sourcedate.hour, sourcedate.minute, sourcedate.second)


def def_vars():
    # netCDF writer expects a series of variable definitions - here they are
    stdin_int = {'units': 'none', 'type': 'u1', 'dims': 'npts'}
    stdin_int2 = {'units': 'none', 'type': 'u2', 'dims': 'npts'}
    stdin_flt = {'type': 'f4', 'dims': 'npts'}
    stdin_dbl = {'type': 'f8', 'dims': 'npts'}
    var_defs = {
        'mjd': dict({'units': 'days', 'long_name': 'Modified Julian Date'}, **stdin_dbl),
        'beam': dict({'long_name': 'Beam #'}, **stdin_int),
        'range': dict({'units': 'km', 'long_name': 'Slant range'}, **stdin_int2),
        'lat': dict({'units': 'deg.', 'long_name': 'Geographic Latitude'}, **stdin_flt),
        'lon': dict({'units': 'deg.', 'long_name': 'Geographic Longitude'}, **stdin_flt),
        'p_l': dict({'units': 'dB', 'long_name': 'Lambda fit SNR'}, **stdin_flt),
        'v': dict({'units': 'm/s', 'long_name': 'LOS Vel. (+ve away from radar)'}, **stdin_flt),
        'v_e': dict({'units': 'm/s', 'long_name': 'LOS Vel. error'}, **stdin_flt),
        'w_l': dict({'units': 'm/s', 'long_name': 'Spectral Width (lambda fit)'}, **stdin_flt),
        'w_l_e': dict({'units': 'm/s', 'long_name': 'Spectral Width error (lambda fit)'}, **stdin_flt),
        'gflg': dict({'long_name': 'Ground scatter flag for ACF, 1 - ground scatter, 0 - other scatter'}, **stdin_int),
        'elv': dict({'units': 'degrees', 'long_name': 'Elevation angle estimate'}, **stdin_flt),
        'elv_low': dict({'units': 'degrees', 'long_name': 'Lowest elevation angle estimate'}, **stdin_flt),
        'elv_high': dict({'units': 'degrees', 'long_name': 'Highest elevation angle estimate'}, **stdin_flt),
        'tfreq': dict({'units': 'kHz', 'long_name': 'Transmit freq'}, **stdin_int2),
        'noise.sky': dict({'units': 'none', 'long_name': 'Sky noise'}, **stdin_flt),
        'cp': dict({'units': 'none', 'long_name': 'Control program ID'}, **stdin_int2),
    }

    return var_defs


def set_header(rootgrp, header_info):
    rootgrp.description = header_info['description']
    rootgrp.fitacf_source = header_info['fitacf_source']
    rootgrp.history = header_info['history']
    rootgrp.fitacf_version = header_info['fitacf_version']
    rootgrp.lat = header_info['lat']
    rootgrp.lon = header_info['lon']
    rootgrp.alt = header_info['alt']
    rootgrp.rsep_km = header_info['rsep']
    rootgrp.maxrangegate = header_info['maxrg']
    rootgrp.bmsep = header_info['bmsep']
    rootgrp.boresight = header_info['boresight']
    rootgrp.beams = header_info['beams']
    rootgrp.brng_at_15deg_el = header_info['brng_at_15deg_el']
    return rootgrp


def def_header_info(in_fname, hdr_vals):
    hdr = {
        **{
            'description': 'Geolocated line-of-sight velocities and related parameters from SuperDARN fitACF',
            'fitacf_source': in_fname,
            'history': 'Created on %s' % dt.datetime.now(),
        },
        **hdr_vals,
    }

    return hdr


def combine_fitacfs(startTime, endTime, fitDir, fitVersion):

    print('Combining fitACF files')

    # Loop through the fitACF files one day at a time
    time = startTime
    while time <= endTime:
        fitDir_t = time.strftime(fitDir)
        if not os.path.isdir(fitDir_t):
            time += relativedelta(months=1)
            print('%s not found - skipping' % fitDir_t)
            continue

        radar_list = get_radar_list(fitDir_t)
        for radar in radar_list:
            inFilenameFormat = time.strftime(os.path.join(
                fitDir_t, '%Y%m%d*{0}*fitacf.bz2'.format(radar)))

            if fitVersion == 3.0:
                outputFilename = time.strftime(os.path.join(
                    fitDir_t, '%Y%m%d.{0}.v{1}.despeckled.fit'.format(radar, fitVersion)))
            elif fitVersion == 2.5:
                outputFilename = time.strftime(os.path.join(
                    fitDir_t, '%Y%m%d.{0}.v{1}.fit'.format(radar, fitVersion)))
            else:
                raise ValueError(
                    'Fit version must be 2.5 of 3.0 - {0} fit version specified'.format(fitVersion))

            if os.path.isfile(outputFilename):
                print("File exists: %s\n" % outputFilename)
                print('Skipping')
                continue

            status = combine_files(
                inFilenameFormat, outputFilename, fitVersion)

        time += dt.timedelta(days=1)


def combine_files(inFilenameFormat, outputFilename, fitVersion):

    # Set up storage directory
    outDir = os.path.dirname(outputFilename)
    os.makedirs(outDir, exist_ok=True)

    # Make fitacfs for the day
    zippedInputFiles = glob.glob(inFilenameFormat)
    if len(zippedInputFiles) == 0:
        print('No zipped files in %s' % inFilenameFormat)
        return 1

    print('bzips found - run concat_fitacf_daily.py first')
    return 1


if __name__ == '__main__':
    cli_args = parse_args()
    sys.exit(main(cli_args))
