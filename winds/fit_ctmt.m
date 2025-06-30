%% fit_ctmt.m
% Produce a 
yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);
radarcode = 'han';
boresight = -12; 
hr = 0:23;
sd_fn_fmt = '~/data/superdarn/meteorwindnc/{yyyy}/{mm}/{yyyymmmdd}.{NAME}.nc';
mwr_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
mwr_radars = {'And', 'Jul'};
ctmt_fn = '~/data/ctmt/ctmt.mat';
