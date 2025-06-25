function [Peak, FWHM] = mwr_ct_model(time, lat, lon);
% yr = 2008;
% hrs = 0:23;
% lat = 60;
% lon = 15;
% months = datenum(yr, 1:12, 15);
% 
% Peak = zeros(length(hrs), length(months));
% FWHM = zeros(length(hrs), length(months));
% for i = 1:length(hrs)
%     for j = 1:length(months)
%         time = months(j) + hrs(i) / 24;
%         [Peak(i, j), FWHM(i, j)] = mwr_ct_model(time, lat, lon);
%     end
% end
%
% tiledlayout(2, 1, 'TileSpacing', 'compact')
% nexttile
% [c, h] = contourf(1:12, hrs, Peak); 
% clabel(c, h)
% clim([85, 95]); 
% set(gca, 'XTickLabels', '') 
% ylabel('Hour (UT)')
% hc = colorbar; 
% ylabel(hc, 'Peak height (km)')
%
%
% nexttile
% [c, h] = contourf(1:12, hrs, FWHM); 
% clabel(c, h)
% clim([5, 12]);
% xlabel('Month')
% ylabel('Hour (UT)')
% hc = colorbar; 
% ylabel(hc, 'Full Width Half Max (km)')

%% 
LT = (time - floor(time)) * 24 + lon / 360 * 24;
LT(LT >= 24) = LT(LT > 24) - 24;
LT(LT < 0) = LT(LT > 24) + 24;

doy = day(datetime(time, 'ConvertFrom', 'datenum'), 'dayofyear'); 

%%

LTfac = sin((LT ./ 24) .* 2 .* pi); 
monthfac = cos((doy / 365) .* 2 .* pi);
Peak = 91 + LTfac + monthfac;
FWHM = 7.5 + 2.25 * monthfac;
