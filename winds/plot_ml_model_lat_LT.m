ml_model_fn = '~/data/meteor_winds/ml_model.mat';
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';
mem_fn = '~/data/meteor_winds/mem_3_output_v1.nc';
mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};


hr = 0:23;
yr = 2020;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);
lat = -90:10:90;

Mdl = loadstruct(ml_model_fn);
meteor_angles = load_nc(meteor_angle_fn);

mem = load_mem(mem_fn);
mem_int = interp_mem(mem, mem_fields, mwr.Time, mwr.lat, mwr.lon);

[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, mwr, mem_int, sw, meteor_angles);

