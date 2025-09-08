%% optimize_mwr_ct_model.m
% Optimize the MWR count model weights to match the meteor wind data


year = 2008;
lat = 69.3;
lon = 16;
weights = [0.2, 1.2, 2, 0.2, 91, 8];
meteor_angle_fn = '~/data/meteor_winds/angles_v1.nc';
msis_fn_fmt = '~/data/meteor_winds/msis_{yyyy}_%1.1fN_%1.1fE.mat';

[Peak, FWHM] = mwr_ct_model_v2(year, lat, lon, weights, meteor_angle_fn, msis_fn_fmt);
