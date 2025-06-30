%% calc_ctmt_wind.m
% Calculate CTMT winds

%% Set inputs
in_fn_sd = '~/data/ctmt/ctmt_semidiurnal_2002_2008.nc';
in_fn_d = '~/data/ctmt/ctmt_diurnal_2002_2008.nc';
out_fn = '~/data/ctmt/ctmt.mat';
coeff_fn = '~/data/ctmt/coeffs.mat';
hours = 0:23;
lons = 0:15:360;

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

for idn = 1:length(dirns)
    dirn = dirns{idn};
    wind_component = calc_wind_comp(hours, lons, model_coeffs, comps, dirn);

    if idn == 1
        % wind_array_lst dimensions: [direction, LST, lon, lat, lev, month]
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
hr_ut = [hours, hours(1) + 24];

%% Save
ctmt.wind = permute(wind_array_ut, [1, 6, 2, 5, 4, 3]);
ctmt.dirns = dirns; 
ctmt.months = double(months);
ctmt.hours = double(hr_ut);
ctmt.alts = alts; 
ctmt.lats = lats; 
ctmt.lons = lons; 
savestruct(out_fn, ctmt)

%%
% contourf(lons, lats, squeeze(wind_array_ut(1, hi, :, :, alts == 100, months==9))')
% 
% for hi = 1:25
% contourf(lons, lats, squeeze(wind_array_ut(1, hi, :, :, alts == 100, months==9))')
% colorbar
% pause(0.5)
% end


% contourf(lons, lats, squeeze(wind_array_lst(1, hours==0, :, :, alts==100, months==9))')
































