%%
diego_radar = {'riogrande'};
diego_fn_fmt = '~/data/meteor_winds/riogrande_{yyyy}.mat';

koki_radar = 'Jul';
koki_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', '_{yyyymmdd}.h5'};

yr = 2020;
days = datenum(yr, 1:12, 15); % output months
hrs = 0:23;
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_v3.nc';
msis_fn_fmt = '~/data/meteor_winds/msis_{yyyy}_%1.1fN_%1.1fE.mat';
ml_model_fn = '~/data/meteor_winds/ml_model.mat';


%% Compare against Diego's radar
Mdl = loadstruct(ml_model_fn);
mwr = loadstruct(filename(diego_fn_fmt, min(days)));
[~, Peak, FWHM] = gaussfit_mwr_cts(mwr, days, hrs);
[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, mwr, sw_fn_csv, meteor_angle_fn, ...
    msis_fn_fmt);


%% Compare against Koki's radar
Mdl = loadstruct(ml_model_fn);
mwr_times = datenum(yr, 1, 1):datenum(yr, 12, 31);

koki_fn = [filename(koki_fn_fmt{1}, min(mwr_times), koki_radar), ...
    filename(koki_fn_fmt{2}, max(mwr_times), koki_radar)];
mwr = load_mwr(koki_fn, 0);

[~, Peak, FWHM] = gaussfit_mwr_cts(mwr, days, hrs);
[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, mwr, sw_fn_csv, meteor_angle_fn, ...
    msis_fn_fmt);
