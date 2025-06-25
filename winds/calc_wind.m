function wind = calc_wind(model_coeffs, lat, lon, alt, hour, month, component, ...
    direction, diurnal_semidiurnal)


[lon2, lat2] = meshgrid(lon, lat);
% check all requested lat within model_coeffs['lat']
% assert np.all(np.in1d(lat, model_coeffs['lat'])), "requested lat must be subset of model_coeffs['lat']"

%  Get the dimensional indexes
mi = model_coeffs.month == month;
li = ismember(model_coeffs.lat, lat);

%  amplitude (m/s) (east/west/north/up, depending on component)
amparr = model_coeffs.(sprintf('amp_%s_%s', component, direction))(li, :, mi);
amp = zeros(size(amparr, 1), 1);
for i = 1:length(amp)
    amp(i) = interp1(model_coeffs.lev, amparr(i, :), alt);
end

% phase (UT of MAX at 0 deg lon)
phasearr = model_coeffs.(sprintf('phase_%s_%s', component, direction))(li, :, mi);
phase = zeros(size(phasearr, 1), 1);
for i = 1:length(phase)
    phase(i) = interp1(model_coeffs.lev, phasearr(i, :), alt);
end

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
[~, amp2] = meshgrid(lon, amp);
[~, phase2] = meshgrid(lon, phase);
wind = amp2 .* cos(ds_multiplier .* pi ./ 12 .* hour - dirn_multiplier .* ...
    s * lon2 .* pi ./ 180 - phase2 .* ds_multiplier .* pi ./ 12);

