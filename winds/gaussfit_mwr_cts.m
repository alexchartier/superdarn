function [A1, B1, C1] = gaussfit_mwr_cts(mwr, months, hrs)

%% gaussfit_mwr_cts.m
% % Returns monthly median of gaussian fit parameters at the specified
% % times/hours
% 
% yr = 2020;
% station = 'JUL';
% months = datenum(yr, 1:12, 15); % output months
% hrs = 0:23;  % output hours
% mwr_mat_fn_fmt = '~/data/meteor_winds/notused_mat/{NAME}_{yyyy}.mat';
% mwr = loadstruct(filename(mwr_mat_fn_fmt, min(months), station));
% [A1, B1, C1] = gaussfit_mwr_cts(mwr, months, hrs)
% 
%
% %% Plot fit parameters
% clf
% tiledlayout(2, 1, 'TileSpacing', 'compact')
% 
% 
% nexttile
% [c, h] = contourf(1:12, hrs, B1);
% clabel(c, h)
% ylabel('Hour (UT)')
% hc = colorbar; 
% set(gca, 'XTickLabels', '') 
% ylabel(hc, 'Peak height (km)')
% clim([85, 95])
% 
% nexttile
% [c, h] = contourf(1:12, hrs, C1); 
% clabel(c, h)
% xlabel('Month'); 
% ylabel('Hour (UT)'); 
% clim([4, 12])
% colormap(gca, spring)
% hc = colorbar; 
% ylabel(hc, 'Full Width @ Half Max (km)')
% 
% 
% 
% 
% 


%% Calculate average counts
times = datenum(year(min(mwr.Time(:))), min(month(months)), 1): ...
    datenum(year(min(mwr.Time(:))), max(month(months)), 31);

ndays = length(times);
mwr.counts_daily = zeros([length(mwr.alt), 24, ndays]) * NaN;
idx = ismember(times, floor(mwr.Time(:)));

mwr.counts_daily(:, :, idx) = reshape(mwr.counts, [length(mwr.alt), 24, sum(idx)]);

mwr.counts_avg = movmedian(mwr.counts_daily, 31, 3, "omitnan");
ti = ismember(times, months);
mwr.counts_avg_monthly = mwr.counts_avg(2:end-1, :, ti);
mwr.alt = mwr.alt(2:end-1);
mwr.counts_avg_monthly(isnan(mwr.counts_avg_monthly)) = 0;

%% Fit
A1 = zeros([length(hrs), length(months)]);  % Max
B1 = zeros([length(hrs), length(months)]);  % Mean
C1 = zeros([length(hrs), length(months)]);  % FWHM
for i = 1:length(hrs)
    for j = 1:length(months)
        f = fit(mwr.alt, mwr.counts_avg_monthly(:, i, j), 'gauss1');
        A1(i, j) = f.a1;
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

