function wind = calc_wind_comp_v2(hours, lons, model_coeffs, comps, dirn)

%% Calculate the wind


ds_list = fieldnames(comps);
ct = 0;
for ids = 1:length(ds_list)
    ds = ds_list{ids};
    comp_list = comps.(ds);
    for icomp = 1:length(comp_list)
        comp = comp_list{icomp};
        wind_comp = calc_wind_v2(model_coeffs.(ds), ...
            lons, hours, comp, dirn, ds);
        
        if ct == 0
            wind = wind_comp;
            ct = ct + 1;
        else
            wind = wind + wind_comp;
        end
    end
end
end

%%
function wind = calc_wind_v2(model_coeffs, lons, lsts, component, ...
    direction, diurnal_semidiurnal)

lats = model_coeffs.lat;
alts = model_coeffs.lev;
months = model_coeffs.month;

[alt3, lat3, month3] = meshgrid(alts, lats, months);


%  amplitude (m/s) (east/west/north/up, depending on component)
amp = model_coeffs.(sprintf('amp_%s_%s', component, direction));

% phase (UT of MAX at 0 deg lon)
phase = model_coeffs.(sprintf('phase_%s_%s', component, direction));
 
% propagation direction multiplier used to determine phase at specified longitude
if component(1) == 'e'  % eastward
    dirn_multiplier = 1;
elseif component(1) == 'w'  % westward
    dirn_multiplier = -1;
elseif component(1) == 's'  % stationary
    dirn_multiplier = 0;
end

% diurnal/semidiurnal multiplier
if diurnal_semidiurnal == 'd'
    ds_multiplier = 1;
elseif strcmp(diurnal_semidiurnal, 'sd')
    ds_multiplier = 2;
end

% wavenumber
s = str2double(component(2));
assert(abs(s) < 5, 'wavenumbers <= 4 supported');

% Wind values at the requested locations
wind = zeros(length(lsts), length(lons), length(lats), length(alts), length(months));

for ih = 1:length(lsts)
    hours = lsts(ih) - lons / 360 * 24;
    for il = 1:length(lons)
        wind(ih, il, :, :, :) = amp .* cos(...
            ds_multiplier .* hours(il) ./ 12 .* pi ...
            - dirn_multiplier .* s * lons(il) ./ 180 .* pi ...
            - phase .* ds_multiplier ./ 12 .* pi);
    end
end

end