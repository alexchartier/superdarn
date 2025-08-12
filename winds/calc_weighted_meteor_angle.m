%% calc_weighted_meteor_angle.m
% Calculate the weighted mean and standard deviation of the meteor source 
% elevation angle

%% Set inputs
in_fn = '~/data/meteor_winds/angles.nc';

lat = -68; 
lon = 0;
times = repmat(datenum(2007, 1:12, 15), [24, 1]) + [0:23]'/24;

% Names = {'NorthApex', 'SouthApex', 'Helion', 'AntiHelion', 'NorthToroidal', 'SouthToroidal'};
Names = {'apex', 'anti_apex', 'helion', 'anti_helion', 'north_toroidal', 'south_toroidal'};
Weights = [10, 10, 35, 35, 10, 10];

%% Load
angles = load_nc(in_fn);
angles.times = datenum(double(angles.year), double(angles.month),...
    double(angles.day), double(angles.hour), double(angles.minute), 0);

lon(lon < 0) = lon(lon < 0) + 360;

%% Create weighted average
vals = zeros([6, numel(angles.apex(:))]); 

for i = 1:length(Names)
    a1 = angles.(Names{i});
    vals(i, :) = a1(:);
end

weights_2d = repmat(Weights', [1, numel(angles.apex(:))]);

weights_2d(vals <= 0) = 0;  % zero out the below-horizon meteors

weighted_mean = permute(reshape(...
    sum(vals .* weights_2d, 1) ./ sum(weights_2d, 1), ...
    size(angles.apex)), [3, 1, 2]);

%% Interpolate
out.elev = zeros(size(times));
out.spread = zeros(size(times));
out.speed = zeros(size(times));
for h = 1:size(times, 1)
    for d = 1:size(times, 2)
        ti = angles.times == times(h, d);
        out.elev(h, d) = interp2(...
            angles.lat, angles.lon, squeeze(weighted_mean(ti, :, :)), ...
            lat, lon);
    end
end

%%
[C, h] = contourf(times(1, :), [0:23] + (lon /360 * 24), out.elev);
clabel(C, h)
clim([0, 40]);
c = colorbar;
c.Label.String = 'Elevation Angle (°)';
datetick
ylabel('LT')
% title('Average over POSITIVE elevations at ASI')