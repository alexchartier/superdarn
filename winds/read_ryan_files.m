%% Read Ryan's files
% TODO: check the angle at equinox and other times

%%
fn = '~/Downloads/output_lat_0_lon_0.txt';
lat = 0;
lon = 0;

Names = {'NorthApex', 'SouthApex', 'Helion', 'AntiHelion', 'NorthToroidal', 'SouthToroidal'};
% Weights = [10, 10, 35, 35, 10, 10];
Weights = [10, 10, 35, 35, 5, 5];

%% Load data
txt = asciiread(fn);

vals = zeros(size(txt, 1)-1, 6);
times = zeros(size(txt, 1)-1, 1);
hdr = strsplit(txt(1, :), ',');
for l = 2:size(txt, 1)
    line = strsplit(txt(l, :), ',');
    times(l-1) = datenum8601(line{1}); 
    for i = 2:7
        vals(l-1, i-1) = str2double(line{i});
    end
end

weighted_mean = vals * Weights' / 100;

%% 
ti = floor(times) > times(1) & ceil(times) < times(end); % get rid of 1st and last day
days = unique(floor(times(ti)));
idx = 5;


% val2d = reshape(vals(ti, idx), [6*24, length(days)]);
val2d = reshape(weighted_mean, [6*24, length(days)]);

hrut = [0:10:1439] / 60;
hrlt = hrut + lon / 360 * 24;
contourf(days, hrlt, val2d); 
clim([-90, 90]);
c = colorbar;
c.Label.String = 'Elevation Angle (°)';
datetick
ylabel('Hour (UT)')
title(Names{idx})