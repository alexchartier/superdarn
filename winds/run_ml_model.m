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
hrs = (Times(:, 1) - min(Times(:, 1))) * 24;
days = unique(floor(Times(:)));
DOY = floor(Times(:)) - datenum(yr, 1, 1) + 1;


LT = ((Times(:) - floor(Times(:))) + lon/360) * 24;
yr = year(min(Times(:)));

% Meteor model
speed = meteor_speed_density_model(Times, lat, lon, meteor_angles);
pres = zeros(length(days), length(hrs))';
for l1 = 1:length(hrs)
    for l2 = 1:length(days)
        pres(l1, l2) = calc_msis_pressure(...
            Times(l1, l2), ref_alt, lat, lon, sw);
    end
end


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
Peak = freq_vs_ht_model(freq, Peak_30, ref_freq);

Peak = reshape(Peak, [length(hrs), length(days)]);
FWHM = reshape(FWHM, [length(hrs), length(days)]);

