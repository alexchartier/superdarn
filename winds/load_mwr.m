function mwr_2d = load_mwr(mwr_fn, boresight)
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

%% calculate weighted average winds in the SD direction
maxct = max(mwr.counts, [], 1);
mwr.u0_avg = zeros(size(mwr.time)) * NaN;
mwr.v0_avg = zeros(size(mwr.time)) * NaN;
mwr.u0_modelavg = zeros(size(mwr.time)) * NaN;
mwr.v0_modelavg = zeros(size(mwr.time)) * NaN;
for i = 1:length(mwr.time)
    if ~isnan(maxct(i))
        mwr.u0_avg(i) = nansum(mwr.u0(:, i) .* mwr.counts(:, i)) / nansum(mwr.counts(:, i));
        mwr.v0_avg(i) = nansum(mwr.v0(:, i) .* mwr.counts(:, i)) / nansum(mwr.counts(:, i));

        [Peak, FWHM] = mwr_ct_model(mwr.time(i), mwr.pos(1), mwr.pos(2));
        model_cts = exp(-((mwr.alt - Peak).^2 / FWHM.^2));
        mwr.u0_modelavg(i) = nansum(mwr.u0(:, i) .* model_cts /...
            sum(model_cts(~isnan(mwr.u0(:, i)))));
        mwr.v0_modelavg(i) = nansum(mwr.v0(:, i) .* model_cts /...
            sum(model_cts(~isnan(mwr.v0(:, i)))));

    end
end

ndays = length(mwr.time) / 24;
mwr_2d.Time = reshape(mwr.time, [24, ndays]);
mwr_2d.u0_daily_avg = reshape(mwr.u0_avg, [24, ndays]);
mwr_2d.v0_daily_avg = reshape(mwr.v0_avg, [24, ndays]);
mwr_2d.u0_daily_modelavg = reshape(mwr.u0_modelavg, [24, ndays]);
mwr_2d.v0_daily_modelavg = reshape(mwr.v0_modelavg, [24, ndays]);

mwr_2d.u0_30daymed_avg = movmedian(mwr_2d.u0_daily_avg, 31, 2, "omitnan");
mwr_2d.v0_30daymed_avg = movmedian(mwr_2d.v0_daily_avg, 31, 2, "omitnan");
mwr_2d.u0_30daymed_modelavg = movmedian(mwr_2d.u0_daily_modelavg, 31, 2, "omitnan");
mwr_2d.v0_30daymed_modelavg = movmedian(mwr_2d.v0_daily_modelavg, 31, 2, "omitnan");

mwr_2d.Vx_med_avg = mwr_2d.u0_30daymed_avg * sind(boresight) + ...
    mwr_2d.v0_30daymed_avg * cosd(boresight);
mwr_2d.Vx_med_modelavg = mwr_2d.u0_30daymed_modelavg * sind(boresight) + ...
    mwr_2d.v0_30daymed_modelavg * cosd(boresight);
mwr_2d.pos = mwr.pos;
mwr_2d.hour = unique(hour(mwr_2d.Time));
mwr_2d.counts = reshape(mwr.counts, [11, 24, 366]);
mwr_2d.u0_raw = reshape(mwr.u0, [size(mwr.u0, 1), size(mwr_2d.Time, 1), size(mwr_2d.Time, 2)]);
mwr_2d.alt = mwr.alt;

