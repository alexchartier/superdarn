%% calc_full_wind.m
% returns a u+v lst/lat/lon distribution of model winds at specified alt and month

%% Set inputs
in_fn_sd = '~/data/ctmt/ctmt_semidiurnal_2002_2008.nc';
in_fn_d = '~/data/ctmt/ctmt_diurnal_2002_2008.nc';
coeff_fn = '~/data/ctmt/coeffs.mat';
hours = 0:24;
month = 9;
lats = -90:5:90;
lons = 0:15:360;
alt = 100;
lst = 0;

comps.d = {'w2', 'w1', 's0', 'e1', 'e2', 'e3'};
comps.sd = {'w4', 'w3', 'w2', 'w1', 's0', 'e1', 'e2', 'e3'};
dirns = {'u', 'v'};

%% Load
try
    model_coeffs = loadstruct(coeff_fn);
catch
    model_coeffs.d = load_nc(in_fn_d);
    model_coeffs.sd = load_nc(in_fn_sd);
    savestruct(coeff_fn, model_coeffs);
end

alts = model_coeffs.d.lev;
months = model_coeffs.d.month;
% wind_array_lst dimensions: [direction, LST, lon, lat, lev, month]

for idn = 1:length(dirns)
    dirn = dirns{idn};
    wind_component = calc_wind_comp_v2(hours, lons, model_coeffs, comps, dirn);

    if idn == 1
        wind_array_lst = zeros([2, size(wind_component)]);
    end 
    wc = reshape(wind_component, [1, size(wind_component)]); 
    wind_array_lst(idn, :, :, :, :, :) = wind_array_lst(idn, :, :, :, :, :) + wc;
end



%% Convert to UT
wind_array_ut = zeros(size(wind_array_lst));

for ilst = 1:length(hours)
    UTs = hours(ilst) - lons * 24 / 360;
    UTs(UTs < 0) = UTs(UTs < 0) + 24;
    for iut = 1:length(hours)
        ut = hours(iut);
        lonidx = ismember(UTs, ut);
        wind_array_ut(:, iut, lonidx, :, :, :) = wind_array_lst(:, ilst, lonidx, :, :, :);
    end
end
wind_array_ut(:, 25, :, :, :, :) = wind_array_ut(:, 1, :, :, :, :);

%%
% contourf(squeeze(wind_array_ut(1, 1, :, :, alts == 100, months==9))')
% colorbar

contourf(lons, lats, squeeze(wind_array_lst(1, hours==0, :, :, alts==100, months==9))')


















