function [A1, B1, C1] = gaussfit_mwr_cts(mwr, months, hrs)

%% gaussfit_mwr_cts.m
% % Returns monthly median of gaussian fit parameters at the specified
% % times/hours
% 
% yr = 2008;
% station = 'AND';
% months = datenum(yr, 1:12, 15); % output months
% hrs = 0:23;  % output hours
% mwr_fn = '~/data/meteor_winds/SMR_AND_AND_32_20080101_20081231.h5'
% 
% mwr = load_mwr(mwr_fn, 0);
% [A1, B1, C1] = gaussfit_mwr_cts(mwr, months, hrs)
% 
%
% %% Plot fit parameters
% clf
% tiledlayout(3, 1, 'TileSpacing', 'compact')
% 
% nexttile
% [c, h] = contourf(1:12, hrs, A1);  % TODO: A1=Gaussian peak amplitude
% clabel(c, h)
% title(sprintf('%i %s meteor echoes (smoothed, monthly median)', yr, station))
% ylabel('Hour (UT)')
% hc = colorbar; 
% set(gca, 'XTickLabels', '') 
% ylabel(hc, 'Max counts (#)')
% % clim([85, 95])
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
% hc = colorbar; 
% ylabel(hc, 'Full Width @ Half Max (km)')
% 
% 
% 
% 
% 


%% Load
times = unique(floor(mwr.Time(:)));
ndays = length(times);
mwr.counts_daily = reshape(mwr.counts, [11, 24, ndays]);
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

