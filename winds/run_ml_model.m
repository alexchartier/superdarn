function [Peak, FWHM] = run_ml_model(Mdl, Times, lat, lon, mem_int, ...
    sw, meteor_angles, freq)
%% run_ml_model(times, mwr, sw_fn_csv)
% [Peak, FWHM] = run_ml_model(Mdl, Times, lat, lon, mem_int, sw, meteor_angles)
% Training or 'reference' frequency is 30 MHz

%% Set inputs
% hrs = 0:23;
ref_alt = 90E3; % for the pressure calculation
ref_freq = 30;


%% Load 
yr = year(min(Times(:)));
DOY = floor(Times(:)) - datenum(yr, 1, 1) + 1;


LT = ((Times(:) - floor(Times(:))) + lon/360) * 24;
yr = year(min(Times(:)));

% Meteor model
speed = meteor_speed_density_model(Times, lat, lon, meteor_angles);
pres = calc_msis_pressure(Times, ref_alt, lat, lon, sw);


Tbl = table; 

Tbl.DOY = DOY(:);
Tbl.LT = LT(:);
if lat > 0
    Tbl.SinDOY = sin(DOY(:)/365 * pi);
else
    Tbl.SinDOY = sin(DOY(:)/365 * pi + pi);
end
Tbl.SinLT = sin(LT(:) / 24 * pi);
Tbl.lat = lat * ones(size(DOY(:)));
Tbl.abs_lat = abs(lat) * ones(size(DOY(:)));

Tbl.F107 = interp1(sw.DATE, sw.F10_7_ADJ_CENTER81, ...
            datetime(Times(:), 'ConvertFrom', 'datenum'));

Tbl.speed = speed(:);
Tbl.pressure = pres(:);
Tbl.norm_pressure = normalize(pres(:));

fields = fieldnames(mem_int);
for fi = 1:length(fields)
    Tbl.(fields{fi}) = mem_int.(fields{fi})(:);
end

Peak_30 = Mdl.Peak.predict(Tbl);
FWHM = Mdl.FWHM.predict(Tbl);
freq_vec = freq(:);
if isscalar(freq_vec)
    freq_vec = repmat(freq_vec, size(Peak_30));
elseif numel(freq_vec) ~= numel(Peak_30)
    error('run_ml_model:FreqSizeMismatch', 'freq length (%d) must match predictions (%d) or be scalar.', numel(freq_vec), numel(Peak_30));
else
    freq_vec = reshape(freq_vec, size(Peak_30));
end
Peak = freq_vs_ht_model(freq_vec, Peak_30, ref_freq);

Peak = reshape(Peak, size(Times));
FWHM = reshape(FWHM, size(Times));
