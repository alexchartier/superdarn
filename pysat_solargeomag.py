from __future__ import print_function
from builtins import input
import datetime as dt
import numpy as np
import sys
import pdb

from netCDF4 import Dataset
import pandas as pds
import pysat
from pysat.instruments.methods import sw as sw_methods



def main():
    """ Download and write the solargeomag file containing F10.7, Kp, and Ap
    """

    # Prompt or take command line input
    input_args = process_command_line_input()
    input_prompts = [
        'Output filename: ',
        'Start date (YYYY-MM-DD or none/enter for today): ',
        'End date (YYYY-MM-DD or none/enter for today): ',
    ]

    while len(input_args) < len(input_prompts):
        input_args.append(input(input_prompts[len(input_args)]))

    outfile = input_args[0]
    stime = dt.datetime.strptime(none_string(input_args[1]), '%Y-%m-%d')
    etime = dt.datetime.strptime(none_string(input_args[2]), '%Y-%m-%d')
    f107_kp_inst, ap_inst = get_f107_kp_ap(outfile, stime, etime)


# This would call the routines process_command_line_input and none_string,
# which are currently duplicated here for simplicity
#
# from validation.tools import run_tools
#
# Routines from run_tools
def none_string(line):
    """ Determine whether a string should be None

    Parameters
    ----------
    line : string
        Line to be tested

    Returns
    -------
    out_line : string or NoneType
        None if all-lowercase version of line is "none" or line is zero length.
        Otherwise returns original value of line

    """
    if line.lower() == "none" or len(line) == 0:
        return None
    else:
        return line

def process_command_line_input():
    """ Process command line input, needed to possible ipython use

    Returns
    -------
    input_args : list
        List of input arguements

    """

    input_args = sys.argv
    if input_args[0].find('ipython') >= 0:
        input_args = list()
    else:
        input_args.pop(0)

    return input_args
# End of run_tools routines

def evaluate_today(dtime):
    return dtime.date() == dt.datetime.today().date()

def get_recent_f107_data(today=dt.datetime.today()):
    """ Get today's F10.7 forecasts and historic 30-day record from SWPC

    Parameters
    ----------
    today : (dt.datetime)
        Today's datetime (default=dt.datetime.today())

    Returns
    -------
    f107_inst : (pysat.Instrument)
        pysat Instrument object containing the last 30 days of F10.7 and
        the 3-day forcast

    """

    # Initialize the instrument objects
    standard_inst = pysat.Instrument('sw', 'f107', 'daily')
    forecast_inst = pysat.Instrument('sw', 'f107', 'forecast')

    # Download today's files
    standard_inst.download()
    forecast_inst.download()

    # Load today's data
    standard_inst.load(date=today)
    forecast_inst.load(date=today)

    # Combine the standard and forecast data into a single instrument
    f107_inst = sw_methods.combine_f107(standard_inst, forecast_inst)

    return f107_inst

def get_historic_f107_data(stime, etime):
    """ Get historic F10.7 for a specified range of dates

    Parameters
    ----------
    stime : (dt.datetime)
        Start time
    etime : (dt.datetime)
        End time

    Returns
    -------
    f107_inst : (pysat.Instrument)
        pysat Instrument object containing the desired date range

    """

    # Initialize the instrument objects
    all_inst = pysat.Instrument('sw', 'f107', 'all')
    prelim_inst = pysat.Instrument('sw', 'f107', 'prelim')

    # Download the most recent historic file and desired preliminary data
    all_inst.download()
    prelim_inst.download(start=stime, stop=etime)

    # Combine the historic and preliminary data into a single instrument
    # for the desired range
    f107_inst = sw_methods.combine_f107(all_inst, prelim_inst, start=stime,
                                        stop=etime)

    return f107_inst

