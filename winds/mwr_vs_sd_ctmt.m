%% mwr_vs_sd_ctmt.m
% Compare the Hankasalmi SuperDARN winds against the Andenes and Juliusruh
% meteor winds, plus the CTMT model

% % TODO:
%     1. Add Juliusruh 2008
%     2. Add CTMT with Gaussian kernel
clear

%% Set inputs
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

%% Load
ctmt = loadstruct(ctmt_fn);
for i = 1:length(mwr_radars)
    mwr_fn = [filename(mwr_fn_fmt{1}, min(days), mwr_radars{i}), ...
        filename(mwr_fn_fmt{2}, max(days), mwr_radars{i})];
    mwr.(mwr_radars{i}) = load_mwr(mwr_fn, boresight);
end

sd = load_sd(sd_fn_fmt, radarcode, days, hr);

%% Interpolate CTMT to the SuperDARN location and boresight
Vx_arr = squeeze(ctmt.wind(1, :, :, :, :, :) * sind(boresight) + ...
    ctmt.wind(2, :, :, :, :, :) * cosd(boresight));

ctmt.Vx = zeros([length(ctmt.hours), length(ctmt.months)]);
for im = 1:length(ctmt.months)
    for ih = 1:length(ctmt.hours)
        Vx_prof = zeros(size(ctmt.alts));
        for ia = 1:length(ctmt.alts)
            Vx_prof(ia) = interp2(ctmt.lats, ctmt.lons, ...
                squeeze(Vx_arr(im, ih, ia, :, :))', sd.pos(1), sd.pos(2));
        end

        time = datenum(yr, double(ctmt.months(im)), 15, double(ctmt.hours(ih)), 0, 0);
        [Peak, FWHM] = mwr_ct_model(time, sd.pos(1), sd.pos(2));
        model_cts = exp(-((ctmt.alts - Peak).^2 / FWHM.^2));
        ctmt.Vx(ih, im) = sum(Vx_prof .* model_cts) ./ sum(model_cts);
    end
end



%% Plotting mean winds 1d
ti = ismember(months, days);
figure
hold on
for im = 1:length(mwr_radars)
    plot(0:23, mean(mwr.(mwr_radars{im}).Vx_med_modelavg(:, ti), 2), 'LineWidth', 3)
end
plot(0:23, mean(sd.Vx_med(:, ti), 2), 'LineWidth', 3)
plot(0:23, mean(ctmt.Vx(1:end-1, :), 2), 'LineWidth', 3)

xlabel('Hour (UT)')
ylabel(sprintf('Annual mean wind %1.0f° E of N (m/s)', boresight))
xlim([0, 24])
grid on 
grid minor
legend([mwr_radars, {'Han', 'CTMT'}])





%% Plot winds 2d (contourf)
ti = ismember(months, days);

colormap(turbo(30))

climit = [-35, 35];
clf
tiledlayout(4, 1, 'TileSpacing', 'compact')

nexttile
contourf(1:12, sd.hour, sd.Vx_med(:, ti))
clim(climit)
set(gca, 'xticklabel', '')
ylabel('Hour (UT)')
grid on 
grid minor
title(sprintf('Hankasalmi SDR @ %1.1f° N, %1.1f° E', sd.pos))

nexttile
contourf(ctmt.months, ctmt.hours(1:24), ctmt.Vx(1:24, ti))
clim(climit)
set(gca, 'xticklabel', '')
ylabel('Hour (UT)')
grid on 
grid minor
title(sprintf('CTMT Model @ %1.1f° N, %1.1f° E', sd.pos))

nexttile
contourf(1:12, mwr.And.hour, mwr.And.Vx_med_modelavg(:, ti))
set(gca, 'xticklabel', '')
ylabel('Hour (UT)')
clim(climit)
title(sprintf('Andenes MWR @ %1.1f° N, %1.1f° E', mwr.And.pos))
grid on 
grid minor

nexttile
contourf(1:12, mwr.Jul.hour, mwr.Jul.Vx_med_modelavg(:, ti))
ylabel('Hour (UT)')
clim(climit)
title(sprintf('Juliusruh MWR @ %1.1f° N, %1.1f° E', mwr.Jul.pos))
grid on 
grid minor




cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, sprintf('31-day median wind %1.0f° E of N (m/s)', boresight), 'FontSize', 24)
xlabel('Month of 2008')


