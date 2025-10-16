function mwr_2d = load_mwr_simple(mwr_fn)
%% load_mwr.m
% times = [datenum(2008, 1, 1), datenum(2008, 12, 31)];
% mwr_fn_fmt = {'~/data/meteor_winds/SMR_And_And_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
% % Load
% mwr_fn = [filename(mwr_fn_fmt{1}, min(times)), filename(mwr_fn_fmt{2}, max(times))];
% mwr = load_mwr_simple(mwr_fn);

%% HDF5 read
mwr.u0 = h5read(mwr_fn, '/wind/u0');
mwr.v0 = h5read(mwr_fn, '/wind/v0');
mwr.alt = h5read(mwr_fn, '/info/altitude');
mwr.pos = h5read(mwr_fn, '/info/RadarPos');
mwr.counts = h5read(mwr_fn, '/info/counts');
mwr.time = h5read(mwr_fn, '/info/datenums');



ndays = length(mwr.time) / 24;
mwr_2d.Time = reshape(mwr.time, [24, ndays]);
mwr_2d.u0 = reshape(mwr.u0, [length(mwr.alt), 24, ndays]);
mwr_2d.v0 = reshape(mwr.v0, [length(mwr.alt), 24, ndays]);
mwr_2d.counts = reshape(mwr.counts, [length(mwr.alt), 24, ndays]);
mwr_2d.alt = mwr.alt;
mwr_2d.lat = mwr.pos(1);
mwr_2d.lon = mwr.pos(2);