%% calc_full_wind.m
% returns a u+v lst/lat/lon distribution of model winds at specified alt and month

%% Set inputs
in_fn_sd = '~/data/ctmt/ctmt_semidiurnal_2002_2008.nc';
in_fn_d = '~/data/ctmt/ctmt_diurnal_2002_2008.nc';
hours = 0:23;
month = 9;
lats = -90:5:90;
lons = 0:15:360;
alt = 100;

comps.d = {'w2', 'w1', 's0', 'e1', 'e2', 'e3'};
comps.sd = {'w4', 'w3', 'w2', 'w1', 's0', 'e1', 'e2', 'e3'};
dirns = {'u', 'v'};

%% Load
model_coeffs.d = load_nc(in_fn_d); 
model_coeffs.sd = load_nc(in_fn_sd);

% Load the winds in LST
wind_array_lst = zeros(length(dirns), length(hours), length(lats), length(lons));
for il = 1:length(hours)
    lst = hours(il);
    for idn = 1:length(dirns)
        dirn = dirns{idn};
        wind_component = calc_wind_component(...
            lats, lons, alt, month, model_coeffs, comps, lst, dirn);
        wind_array_lst(idn, il, :, :) = wind_component;
    end
end

%% Convert to UT
wind_array_ut = zeros(size(wind_array_lst));

for ilst = 1:length(hours)
    UTs = hours(ilst) - lons * 24 / 360;
    UTs(UTs < 0) = UTs(UTs < 0) + 24;
    for iut = 1:length(hours)
        ut = hours(iut);
        lonidx = ismember(UTs, ut);
        wind_array_ut(:, iut, :, lonidx) = wind_array_lst(:, ilst, :, lonidx);
    end
end
wind_array_ut(:, 25, :, :) = wind_array_ut(:, 1, :, :);

%% 
contourf(squeeze(wind_array_ut(1, 1, :, :)))

