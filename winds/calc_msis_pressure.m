function hPa = calc_msis_pressure(time, alt, lat, lon)
%% %  calc_msis_pressure.m
% 
% time = datenum(2022, 1, 1, 12, 0, 0);
% dt = datetime(time, 'ConvertFrom', 'datenum');
% alt = 90E3;
% lat = 60;
% lon = 15;
% 
% hPa = calc_msis_pressure(time, alt, lat, lon) % returns pressure in hectopascals;

%% Input filename for indices
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/

%% Calculate time
dt = datetime(time, 'ConvertFrom', 'datenum');
yr = year(dt);
doy = day(dt, 'dayofyear'); 
utcsec = seconds(timeofday(dt));

%% Load Ap and F107
warning('off', 'MATLAB:table:ModifiedAndSavedVarnames'); 
sw = readtable(sw_fn_csv);
f107a = sw.F10_7_ADJ_CENTER81(sw.DATE == dateshift(dt, 'start', 'day'));
f107d = sw.F10_7_ADJ(sw.DATE == dateshift(dt, 'start', 'day'));
Apd = sw.AP_AVG(sw.DATE == dateshift(dt, 'start', 'day'));

%% Calculate pressure
[T, rho] = atmosnrlmsise00(alt, lat, lon, yr, doy, utcsec, f107a, f107d, Apd);
N_tot = sum(rho([1:5, 7:9]));
Kb = 1.380649E-23;
P = N_tot * Kb * T(2);
hPa = P ./ 100;



