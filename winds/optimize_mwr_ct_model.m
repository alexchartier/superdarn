%% optimize_mwr_ct_model.m
% Optimize the MWR count model weights to match the meteor wind data
year = 2008;
% lat = 69.3;
% lon = 16;
weights = [0.2, 1.2, 2, 0.2, 91, 8];
meteor_angle_fn = '~/data/meteor_winds/angles_v3.nc';
msis_fn_fmt = '~/data/meteor_winds/msis_{yyyy}_%1.1fN_%1.1fE.mat';
boresight = 0;

mwr_radars = {'And'};
mwr_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', '_{yyyymmdd}.h5'};


%%
for i = 1:length(mwr_radars)
    days = datenum(year, 1, 1):datenum(year, 12, 31);

    mwr_fn = [filename(mwr_fn_fmt{1}, min(days), mwr_radars{i}), ...
        filename(mwr_fn_fmt{2}, max(days), mwr_radars{i})];
    %mwrs.(mwr_radars{i}) = load_mwr(mwr_fn, boresight);
    mwr = load_mwr(mwr_fn, boresight);
end

[Peak, FWHM] = mwr_ct_model_v2(year, mwr.pos(1), mwr.pos(1), weights, ...
    meteor_angle_fn, msis_fn_fmt);

