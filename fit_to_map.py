"""
fit_to_map.py

Turn .cfit into .map files

Terms:
    iq.dat - raw in-phase and quadrature samples recorded by superdarn radars
    .rawacf - autocorrelation of the iq to the pulse sequence produced by the radar (C binary)
    .fitacf - fitted autocorrelation function containing parameters in local reference frame (range, doppler, azimuth, elevation etc.) (C binary)
              Typically 2-hour files, one per radar
    .cfit - subset of the fitacf (saves on space)  (C binary)
            Typically daily, one per radar
    .grid - Gridded LOS velocities from one radar at a time
    .map - Hemispheric convection map
    

    make_grid - turns .cfit/.fitacf into .grid
    combine_grid - turns .grid into .map
author: A.T. Chartier, 2 November 2020
"""


import os
import sys 
import glob
import datetime as dt
#import bz2
import shutil
import pdb
from run_meteorproc import get_radar_params
sys.path.append('/homes/chartat1/fusionpp/src/nimo/')


def main(
    starttime=dt.datetime(2020, 1, 1),
    endtime=dt.datetime(2020, 1, 5),
    in_dir_fmt='/project/superdarn/alex/cfit/%Y/%m/',
    out_fname_fmt='/project/superdarn/alex/map/%Y/%m/%Y%m%d.map',
    run_dir='./run_fit_to_map/',
    imf_fn='imf_data.txt',
    hdw_dat_dir='../rst/tables/superdarn/hdw/',
    step=1,  # month
    skip_existing=True,
    fit_ext='%Y%m%d.*.cfit',
):
    os.makedirs(run_dir, exist_ok=True)

    # Get list of NH radars
    radar_info = get_radar_params(hdw_dat_dir)
    NH_radars = []
    for k, v in radar_info.items():
        t0 = list(v.keys())[0]
        if v[t0]['glat'] > 0:
            NH_radars.append(k)

    # Loop over time
    time = starttime
    while time < endtime:

        timestr = time.strftime('%Y%m%d')
        os.makedirs(time.strftime(os.path.dirname(out_fname_fmt)), exist_ok=True)

        # Clear out the run directory
        files = glob.glob(os.path.join(run_dir, '*'))
        for f in files:
            os.remove(f)

        # CFit to GRID
        in_fname_fmt_t = time.strftime(os.path.join(in_dir_fmt, fit_ext))
        cfit_fn_list = glob.glob(in_fname_fmt_t)
        
        for cfit_fn in cfit_fn_list:
            if os.path.basename(cfit_fn).split('.')[1] in NH_radars:  # identify just the NH radars
                grd_fn = os.path.join(run_dir, os.path.basename(cfit_fn)) + '.grd'
                arg = 'make_grid -cfit %s > %s' % (cfit_fn, grd_fn)
                os.system(arg)

        # Combine GRID files into one
        grd_fn_fmt = os.path.join(run_dir, '%s*.grd' % timestr)
        cmb_grd_fn = os.path.join(run_dir, '%s.grd' % timestr)
        arg2 = 'combine_grid %s > %s' % (grd_fn_fmt, cmb_grd_fn)
        os.system(arg2)

        # GRID to MAP
        fn_pre = os.path.join(run_dir, timestr)
        empty_map_fn =  fn_pre + '.empty.map'
        hmb_map_fn = fn_pre + '.hmb.map'
        imf_map_fn = fn_pre + '.imf.map'
        mod_map_fn = fn_pre + '.model.map'
        out_fn = time.strftime(out_fname_fmt)

        os.system('map_grd %s > %s' % (cmb_grd_fn, empty_map_fn))
        os.system('map_addhmb %s > %s' % (empty_map_fn, hmb_map_fn))
        os.system('map_addimf -if %s %s > %s' % (imf_fn, hmb_map_fn, imf_map_fn))
        os.system('map_addmodel -o 8 -d l %s > %s' % (imf_map_fn, mod_map_fn))
        os.system('map_fit %s > %s' % (mod_map_fn, out_fn))
        """
        map_grd 20181001.grd > 20181001.empty.map
        map_addhmb 20181001.empty.map > 20181001.hmb.map
        map_addimf -if imfdata.txt 20181001.hmb.map > 20181001.imf.map
        map_addmodel -o 8 -d l 20181001.imf.map > 20181001.model.map
        map_fit  20181001.model.map > 20181001.north.map

        """
    
        print('wrote to %s' % out_fn)
        
        time += dt.timedelta(days=1)


if __name__ == '__main__':
    main()
