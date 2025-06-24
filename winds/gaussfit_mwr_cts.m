%% gaussfit_mwr_cts.m

% times = datenum(2008, 1, 1):datenum(2008, 12, 31);
% months = datenum(2008, 1:12, 15);
year =2020;
times = datenum(year, 1, 1):datenum(year, 12, 31);
months = datenum(year, 1:12, 15);
hrs = 0:23;
mwr_fn_fmt = {'~/data/meteor_winds/SMR_And_And_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
ref_ht = 200*1E3;


%% Load
mwr_fn = [filename(mwr_fn_fmt{1}, min(times)), filename(mwr_fn_fmt{2}, max(times))];
mwr = load_mwr(mwr_fn);
ndays = length(mwr.time) / 24;
mwr.counts_daily = reshape(mwr.counts, [11, 24, ndays]);
mwr.counts_avg = movmedian(mwr.counts_daily, 31, 3, "omitnan");
ti = ismember(times, months);
mwr.counts_avg_monthly = mwr.counts_avg(2:end-1, :, ti);
mwr.alt = mwr.alt(2:end-1);
idx = mwr.counts_avg_monthly(1, :, :) > 100;
mwr.counts_avg_monthly(1, idx) = 0;
month_times = times(ti);

%% Fit
B1 = zeros([length(hrs), length(months)]);  % Mean
C1 = zeros([length(hrs), length(months)]);  % FWHM
for i = 1:length(hrs)
    for j = 1:length(months)
        f = fit(mwr.alt, mwr.counts_avg_monthly(:, i, j), 'gauss1');
        B1(i, j) = f.b1;
        C1(i, j) = f.c1;
    end
end

%% Plot gaussian fitting example
% clf
% h = plot(f); 
% hold on
% plot(mwr.alt, mwr.counts_avg_monthly(:, i, j), 'xk', 'MarkerSize', 20, 'LineWidth', 4)
% legend({'Gaussian fit', 'Observed counts'}); set(h, 'LineWidth', 3)
% grid on
% grid minor
% xlabel('Alt (km)')
% ylabel('# Meteor counts')

%% Plot fit parameters
clf

tiledlayout(2, 1, 'TileSpacing', 'compact')
nexttile

LT = hrs + lon / 360 * 24; 
LT(LT > 24) = LT(LT > 24) - 24;
[c, h] = contourf(1:12, LT, B1);
clabel(c, h)


title('Gaussian fitted meteor counts (monthly median)')
ylabel('Hour (LT)')
hc = colorbar; 
set(gca, 'XTickLabels', '') 
ylabel(hc, 'Peak height (km)')
clim([85, 95])

nexttile
[c, h] = contourf(1:12, LT, C1); 
clabel(c, h)


xlabel('Month of 2008'); 
ylabel('Hour (LT)'); 
clim([5, 12])
hc = colorbar; ylabel(hc, 'Full Width Half Max (km)')


%% Integrate MSIS density from peak up, and from 90 km up
for i = 1:length(hrs)
    for j = 1:length(months)
        time = month_times(j) + hrs(i) / 24;
        N_90_up(i, j) = calc_msis_density(time, ref_ht:ref_ht+1, lat, lon);
        % N_peak_up(i, j) = calc_msis_density(time, B1(i, j) * 1E3:B1(i, j) * 1E3 + 1, lat, lon);

        fprintf('%s %1.4e %1.4e\n', datestr(time), N_90_up(i, j), N_peak_up(i, j))
    end
end


% subplot(2, 1, 1); 
contourf(N_90_up); colorbar; 
% subplot(2, 1, 2); contourf(N_peak_up);colorbar

%% Calculate MSIS pressures at peak heights and at 90 km
P_90 = zeros([length(hrs), length(months)]);  % Mean
P_peak = zeros([length(hrs), length(months)]);  % FWHM
for i = 1:length(hrs)
    for j = 1:length(months)
        time = month_times(j) + hrs(i) / 24;
        P_90(i, j) = calc_msis_pressure(time, ref_ht, lat, lon);
        P_peak(i, j) = calc_msis_pressure(time, B1(i, j) * 1E3, lat, lon);
        fprintf('%s %1.4e %1.4e\n', datestr(time), P_90(i, j), P_peak(i, j))

    end
end

subplot(2, 1, 1); contourf(P_90); colorbar; subplot(2, 1, 2); contourf(P_peak);colorbar


%%  Contour plot of gaussian fit parameters
contourf(months, hrs, B1)
xlabel('Month of 2008')
ylabel('Hour (UT)')
cb = colorbar;
ylabel(cb, 'Peak height of Gaussian fit to count rate', 'FontSize', 24)
datetick('keeplimits')

%% Contour plot meteor count altitudes (4X contourf + line plot)
colormap('parula')
clf
tiledlayout(4, 1, 'TileSpacing', 'compact')
hrs = 0:23;
for hr = 0:6:18
nexttile
contourf(1:12, mwr.alt, squeeze(mwr_2d.counts_avg(:, hrs == hr, ti)))
clim([0, 75])
if hr < 18
    set(gca, 'XTickLabels', '')
else
    xlabel('Month of 2008')
end
ylabel(sprintf('%i UT\nAlt (km)', hr))
end

cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, sprintf('31-day median count rate', boresight), 'FontSize', 24)

figure
plot(mean(mwr_2d.counts_avg(:, :, ti), 3), mwr.alt, '-x', 'LineWidth', 2)
    
    ylabel('Alt (km)')
    xlabel('Counts')
