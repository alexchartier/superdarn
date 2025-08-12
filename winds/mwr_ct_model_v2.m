% function [Peak, FWHM] = mwr_ct_model_v2(time, lat, lon);
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

%% Inputs
% time = datenum(2022, 8, 1);
% lats = -90:10:90;
% lons = 0:10:360;

meteor_angle_fn = '~/data/meteor_winds/angles.nc';
msis_fn_fmt = '~/data/meteor_winds/msis_{yyyy}_%1.1fN_%1.1fE.mat';
year = 2008;
Names = {'apex', 'anti_apex', 'helion', 'anti_helion', 'north_toroidal', 'south_toroidal'};
Weights = [10, 10, 35, 35, 10, 10];
alts = 80:600;
lat = 69.3; 
lon = 16;

% JFC=30, HTC=55. Note Nesvorny (2010) has JFC around 15, but there's a
% double peak in the distribution and the <30 km/s are not radar-observable
Geocentric_Speeds = [55, 55, 30, 30, 55, 55];

%% load 
angles = load_nc(meteor_angle_fn);
% Note angles are the same every year
angles.times = datenum(year, double(angles.month),...
    double(angles.day), double(angles.hour), double(angles.minute), 0); 

times = repmat(datenum(year, 1:12, 15), [24, 1]) + [0:23]'/24;


%% Speeds 
for i = 1:length(Names)
    speeds.(Names{i}) = sind(angles.(Names{i})) .* Geocentric_Speeds(i);
end

%% MSIS height-integrated density above X km
msis_fn = filename(sprintf(msis_fn_fmt, lat, lon), times(1));
try
    msis = loadstruct(msis_fn);
catch
    fprintf('MSIS file not found: %s\nLoading...\n', msis_fn)
    msis = zeros(size(times));
    for t1 = 1:size(times, 1)
        for t2 = 1:size(times, 2)
            disp(datestr(times(t1, t2)));
            msis(t1, t2) = calc_msis_density(times(t1, t2), alts, lat, lon);
        end
    end
end

%% Interpolate to Andenes, see what's happening



%% 
LT = (time - floor(time)) * 24 + lon / 360 * 24;
LT(LT >= 24) = LT(LT > 24) - 24;
LT(LT < 0) = LT(LT > 24) + 24;

doy = day(datetime(time, 'ConvertFrom', 'datenum'), 'dayofyear'); 

%%