def add_f107a(f107_inst):
    """ Add F10.7a to input instrument object, using historic data when needed

    Parameters
    ----------
    f107_inst : (pysat.Instrument)
        Instrument containing F10.7 data

    """

    # Determine the desired time range
    start_time = f107_inst.index[0] - pds.DateOffset(days=41)
    stop_time = f107_inst.index[0]

    # Initialize the historic instrument objects
    hist_inst = get_historic_f107_data(start_time, stop_time)

    if hist_inst.empty:
        raise RuntimeError('unable to load past F107 data for {:}-{:}'.format(
                                                        start_time, stop_time))
    
    # Ensure enough data was loaded
    i = 0
    while (stop_time - hist_inst.index[-1]).total_seconds() > 86400.0 and i < 5:
        temp_inst = hist_inst.copy()
        temp_inst.load(date=hist_inst.index[-1] + pds.DateOffset(days=1))
        hist_inst.data = hist_inst.data.combine_first(temp_inst.data)
        i += 1

    if (stop_time - hist_inst.index[-1]).total_seconds() > 86400.0:
        # If there is just a one-day gap, go on.  This can happen at certain
        # times of day
        raise RuntimeError('trouble downloading desired data')
            
    # Combine the input and historic data, prioritizing input
    f107a_input = f107_inst.copy()
    f107a_input.data = f107_inst.data.combine_first(hist_inst.data)

    # Calculate the F10.7a
    pysat.instruments.sw_f107.calc_f107a(f107a_input)

    # Add the F10.7a to the output instrument
    f107_inst.meta['f107a'] = f107a_input.meta['f107a']
    f107_inst['f107a'] = f107a_input['f107a'].loc[f107_inst.index[0]:
                                                  f107_inst.index[-1]]

    return

def get_recent_kp_data(today=dt.datetime.today()):
    """ Get today's Kp forecasts and historic 30-day record from SWPC

    Parameters
    ----------
    today : (dt.datetime)
        Today's datetime (default=dt.datetime.today())

    Returns
    -------
    kp_inst : (pysat.Instrument)
        pysat Instrument object containing the last 30 days of Kp and
        the 3-day forcast

    """

    # Initialize the instrument objects
    recent_inst = pysat.Instrument('sw', 'kp', 'recent')
    forecast_inst = pysat.Instrument('sw', 'kp', 'forecast')

    # Download today's files
    recent_inst.download()
    forecast_inst.download()

    # Load today's data
    recent_inst.load(date=today)
    forecast_inst.load(date=today)

    # Combine the data into a single instrument
    kp_inst = sw_methods.combine_kp(recent_inst=recent_inst,
                                    forecast_inst=forecast_inst)

    return kp_inst

def get_historic_kp_data(stime, etime):
    """ Get today's Kp forecasts and historic 30-day record from SWPC

    Parameters
    ----------
    stime : (dt.datetime)
        Start time
    etime : (dt.datetime)
        End time

    Returns
    -------
    kp_inst : (pysat.Instrument)
        pysat Instrument object containing the last 30 days of Kp and
        the 3-day forcast

    """

    # Initialize the instrument objects
    standard_inst = pysat.Instrument('sw', 'kp', '')
    recent_inst = pysat.Instrument('sw', 'kp', 'recent')

    # Download today's files
    standard_inst.download(start=stime, stop=etime)
    recent_inst.download(start=stime, stop=etime)

    # Combine the data into a single instrument
    kp_inst = sw_methods.combine_kp(standard_inst=standard_inst,
                                    recent_inst=recent_inst, start=stime,
                                    stop=etime)

    return kp_inst

