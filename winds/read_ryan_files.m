%% Read Ryan's files
% TODO: check the angle at equinox and other times

%%
fn = '~/Downloads/output_lat_0_lon_0.txt';
fn2 = '~/data/meteor_line_profs/ELINDEN_LUT__June_Latm60__all_q_organics__theta_40_Dec2024.mat';
lat = 0;
lon = 0;

Names = {'NorthApex', 'SouthApex', 'Helion', 'AntiHelion', 'NorthToroidal', 'SouthToroidal'};
% Weights = [10, 10, 35, 35, 10, 10];
Weights = [10, 10, 35, 35, 5, 5];

%% 
MLP = loadstruct(fn2);
%%
sza = [];
v = [];
mass = [];
Eletter = {};
Enum = [];
fn = {};
for i = 1:4800
    sza = [sza, str2double(MLP(i).fname(4:6))];
    v = [v, str2double(MLP(i).fname(8:10))];
    mass = [mass, str2double(MLP(i).fname(15))];
    Eletter = [Eletter; (MLP(i).fname(17:18))];
    fn = [fn; MLP(i).fname];
    % fprintf('%s\n', MLP(i).fname)
end

lenv = length(unique(v))
lenm = length(unique(mass))
lenE = length(unique(Eletter))
len = lenv* lenm * lenE
lentot = length(unique(fn))


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


weights_2d = repmat(Weights', [1, size(vals, 1)])';
weights_2d(vals <= 0) = 0;
weighted_mean = sum(vals .* weights_2d, 2) ./ sum(weights_2d, 2);

%% 
ti = floor(times) > times(1) & ceil(times) < times(end); % get rid of 1st and last day
days = unique(floor(times(ti)));
idx = 5;

% val2d = reshape(vals(ti, idx), [6*24, length(days)]);
val2d = reshape(weighted_mean(ti), [6*24, length(days)]);

hrut = [0:10:1439] / 60;
hrlt = hrut + lon / 360 * 24;
[C, h] = contourf(days, hrlt, val2d); 
clabel(C, h)
clim([-90, 90]);
c = colorbar;
c.Label.String = 'Elevation Angle (°)';
datetick
ylabel('Hour (LT)')
title('Weighted Elevation Angle for 0°N, 0°E, 2007')