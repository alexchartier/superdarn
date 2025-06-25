%% mwr_vs_sd.m
% Compare the Hankasalmi SuperDARN winds against the Andenes meteor winds
clear

%% Set inputs
times = datenum(2008, 1, 1):datenum(2008, 12, 31);
months = datenum(2008, 1:12, 15);
radarcode = 'han';
boresight = -12; 
sd_fn_fmt = '~/data/superdarn/meteorwindnc/{yyyy}/{mm}/{yyyymmmdd}.{NAME}.nc';
mwr_fn_fmt = {'~/data/meteor_winds/SMR_And_And_32_{yyyymmdd}', '_{yyyymmdd}.h5'};

%% Load
mwr_fn = [filename(mwr_fn_fmt{1}, min(times)), filename(mwr_fn_fmt{2}, max(times))];
mwr = load_mwr(mwr_fn);
sd.Vx = zeros(size(mwr.u0)) * NaN;
sd.time = zeros(size(mwr.u0)) * NaN;
hr = 0:23;
for t = 1:length(times)
    
    sd_fn = filename(sd_fn_fmt, times(t), radarcode);
    try
        sd_t = load_nc(sd_fn);
    catch
        continue
    end
  
    hri = ismember(hr, sd_t.hour);
    sd.Vx(hri, t) = sd_t.Vx;
    sd.time(hri, t) = times(t) + hr(hri) / 24;
    
end
sd.pos = [ncreadatt(sd_fn, '//', 'lat'), ncreadatt(sd_fn, '//', 'lon')];

%% Calculate
maxct = max(mwr.counts, [], 1);
mwr.u0_max = zeros(size(mwr.time)) * NaN;
mwr.v0_max = zeros(size(mwr.time)) * NaN;
mwr.u0_avg = zeros(size(mwr.time)) * NaN;
mwr.v0_avg = zeros(size(mwr.time)) * NaN;
mwr.u0_modelavg = zeros(size(mwr.time)) * NaN;
mwr.v0_modelavg = zeros(size(mwr.time)) * NaN;
for i = 1:length(mwr.time)
    if ~isnan(maxct(i))
        mwr.u0_max(i) = mwr.u0(mwr.counts(:, i) == maxct(i), i);
        mwr.v0_max(i) = mwr.v0(mwr.counts(:, i) == maxct(i), i);
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
mwr_2d.u0_daily_atmax = reshape(mwr.u0_max, [24, ndays]);
mwr_2d.v0_daily_atmax = reshape(mwr.v0_max, [24, ndays]);
mwr_2d.u0_daily_avg = reshape(mwr.u0_avg, [24, ndays]);
mwr_2d.v0_daily_avg = reshape(mwr.v0_avg, [24, ndays]);
mwr_2d.u0_daily_modelavg = reshape(mwr.u0_modelavg, [24, ndays]);
mwr_2d.v0_daily_modelavg = reshape(mwr.v0_modelavg, [24, ndays]);

mwr_2d.u0_30daymed_atmax = movmedian(mwr_2d.u0_daily_atmax, 31, 2, "omitnan");
mwr_2d.v0_30daymed_atmax = movmedian(mwr_2d.v0_daily_atmax, 31, 2, "omitnan");
mwr_2d.u0_30daymed_avg = movmedian(mwr_2d.u0_daily_avg, 31, 2, "omitnan");
mwr_2d.v0_30daymed_avg = movmedian(mwr_2d.v0_daily_avg, 31, 2, "omitnan");
mwr_2d.u0_30daymed_modelavg = movmedian(mwr_2d.u0_daily_modelavg, 31, 2, "omitnan");
mwr_2d.v0_30daymed_modelavg = movmedian(mwr_2d.v0_daily_modelavg, 31, 2, "omitnan");

mwr_2d.Vx_med_atmax = mwr_2d.u0_30daymed_atmax * sind(boresight) + ...
    mwr_2d.v0_30daymed_atmax * cosd(boresight);
mwr_2d.Vx_med_avg = mwr_2d.u0_30daymed_avg * sind(boresight) + ...
    mwr_2d.v0_30daymed_avg * cosd(boresight);
mwr_2d.Vx_med_modelavg = mwr_2d.u0_30daymed_modelavg * sind(boresight) + ...
    mwr_2d.v0_30daymed_modelavg * cosd(boresight);

sd.Vx_med = movmedian(sd.Vx, 31, 2, "omitnan");


%% Plot winds 2d (contourf)
ti = ismember(months, times);

colormap(turbo(30))

climit = [-30, 30];
clf
tiledlayout(3, 1, 'TileSpacing', 'compact')
nexttile
contourf(mwr_2d.Vx_med_avg(:, ti))
set(gca, 'xticklabel', '')
ylabel('Hour (UT)')
clim(climit)
title(sprintf('Andenes MWR (obs count weights) @ %1.1f° N, %1.1f° E', mwr.pos))
grid on 
grid minor

nexttile
contourf(mwr_2d.Vx_med_modelavg(:, ti))
set(gca, 'xticklabel', '')
ylabel('Hour (UT)')
clim(climit)
title(sprintf('Andenes MWR (model count weights) @ %1.1f° N, %1.1f° E', mwr.pos))


nexttile
contourf(sd.Vx_med(:, ti))
clim(climit)
ylabel('Hour (UT)')
% cb = colorbar;
% ylabel(cb, '31-day mean Wind in SD boresight direction (m/s)', 'FontSize', 24)

title(sprintf('Hankasalmi SD (not height resolved) @ %1.1f° N, %1.1f° E', sd.pos))

cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, sprintf('31-day median wind %1.0f° E of N (m/s)', boresight), 'FontSize', 24)
xlabel('Month of 2008')



%% Plotting mean winds 1d
figure
hold on
plot(0:23, mean(mwr_2d.Vx_med_avg(:, ti), 2), 'LineWidth', 3)
plot(0:23, mean(mwr_2d.Vx_med_modelavg(:, ti), 2), 'LineWidth', 3)
plot(0:23, mean(sd.Vx_med(:, ti), 2), 'LineWidth', 3)
xlabel('Hour (UT)')
ylabel(sprintf('Annual mean wind %1.0f° E of N (m/s)', boresight))
xlim([0, 24])
grid on 
grid minor
legend({'Andenes (observed count weights)', 'Andenes (modeled count weights)', 'Hankasalmi'})

