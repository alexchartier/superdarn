function speed = meteor_speed_density_model(times, lat, lon, angles)

%% Inputs


Names = {...
    'north_apex_el', 'south_apex_el', ...
    'helion_el', 'anti_helion_el', ...
    'north_toroidal_el', 'south_toroidal_el'};
Names2 = {'north_apex', 'south_apex', 'helion', 'antihelion',...
    'north_toroidal', 'south_toroidal'};

% JFC=30, HTC=55. Note Nesvorny (2010) has JFC around 15, but there's a
% double peak in the distribution and the <30 km/s are not radar-observable
Geocentric_Speeds = [55, 55, 30, 30, 55, 55];
lon(lon < 0) = lon(lon < 0) + 360;

%% load
% Note angles are the same every year
dv0 = datevec(min(times(:)));
yr = dv0(1);
flds = fieldnames(angles);
if ~leapyear(yr)
    lyi = angles.month == 2 & angles.day == 29;
    for i =1:length(flds)
        if contains(flds{i}, 'az') || contains(flds{i}, 'el')
            angles.(flds{i}) = angles.(flds{i})(:, :, ~lyi);
        elseif strcmp(flds{i}, 'lat') || strcmp(flds{i}, 'lon') 
            continue
        else
            angles.(flds{i}) = angles.(flds{i})(~lyi);
        end

    end
end

yr_vec = double((yr - min(angles.year(:))) + angles.year);
angles.times = datenum(yr_vec, double(angles.month),...
    double(angles.day), double(angles.hour), double(angles.minute), 0);

sources = sporadic_source_model(); 

%% Time calculations
% times = repmat(datenum(year, 1:12, 15), [24, 1]) + [0:23]'/24;
LTs = (times - floor(times) + lon / 360) * 24;
LTs(LTs >= 24) = LTs(LTs >= 24) - 24;
LTs(LTs < 0) = LTs(LTs < 0) + 24;

%% Speeds
ti_idx = interp1(angles.times(:), 1:numel(angles.times), times(:), 'nearest', 'extrap');
if any(~isfinite(ti_idx))
    error('meteor_speed_density_model:TimeIndex', 'Could not map one or more input times to the meteor-angle grid.');
end
ti_idx = reshape(round(ti_idx), size(times));
for i = 1:length(Names)
    speeds.(Names{i}) = sind(angles.(Names{i})) .* Geocentric_Speeds(i);

    % Interpolate to station
    speeds_s.(Names{i}) = zeros(size(times));
    angles_s.(Names{i}) = zeros(size(times));
    for k = 1:numel(times)
        tIdx = ti_idx(k);
        speeds_s.(Names{i})(k) = interp2(...
            angles.lat, angles.lon, speeds.(Names{i})(:, :, tIdx), ...
            lat, lon);
        angles_s.(Names{i})(k) = interp2(...
            angles.lat, angles.lon, angles.(Names{i})(:, :, tIdx), ...
            lat, lon);
    end
    speeds_s.(Names{i}) = reshape(speeds_s.(Names{i}), size(times));
    angles_s.(Names{i}) = reshape(angles_s.(Names{i}), size(times));
end


%% Calculate weighted mean
vals = zeros([6, numel(speeds_s.north_apex_el(:))]); 

for i = 1:length(Names)
    a1 = speeds_s.(Names{i});
    vals(i, :) = a1(:);
end

doy = floor(times) - datenum(yr, 1, 0);

weights_2d = zeros(size(vals));
for i = 1:length(Names)
    dailyavg_weights = sources.(Names2{i})(doy);
    elv_weight = sind(angles_s.(Names{i}));

    weights_i = dailyavg_weights .* elv_weight;
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

spread = reshape(spread, size(times));
