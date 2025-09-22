function N_int = calc_msis_density(time, alts, lat, lon)
%% %  calc_msis_density.m
% Column-integrated total number density 
% time = datenum(2022, 1, 1, 12, 0, 0);
% dt = datetime(time, 'ConvertFrom', 'datenum');
% alts = [90:600] * 1E3;
% lat = 60;
% lon = 15;
% 
% N_int = calc_msis_density(time, alts, lat, lon) % returns integrated density;
% 
% lats = -90:5:90;
% lons = 0:15:360;
% alts = 80:100;
% N_int = zeros(length(lats), length(lons));
% time = datenum(2022, 1, 1, 12, 0, 0);
% for i = 1:length(lats)
%     for j = 1:length(lons)
%         N_int(i, j) = calc_msis_density(time, alts, lats(i), lons(j));
%     end
% end
% contourf(lons, lats, N_int); title(datestr(time)); grid on; 
% y = colorbar;
% y.Label.String = 'Density between 80-100 km (kg/m2)';
% xlabel('Lon (°)'); ylabel('Lat (°)')


%% Input filename for indices
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/

%% Calculate time
dt = datetime(time, 'ConvertFrom', 'datenum');
yr = year(dt);
doy = day(dt, 'dayofyear'); 
utcsec = seconds(timeofday(dt));

lon(lon > 180) = lon(lon > 180) - 360;

%% Load Ap and F107
warning('off', 'MATLAB:table:ModifiedAndSavedVarnames'); 
sw = readtable(sw_fn_csv);
f107a = sw.F10_7_ADJ_CENTER81(sw.DATE == dateshift(dt, 'start', 'day'));
f107d = sw.F10_7_ADJ(sw.DATE == dateshift(dt, 'start', 'day'));
Apd = sw.AP_AVG(sw.DATE == dateshift(dt, 'start', 'day'));

%% Calculate total mass density
% rho: He, O, N2, O2, AR, total mass density kg/m3, H, N, O_a
[T, rho] = atmosnrlmsise00(alts, lat, lon, yr, doy, utcsec, f107a, f107d, Apd);
% N_tot = sum(rho(:, [1:5, 7:9]), 2);

N_int = trapz(alts * 1E3, rho(:, 6));

%%
