function hPa = calc_msis_pressure(time, alt, lat, lon, sw)
%% %  calc_msis_pressure.m
% 
% alt = 90E3;
% lat = 50;
% lon = 15;
% sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
% 
% sw  = readtable(sw_fn_csv
% days = datenum(yr, 1:12, 15);
% hrs = 0:23;
% Times = (days + hrs')';
% pres = zeros(length(days), length(hrs));
% for l1 = 1:length(days)
%     for l2 = 1:length(hrs)
%         pres(l1, l2) = calc_msis_pressure(Times(l1, l2), alt, lat, lon, sw);
%     end
% end
% contourf(days, hrs, pres')
% datetick

%% Input filename for indices


%% Calculate time
dt = datetime(time, 'ConvertFrom', 'datenum');
dt_flat = dt(:);
yr = year(dt_flat);
doy = day(dt_flat, 'dayofyear'); 
utcsec = seconds(timeofday(dt_flat));
day_start = dateshift(dt_flat, 'start', 'day');

%% Load Ap and F107
warning('off', 'MATLAB:table:ModifiedAndSavedVarnames'); 
f107a = interp1(sw.DATE, sw.F10_7_ADJ_CENTER81, day_start);
f107d = interp1(sw.DATE, sw.F10_7_ADJ, day_start);
Apd = interp1(sw.DATE, sw.AP_AVG, day_start);

%% Calculate pressure
[T, rho] = atmosnrlmsise00(repmat(alt, numel(dt_flat), 1), ...
    repmat(lat, numel(dt_flat), 1), repmat(lon, numel(dt_flat), 1), ...
    yr, doy, utcsec, f107a, f107d, Apd);
N_tot = sum(rho(:, [1:5, 7:9]), 2);
Kb = 1.380649E-23;
P = N_tot .* Kb .* T(:, 2);
hPa = reshape(P ./ 100, size(time));


