function mwr = load_mwr(mwr_fn)
%% load_mwr.m
% times = [datenum(2008, 1, 1), datenum(2008, 12, 31)];
% mwr_fn_fmt = {'~/data/meteor_winds/SMR_And_And_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
% % Load
% mwr_fn = [filename(mwr_fn_fmt{1}, min(times)), filename(mwr_fn_fmt{2}, max(times))];
% mwr = load_mwr(mwr_fn);

%% 
mwr.u0 = h5read(mwr_fn, '/wind/u0');
mwr.v0 = h5read(mwr_fn, '/wind/v0');
mwr.alt = h5read(mwr_fn, '/info/altitude');
mwr.pos = h5read(mwr_fn, '/info/RadarPos');
mwr.counts = h5read(mwr_fn, '/info/counts');
mwr.time = h5read(mwr_fn, '/info/datenums');