def combine_f107_kp(f107_inst, kp_inst):
    """ Combine F10.7 and Kp data, saving only overlapping data

    Parameters
    ----------
    f107_inst : (pysat.Instrument)
        pysat Instrument with F10.7 data
    kp_inst : (pysat.Instrument)
        pysat Instrument with Kp data

    Returns
    -------
    f107_kp_inst : (pysat.Instrument)
        pysat Instrument with F10.7 and Kp data for the same range and
        cadence

    """

    # Initialize the output instrument
    f107_kp_inst = pysat.Instrument()
    f107_kp_inst.platform = 'sw'
    f107_kp_inst.name = 'f107_kp'
    f107_kp_inst.tag = "_".join([f107_inst.tag, kp_inst.tag])

    # Get the Kp output frequency
    del_time = (kp_inst.index[1:] - kp_inst.index[0:-1]).min().total_seconds()
    freq = "{:.0f}S".format(del_time)

    # Get the F10.7 at this new frequency
    f107 = f107_inst['f107'].resample(freq).pad()
    out_time = list(f107.index)
    out_f107 = list(f107)

    # Add frequency to the Kp time index
    kp_inst.index.freq = freq

    # Extend the F10.7 data until the end of the last day if there is Kp data
    if out_time[-1] < kp_inst.index[-1]:
        i = abs(kp_inst.index - out_time[-1]).argmin() + 1
        imax = len(kp_inst.index)
        while i < imax and out_time[-1].date() == kp_inst.index[i].date():
            out_time.append(kp_inst.index[i])
            out_f107.append(out_f107[-1])
            i += 1

    out_time = np.array(out_time)
    out_f107 = np.array(out_f107)
            
    # Determine the date range, using the latest start and soonest stop date
    start = max([out_time[0], kp_inst.index[0]])
    stop = min([out_time[-1], kp_inst.index[-1]])

    tdiff_start = np.array([abs(t - start) for t in out_time])
    tdiff_stop = np.array([abs(t - stop) for t in out_time])
    fstart = tdiff_start.argmin()
    fstop = tdiff_stop.argmin() + 1
    
    kstart = abs(kp_inst.index - start).argmin()
    kstop = abs(kp_inst.index - stop).argmin() + 1

    # Save the output data
    f107_kp_inst.data = pds.DataFrame({"f107": out_f107[fstart:fstop],
                                       "Kp": kp_inst['Kp'][kstart:kstop]},
                                      index=out_time[fstart:fstop])
    f107_kp_inst.meta = f107_inst.meta
    f107_kp_inst.meta['Kp'] = kp_inst.meta['Kp']
    f107_kp_inst.date = start
    f107_kp_inst.doy = int(start.strftime('%j'))

    return f107_kp_inst
    
