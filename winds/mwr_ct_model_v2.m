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
Names2 = {'north_apex', 'south_apex', 'helion', 'antihelion', 'north_toroidal', 'south_toroidal'};

LTmax = [270, 270, 350, 190, 270, 270] ./ 360 .* 24 - 12; % Based on Lambda values

% Weights = [10, 10, 35, 35, 10, 10];
alts = 80:100;
lat = 69.3;
lon = 16;

% lat = 54.6;
% lon = 13.4;


% JFC=30, HTC=55. Note Nesvorny (2010) has JFC around 15, but there's a
% double peak in the distribution and the <30 km/s are not radar-observable
Geocentric_Speeds = [55, 55, 30, 30, 55, 55];

%% load
angles = load_nc(meteor_angle_fn);
% Note angles are the same every year
angles.times = datenum(year, double(angles.month),...
    double(angles.day), double(angles.hour), double(angles.minute), 0);
sources = sporadic_source_model(); 

%% Time calculations
times = repmat(datenum(year, 1:12, 15), [24, 1]) + [0:23]'/24;
LTs = (times - floor(times) + lon / 360) * 24;
LTs(LTs >= 24) = LTs(LTs >= 24) - 24;
LTs(LTs < 0) = LTs(LTs < 0) + 24;


%% Speeds
for i = 1:length(Names)
    speeds.(Names{i}) = sind(angles.(Names{i})) .* Geocentric_Speeds(i);

    % Interpolate to station
    for t1 = 1:size(times, 1)
        for t2 = 1:size(times, 2)
            ti = angles.times == times(t1, t2);
            speeds_s.(Names{i})(t1, t2) = interp2(...
                angles.lat, angles.lon, squeeze(speeds.(Names{i})(:, :, ti)), ...
                lat, lon);          
            angles_s.(Names{i})(t1, t2) = interp2(...
                angles.lat, angles.lon, squeeze(angles.(Names{i})(:, :, ti)), ...
                lat, lon);          
        end
    end
end

%% MSIS height-integrated density above X km at the station
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
    savestruct(msis_fn, msis)
end


%% Calculate weighted mean
vals = zeros([6, numel(speeds_s.apex(:))]); 

for i = 1:length(Names)
    a1 = speeds_s.(Names{i});
    vals(i, :) = a1(:);
end

% weights_2d = repmat(Weights', [1, numel(speeds_s.apex(:))]);
source_times = datenum(year, 1, 1:366);
ti = ismember(source_times, floor(times));

weights_2d = zeros(size(vals));
for i = 1:length(Names)
    dailyavg_weights = sources.(Names2{i})(ti);
    LT_weight = cosd((LTs - LTmax(i))/24 * 360);
    weights_i = repmat(dailyavg_weights', [24, 1]) .* LT_weight;
    weights_2d(i, :) = weights_i(:);
    % weights_2d(i, :) = weights_2d(i, :) .* LT_weight(:)';% angle_weight(:)';
    
end

weights_2d(vals <= 0) = 0;  % zero out the below-horizon meteors
weights_2d(weights_2d < 0) = 0;  % zero out negative weights


speeds_s.weighted_mean = squeeze(permute(reshape(...
    sum(vals .* weights_2d, 1) ./ sum(weights_2d, 1), ...
    size(speeds_s.apex)), [3, 1, 2]));

% calculate spread
spread = zeros(size(weights_2d, 2), 1);
for i = 1:size(weights_2d, 2)
    spread(i) = std(vals(:, i), weights_2d(:, i));
end

spread = reshape(spread, [24, 12]);

%% estimate peak height and FWHM
pht_norm = reshape(normalize(msis(:))/10 + normalize(speeds_s.weighted_mean(:)), ...
    size(msis))  + 91;
pht_norm(isnan(pht_norm)) = 90;

FWHM = reshape(normalize(msis(:)) + 0.1 * normalize(speeds_s.weighted_mean(:)), ...
    size(msis)) * 2 + 8;



%% Plot model output
close
tiledlayout(2, 1, 'TileSpacing', 'tight');

nexttile
[c, h] = contourf(pht_norm);
clabel(c, h)
% xlabel('Month')
ylabel('Time (UT)')
set(gca, 'XTickLabels', '')
clim([85, 95])
hc = colorbar;
ylabel(hc, 'Peak height (km)')
title('Peak height model')

nexttile
[c, h] = contourf(FWHM);
clabel(c, h)
xlabel('Month')
ylabel('Time (UT)')
clim([4, 12])
hc = colorbar;
ylabel(hc, 'Full Width @ Half Max (km)')





%% plot calculated parameters
tiledlayout(4, 1, 'TileSpacing', 'tight');
speeds_s.weighted_mean(isnan(speeds_s.weighted_mean)) = 0;

nexttile
[c, h] = contourf(speeds_s.weighted_mean);
clabel(c, h)
% xlabel('Month')
set(gca, 'XTickLabels', '')
ylabel('Time (UT)')
clim([0, 50])
hc = colorbar;
ylabel(hc, 'Speed (km/s)')
title('Mean effective speed')

nexttile
spread(isnan(spread)) = 0;
[c, h] = contourf(spread);
clabel(c, h)
%xlabel('Month')
set(gca, 'XTickLabels', '')
ylabel('Time (UT)')
clim([0, 20])
hc = colorbar;
ylabel(hc, 'Speed (km/s)')
title('Spread of speeds')

nexttile
[c, h] = contourf(msis);
clabel(c, h)
xlabel('Month')
ylabel('Time (UT)')
hc = colorbar;
ylabel(hc, 'Density (kg/m^{2})')
title('MSIS density between 80-100 km')

%%
% LT = (time - floor(time)) * 24 + lon / 360 * 24;
% LT(LT >= 24) = LT(LT > 24) - 24;
% LT(LT < 0) = LT(LT > 24) + 24;
% 
% doy = day(datetime(time, 'ConvertFrom', 'datenum'), 'dayofyear');

%%

