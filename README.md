"fit.nc" and "grid.nc" files are made available via Zenodo and
superdarn.jhuapl.edu

These files in netCDF format are designed for use in various high-level
languages (e.g. MATLAB, Python) and in Fortran/C/Java etc, eliminating the need
to acquire/compile/run the Radar Software Toolkit (RST) and providing a common, 
open and reproducible platform for research. 

See plot_grid_nc.py and plot_fit_nc.py for examples of how to plot the data. 
Commandline users with netCDF installed can use ncdump to interrogate files, e.g.
    ncdump -h your_nc_file.nc

To the extent possible, we preserve variable names and other terminology from the RST,
with the goal of maximizing interoperability. Therefore, see 
    https://radar-software-toolkit-rst.readthedocs.io/en/latest/references/general/fitacf/
    https://radar-software-toolkit-rst.readthedocs.io/en/latest/references/general/grid/
for further details of variable definitions. 


The procedure we used to generate netCDF "fit.nc" and "grid.nc" files begins with 
the "RawACF" files that are shared across the network and uploaded to 
    https://www.frdr-dfdr.ca/repo/collection/superdarn

The files are acquired and processed to fitACF. The code executes make_fit (from RST)
using version 2.5 and version 3.0 (two files are generated). fit_speck_removal is 
applied to the v3 files, which "despeckles" the data (removing salt and pepper noise
and interference). Then the "radFov" algorithm (part of DaViTpy) is applied to geolocate
the radar returns using basic assumptions. The output is stored in netCDF format, as 1D
vectors to simplify the structure. 

The version 3 fitACFs are gridded using make_grid (also from RST) and then converted to 
netCDF. The executable command used is stored in the file metadata. 