def write_solargeomag_file(filename, f107_kp_inst, ap_inst):
    """ Write a HDF5 file containing F10.7, Kp, and Ap data

    Parameters
    ----------
    filename : (str)
        Output filename with directory structure and .nc extension
    f107_kp_inst : (pysat.Instrument)
        pysat instrument containing F10.7 and Kp data
    ap_inst : (pysat.Instrument or NoneType)
        pysat instrument containing the 45-day forecasts of F10.7 and Ap or
        None to exclude the future block from the file

    Returns
    -------
    Void

    """

    # Open the data file and add header information
    root_grp = Dataset(filename, "w", format="NETCDF4")
    root_grp.description = "".join(
        ["F10.7, F10.7a, Kp, ap, and Ap ",
        "" if ap_inst is None else " recent",
        "historical data ",
        "" if ap_inst is None else "and forecasts ",
        "made on {:}".format(dt.datetime.today())],
    )
    
    # Define the two different data groups and their dimension (time)
    recent_grp = root_grp.createGroup('recent')
    recent_grp.description = "".join(
        ["Solar and geomagnetic indices for the ",
         "requested time period"
         if ap_inst is None else
         "last 30 days and a 3-day forecast"],
    )
    recent_time = recent_grp.createDimension('time', None)

    if ap_inst is not None:
        forecast_grp = root_grp.createGroup('forecast')
        forecast_grp.description = "45 day forecast of F10.7, F10.7a, and Ap"
        forecast_time = forecast_grp.createDimension('time', None)

    # Add the data variables for the recent group
    recent_year = recent_grp.createVariable('year', 'i4', ('time',))
    recent_year.units = "Years"
    recent_year.description = "Years"
    recent_year[:] = [tt.year for tt in f107_kp_inst.index]

    recent_doy = recent_grp.createVariable('doy', 'i4', ('time',))
    recent_doy.units = "Days"
    recent_doy.description = "Days of year"
    recent_doy[:] = [int(tt.strftime("%j")) for tt in f107_kp_inst.index]

    recent_sod = recent_grp.createVariable('utsod', 'i4', ('time',))
    recent_sod.units = "Seconds"
    recent_sod.description = "Universal Time seconds of day"
    recent_sod[:] = [tt.hour * 3600 + tt.minute * 60 + tt.second
                  for tt in f107_kp_inst.index]

    recent_f107 = recent_grp.createVariable('f107', 'i4', ('time',))
    f107_meta = f107_kp_inst.meta['f107']
    recent_f107.units = f107_meta[f107_kp_inst.meta.units_label]
    recent_f107.description = f107_meta[f107_kp_inst.meta.desc_label]
    nan_index = f107_kp_inst.index[np.isnan(f107_kp_inst['f107'].values.astype(
                float))]
    f107_kp_inst.data.loc[nan_index, ('f107')] = -1
    recent_f107[:] = list(f107_kp_inst['f107'])

    recent_f107a = recent_grp.createVariable('f107a', 'f4', ('time',))
    f107a_meta = f107_kp_inst.meta['f107a']
    recent_f107a.units = f107a_meta[f107_kp_inst.meta.units_label]
    recent_f107a.description = f107a_meta[f107_kp_inst.meta.desc_label]
    nan_index = f107_kp_inst.index[np.isnan(f107_kp_inst['f107a'].values.astype(
                float))]
    f107_kp_inst.data.loc[nan_index, ('f107a')] = -1
    recent_f107a[:] = list(f107_kp_inst['f107a'])

    recent_kp = recent_grp.createVariable('kp', 'f4', ('time',))
    kp_meta = f107_kp_inst.meta['Kp']
    recent_kp.units = kp_meta[f107_kp_inst.meta.units_label]
    recent_kp.description = kp_meta[f107_kp_inst.meta.desc_label]
    nan_index = f107_kp_inst.index[np.isnan(f107_kp_inst['Kp'].values.astype(
                float))]
    f107_kp_inst.data.loc[nan_index, ('Kp')] = -1
    recent_kp[:] = list(f107_kp_inst['Kp'])

    recent_Ap = recent_grp.createVariable('ap', 'f4', ('time',))
    Ap_meta = f107_kp_inst.meta['Ap']
    recent_Ap.units = Ap_meta[f107_kp_inst.meta.units_label]
    recent_Ap.description = Ap_meta[f107_kp_inst.meta.desc_label]
    nan_index = f107_kp_inst.index[np.isnan(f107_kp_inst['Ap'].values.astype(
                float))]
    f107_kp_inst.data.loc[nan_index, ('Ap')] = -1
    recent_Ap[:] = list(f107_kp_inst['Ap'])

    recent_dap = recent_grp.createVariable('daily_ave_ap', 'f4', ('time',))
    dap_meta = f107_kp_inst.meta['daily_ave_ap']
    recent_dap.units = dap_meta[f107_kp_inst.meta.units_label]
    recent_dap.description = dap_meta[f107_kp_inst.meta.desc_label]
    nan_index = f107_kp_inst.index[np.isnan(
            f107_kp_inst['daily_ave_ap'].values.astype(float))]
    f107_kp_inst.data.loc[nan_index, ('daily_ave_ap')] = -1
    recent_dap[:] = list(f107_kp_inst['daily_ave_ap'])

    recent_ap3h = recent_grp.createVariable('ap_3hr', 'f4', ('time',))
    ap3h_meta = f107_kp_inst.meta['3hr_ap']
    recent_ap3h.units = ap3h_meta[f107_kp_inst.meta.units_label]
    recent_ap3h.description = ap3h_meta[f107_kp_inst.meta.desc_label]
    nan_index = f107_kp_inst.index[np.isnan(
            f107_kp_inst['3hr_ap'].values.astype(float))]
    f107_kp_inst.data.loc[nan_index, ('3hr_ap')] = -1
    recent_ap3h[:] = list(f107_kp_inst['3hr_ap'])

    # Add the data variables for the forecast group if desired
    if ap_inst is not None:
        forecast_year = forecast_grp.createVariable('year', 'i4', ('time',))
        forecast_year.units = "Years"
        forecast_year.description = "Years"
        forecast_year[:] = [tt.year for tt in ap_inst.index]

        forecast_doy = forecast_grp.createVariable('doy', 'i4', ('time',))
        forecast_doy.units = "Days"
        forecast_doy.description = "Days of year"
        forecast_doy[:] = [int(tt.strftime("%j")) for tt in ap_inst.index]

        forecast_sod = forecast_grp.createVariable('utsod', 'i4', ('time',))
        forecast_sod.units = "Seconds"
        forecast_sod.description = "Universal Time seconds of day"
        forecast_sod[:] = [tt.hour * 3600 + tt.minute * 60 + tt.second
                           for tt in ap_inst.index]

        forecast_f107 = forecast_grp.createVariable('f107', 'i4', ('time',))
        f107_meta = ap_inst.meta['f107']
        forecast_f107.units = f107_meta[ap_inst.meta.units_label]
        forecast_f107.description = f107_meta[ap_inst.meta.desc_label]
        nan_index = ap_inst.index[np.isnan(ap_inst['f107'].values.astype(float))]
        ap_inst.data.loc[nan_index, ('f107')] = -1
        forecast_f107[:] = list(ap_inst['f107'])

        forecast_f107a = forecast_grp.createVariable('f107a', 'f4', ('time',))
        f107a_meta = ap_inst.meta['f107a']
        forecast_f107a.units = f107a_meta[ap_inst.meta.units_label]
        forecast_f107a.description = f107a_meta[ap_inst.meta.desc_label]
        nan_index = ap_inst.index[np.isnan(ap_inst['f107a'].values.astype(float))]
        ap_inst.data.loc[nan_index, ('f107a')] = -1
        forecast_f107a[:] = list(ap_inst['f107a'])

        forecast_kp = forecast_grp.createVariable('Kp', 'f4', ('time',))
        kp_meta = ap_inst.meta['Kp']
        forecast_kp.units = kp_meta[ap_inst.meta.units_label]
        forecast_kp.description = kp_meta[ap_inst.meta.desc_label]
        nan_index = ap_inst.index[np.isnan(ap_inst['Kp'].values.astype(float))]
        ap_inst.data.loc[nan_index, ('Kp')] = -1
        forecast_kp[:] = list(ap_inst['Kp'])

        forecast_ap = forecast_grp.createVariable('ap', 'i4', ('time',))
        ap_meta = ap_inst.meta['ap']
        forecast_ap.units = ap_meta[ap_inst.meta.units_label]
        forecast_ap.description = ap_meta[ap_inst.meta.desc_label]
        nan_index = ap_inst.index[np.isnan(ap_inst['ap'].values.astype(float))]
        ap_inst.data.loc[nan_index, ('ap')] = -1
        forecast_ap[:] = list(ap_inst['ap'])

    # Close filehandle and exit
    root_grp.close()
    print('Wrote f107 etc. to %s' % filename)
    return

