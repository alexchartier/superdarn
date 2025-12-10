%% compare_raytracers.m
% It is difficult to get a match between simulated IRI/PHARLAP data and the
% Croft ionospheric optimization. One possibility is that differences in
% the two raytracers are responsible. To test that, drive PHARLAP with a
% "Croft" ionosphere.

%%  Calculate ionosphere

cd('~/superdarn');
nm = 1E12;
hm = 300;
ym = 100;
re = 6371;
[ne, alt] = calc_iono(nm, hm, ym, re);

range = 0:50:10000;

iono_en_grid = repmat(ne', [1, length(range)]) / 1E6;
iono_en_grid_5 = iono_en_grid;  % This is the next-time grid

% Raytrace parameters
elevs = [2:2:20];            % initial ray elevation
freq = 20.0;                 % ray frequency (MHz)

%% Croft raytrace it for comparison
[croft_gd, croft_gp, croft_ph] = ...
    raytrace_croft(freq, deg2rad(elevs), elec2freq(nm) / 1E6, hm, ym);

%% Pharlap stuff
cd('~/pharlap_4.2.0/src/matlab/examples/')
UT = [2008 7 1 7 0];        % UT - year, month, day, hour, minute
R12 = 100;                   % R12 index
speed_of_light = 2.99792458e8;

num_elevs = length(elevs);
freqs = freq.*ones(size(elevs));
ray_bear = 180.0;            % bearing of rays
origin_lat = -77.5;          % latitude of the start point of ray
origin_long = 166.4;         % longitude of the start point of ray
tol = [1e-7 .01 10];         % ODE tolerance and min/max step sizes
nhops = 2;                   % number of hops to raytrace
doppler_flag = 1;            % generate ionosphere 5 minutes later so that
% Doppler shift can be calculated
irregs_flag = 0;             % no irregularities - not interested in
% Doppler spread or field aligned irregularities
kp = 3;                      % kp not used as irregs_flag = 0. Set it to a
% dummy value

%% generate collision frequencies and irregularities

max_range = 10000;      % maximum range for sampling the ionosphere (km)
num_range = 201;        % number of ranges (must be < 2000)
range_inc = max_range ./ (num_range - 1);  % range cell size (km)

start_height = 0 ;      % start height for ionospheric grid (km)
height_inc = 3;         % height increment (km)
num_heights = length(alt);      % number of  heights (must be < 2000)

clear iri_options
iri_options.Ne_B0B1_model = 'Bil-2000'; % this is a non-standard setting for
% IRI but is used as an example
tic
fprintf('Generating ionospheric grid... ')
[~, ~, collision_freq, irreg] = ...
    gen_iono_grid_2d(origin_lat, origin_long, R12, UT, ray_bear, ...
    max_range, num_range, range_inc, start_height, ...
    height_inc, num_heights, kp, doppler_flag, 'iri2016', ...
    iri_options);

iono_pf_grid = sqrt(iono_en_grid * 80.6164e-6);
toc

% call raytrace for a fan of rays
% first call to raytrace so pass in the ionospheric and geomagnetic grids
fprintf('Generating %d 2D NRT rays ...', num_elevs);
tic
[ray_data, ray_path_data] = ...
    raytrace_2d(origin_lat, origin_long, elevs, ray_bear, freqs, nhops, ...
    tol, irregs_flag, iono_en_grid, iono_en_grid_5, ...
    collision_freq, start_height, height_inc, range_inc, irreg);
toc;

phar_gd = nan(size(ray_data));
phar_gp = nan(size(ray_data));
phar_ph = nan(size(ray_data));

for i = 1:length(ray_data)
    phar_gd(i) = ray_data(i).ground_range(1);
    phar_gp(i) = ray_data(i).group_range(1);
    phar_ph(i) = ray_data(i).phase_path(1);
end
    

%% TODO: Compare ray_data and the Croft output parameters
subplot(3, 1, 1)
hold on
plot(elevs, croft_gd, 'rx')
plot(elevs, phar_gd, 'bx')
hold off
xlabel('elevation angle')
ylabel('ground range')
legend({'Croft', 'Pharlap'})

subplot(3, 1, 2)
hold on
plot(elevs, croft_gp, 'rx')
plot(elevs, phar_gp, 'bx')
hold off
xlabel('elevation angle')
ylabel('group range')
legend({'Croft', 'Pharlap'})

subplot(3, 1, 3)
hold on
plot(elevs, croft_ph, 'rx')
plot(elevs, phar_ph, 'bx')
hold off
xlabel('elevation angle')
ylabel('phase path')
legend({'Croft', 'Pharlap'})




%% plot the rays and ionosphere
figure(1)
UT_str = [num2str(UT(3)) '/' num2str(UT(2)) '/' num2str(UT(1)) '  ' ...
    num2str(UT(4), '%2.2d') ':' num2str(UT(5), '%2.2d') 'UT'];
freq_str = [num2str(freq) 'MHz'];
R12_str = num2str(R12);
lat_str = num2str(origin_lat);
lon_str = num2str(origin_long);
bearing_str = num2str(ray_bear);
fig_str = [UT_str '   ' freq_str '   R12 = ' R12_str '   lat = ' lat_str ...
    ', lon = ' lon_str ', bearing = ' bearing_str];
set(gcf, 'name', fig_str)
title(fig_str)
start_range = 0;
end_range = 2000;
end_range_idx = fix((end_range-start_range) ./ range_inc) + 1;
start_ht = start_height;
start_ht_idx = 1;
end_ht = 300;
end_ht_idx = fix(end_ht ./ height_inc) + 1;
iono_pf_subgrid = iono_pf_grid(start_ht_idx:end_ht_idx, 1:end_range_idx);
plot_ray_iono_slice(iono_pf_subgrid, start_range, end_range, range_inc, ...
    start_ht, end_ht, height_inc, ray_path_data, 'color', [1, 1, 0.99], ...
    'linewidth', 2);

set(gcf,'units','normal')
pos = get(gcf,'position');
pos(2) = 0.55;
set(gcf,'position', pos)

% uncomment the following to print figure to hi-res ecapsulated postscript
% and PNG files
set(gcf, 'paperorientation', 'portrait')
set(gcf, 'paperunits', 'cent', 'paperposition', [0 0 61 18])
set(gcf, 'papertype', 'a4')
% print -depsc2 -loose -opengl test.ps
% print -dpng test.png













