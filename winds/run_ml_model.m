function [Peak, FWHM] = run_ml_model(Mdl, mwr, mem_int, sw, meteor_angles)
%% run_ml_model(times, mwr, sw_fn_csv)
% [Peak, FWHM] = run_ml_model(times, mwr, sw_fn_csv)


%% Set inputs
% hrs = 0:23;
ref_alt = 90E3;

%% Load 

yr = year(min(mwr.Time(:)));
% Times = repmat(datenum(yr, 1:12, 15), [24, 1]) + hrs'/24;
Times = mwr.Time;
hrs = (mwr.Time(:, 1) - min(mwr.Time(:, 1))) * 24;

days = unique(floor(Times(:)));
DOY = floor(Times(:)) - datenum(yr, 1, 1) + 1;


LT = ((Times(:) - floor(Times(:))) + mwr.lon/360) * 24;
yr = year(min(Times(:)));

% Meteor model
speed = meteor_speed_density_model(Times, mwr.lat, mwr.lon, meteor_angles);
pres = zeros(length(days), length(hrs))';
for l1 = 1:length(hrs)
    for l2 = 1:length(days)
        pres(l1, l2) = calc_msis_pressure(...
            Times(l1, l2), ref_alt, mwr.lat, mwr.lon, sw);
    end
end


Tbl = table; 

Tbl.DOY = DOY(:);
Tbl.LT = LT(:);
if mwr.lat > 0
    Tbl.SinDOY = sin(DOY(:)/365 * pi);
else
    Tbl.SinDOY = sin(DOY(:)/365 * pi + pi);
end
Tbl.SinLT = sin(LT(:) / 24 * pi);
Tbl.lat = mwr.lat * ones(size(DOY(:)));
Tbl.abs_lat = abs(mwr.lat) * ones(size(DOY(:)));

Tbl.F107 = interp1(sw.DATE, sw.F10_7_ADJ_CENTER81, ...
            datetime(Times(:), 'ConvertFrom', 'datenum'));

Tbl.speed = speed(:);
Tbl.pressure = pres(:);
Tbl.norm_pressure = normalize(pres(:));

Peak = Mdl.Peak.predict(Tbl);

% better not to use the MEM stuff in the peak model, but it helps with FWHM
% model
fields = fieldnames(mem_int);
for fi = 1:length(fields)
    Tbl.(fields{fi}) = mem_int.(fields{fi})(:);
end


FWHM = Mdl.FWHM.predict(Tbl);


Peak = reshape(Peak, [length(hrs), length(days)]);
FWHM = reshape(FWHM, [length(hrs), length(days)]);

