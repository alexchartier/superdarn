function hPa = calc_msis_pressure(time, alt, lat, lon, sw)
%% %  calc_msis_pressure.m
% 
% alt = 90E3;
% lat = 50;
% lon = 15;
% sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
% 
% days = datenum(yr, 1:12, 15);
% hrs = 0:23;
% Times = (days + hrs')';
% pres = zeros(length(days), length(hrs));
% for l1 = 1:length(days)
%     for l2 = 1:length(hrs)
%         pres(l1, l2) = calc_msis_pressure(Times(l1, l2), alt, lat, lon);
%     end
% end
% contourf(days, hrs, pres')
% datetick

%% Input filename for indices


%% Calculate time
dt = datetime(time, 'ConvertFrom', 'datenum');
yr = year(dt);
doy = day(dt, 'dayofyear'); 
utcsec = seconds(timeofday(dt));

%% Load Ap and F107
warning('off', 'MATLAB:table:ModifiedAndSavedVarnames'); 
f107a = sw.F10_7_ADJ_CENTER81(sw.DATE == dateshift(dt, 'start', 'day'));
f107d = sw.F10_7_ADJ(sw.DATE == dateshift(dt, 'start', 'day'));
Apd = sw.AP_AVG(sw.DATE == dateshift(dt, 'start', 'day'));

%% Calculate pressure
[T, rho] = atmosnrlmsise00(alt, lat, lon, yr, doy, utcsec, f107a, f107d, Apd);
N_tot = sum(rho([1:5, 7:9]));
Kb = 1.380649E-23;
P = N_tot * Kb * T(2);
hPa = P ./ 100;



