%% plot_mwr.m
mwr_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);
hr = 0:23;
mwr_radars = {'And'};
boresight = -12;

%%
for i = 1:length(mwr_radars)
    mwr_fn = [filename(mwr_fn_fmt{1}, min(days), mwr_radars{i}), ...
        filename(mwr_fn_fmt{2}, max(days), mwr_radars{i})];
    mwr.(mwr_radars{i}) = load_mwr(mwr_fn, boresight);
end


%%
mwr = mwr.And;

contourf(squeeze(mwr.counts(:, 1, :)))