def get_f107_kp_ap(outfile, stime, etime):

    # Cast the date appropriately and determine if it is today or in the past
    if stime is None:
        stime = dt.datetime.today()
    istoday = stime.date() == dt.datetime.today().date()

    # Get the F10.7 and Kp data
    if istoday:
        f107_inst = get_recent_f107_data(today=stime)
        kp_inst = get_recent_kp_data(today=stime)
    else:
        f107_inst = get_historic_f107_data(stime, etime)
        kp_inst = get_historic_kp_data(stime, etime)

    # Combine the Kp and F10.7 data, ensuring the same temporal cadance
    f107_kp_inst = combine_f107_kp(f107_inst, kp_inst)

    # Calculate the F10.7a
    add_f107a(f107_kp_inst)

    # Add the 3-hourly ap and daily Ap to the Kp instrument
    pysat.instruments.sw_kp.convert_3hr_kp_to_ap(f107_kp_inst)
    sw_methods.calc_daily_Ap(f107_kp_inst, running_name="daily_ave_ap")

    # Get the 45-day predictions of Ap and F10.7 if forecast block is desired
    if istoday:
        ap_inst = pysat.Instrument('sw', 'f107', '45day')
        ap_inst.download()
        ap_inst.load(date=today)

        # Calculate the F10.7a
        add_f107a(ap_inst)

        # Add the Kp to the 45-day predictions of Ap
        ap_inst.data['Kp'], kp_meta = sw_methods.convert_ap_to_kp(
            ap_inst['ap'],
            ap_inst.meta['ap'].fill,
            ap_inst.meta['ap'].long_name,
        )

        ap_inst.meta['Kp'] = kp_meta['Kp']
    else:
        ap_inst = None

    # Write the output file
    write_solargeomag_file(outfile, f107_kp_inst, ap_inst)

    return f107_kp_inst, ap_inst


if __name__ == '__main__':
    main()
