function [speed, msis] = ...
    meteor_speed_density_model(year, lat, lon, meteor_angle_fn, msis_fn_fmt)
%
% year = 2008;
% lat = 69.3;
% lon = 0;
% weights = [0.2, 1.2, 2, 0.2, 91, 8];
% meteor_angle_fn = '~/data/meteor_winds/angles_v1.nc';
% msis_fn_fmt = '~/data/meteor_winds/msis_{yyyy}_%1.1fN_%1.1fE.mat';
% 
% [Peak, FWHM, speed, msis] = meteor_speed_density_model(year, lat, lon, weights, ...
%   meteor_angle_fn, msis_fn_fmt);
%
%
%
% close
% tiledlayout(2, 1, 'TileSpacing', 'tight');
% 
% nexttile
% [c, h] = contourf(speed);
% clabel(c, h)
% % xlabel('Month')
% ylabel('Time (LT)')
% set(gca, 'XTickLabels', '')
% % clim([85, 95])
% hc = colorbar;
% ylabel(hc, 'Weighted mean eff. spd. (km/s)')
% colormap(gca, 'cool')
%
% 
% nexttile
% [c, h] = contourf(msis);
% clabel(c, h)
% xlabel('Month')
% ylabel('Time (LT)')
% % clim([4, 12])
% hc = colorbar;
% ylabel(hc, '80-100 integrated MSIS density (kg/m^{2})')
% colormap(gca, 'Copper')


%% Inputs


Names = {...
    'north_apex_el', 'south_apex_el', ...
    'helion_el', 'anti_helion_el', ...
    'north_toroidal_el', 'south_toroidal_el'};
Names2 = {'north_apex', 'south_apex', 'helion', 'antihelion',...
    'north_toroidal', 'south_toroidal'};


% Weights = [10, 10, 35, 35, 10, 10];
alts = 80:100;


% JFC=30, HTC=55. Note Nesvorny (2010) has JFC around 15, but there's a
% double peak in the distribution and the <30 km/s are not radar-observable
Geocentric_Speeds = [55, 55, 30, 30, 55, 55];
lon(lon < 0) = lon(lon < 0) + 360;

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
vals = zeros([6, numel(speeds_s.north_apex_el(:))]); 

for i = 1:length(Names)
    a1 = speeds_s.(Names{i});
    vals(i, :) = a1(:);
end

source_times = datenum(year, 1, 1:366);
ti = ismember(source_times, floor(times));

weights_2d = zeros(size(vals));
for i = 1:length(Names)
    dailyavg_weights = sources.(Names2{i})(ti);
    elv_weight = sind(angles_s.(Names{i})); 

    weights_i = repmat(dailyavg_weights', [24, 1]) .* elv_weight;
    weights_2d(i, :) = weights_i(:);
    % weights_2d(i, :) = weights_2d(i, :) .* LT_weight(:)';% angle_weight(:)'; 
end

weights_2d(vals <= 0) = 0;  % zero out the below-horizon meteors
weights_2d(weights_2d < 0) = 0;  % zero out negative weights

speeds_s.weighted_mean = squeeze(permute(reshape(...
    sum(vals .* weights_2d, 1) ./ sum(weights_2d, 1), ...
    size(speeds_s.north_apex_el)), [3, 1, 2]));

speed = speeds_s.weighted_mean;

%% calculate spread
spread = zeros(size(weights_2d, 2), 1);
for i = 1:size(weights_2d, 2)
    spread(i) = std(vals(:, i), weights_2d(:, i));
end

spread = reshape(spread, [24, 12]);

