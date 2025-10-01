function [Peak, FWHM] = run_ml_model(Mdl, mwr, sw_fn_csv, meteor_angle_fn, msis_fn_fmt)
%% run_ml_model(times, mwr, sw_fn_csv)
% [Peak, FWHM] = run_ml_model(times, mwr, sw_fn_csv)


%% Set inputs
hrs = 0:23;
ref_alt = 90E3;

%% Load 
% Solar params
sw = readtable(sw_fn_csv);

yr = year(min(mwr.Time(:)));
Times = repmat(datenum(yr, 1:12, 15), [24, 1]) + hrs'/24;
days = unique(floor(Times(:)));
DOY = floor(Times(:)) - datenum(yr, 1, 1) + 1;


LT = ((Times(:) - floor(Times(:))) + mwr.lon/360) * 24;
yr = year(min(Times(:)));

% Meteor model
[speed, msis] = meteor_speed_density_model(Times, mwr.lat, mwr.lon, ...
    meteor_angle_fn, msis_fn_fmt);
pres = zeros(length(days), length(hrs))';
for l1 = 1:length(hrs)
    for l2 = 1:length(days)
        pres(l1, l2) = calc_msis_pressure(Times(l1, l2), ref_alt, mwr.lat, mwr.lon);
    end
end


Tbl_pred = table; 

Tbl_pred.DOY = DOY(:);
Tbl_pred.LT = LT(:);
Tbl_pred.SinDOY = sin(DOY(:)/365 * pi);
Tbl_pred.SinLT = sin(LT(:) / 24 * pi);
Tbl_pred.abs_lat = 55 .* ones(size(LT(:)));

Tbl_pred.F107 = interp1(sw.DATE, sw.F10_7_ADJ_CENTER81, ...
            datetime(Times(:), 'ConvertFrom', 'datenum'));

Tbl_pred.speed = speed(:);
Tbl_pred.pressure = pres(:);
Peak = Mdl.Peak.predict(Tbl_pred);
FWHM = Mdl.FWHM.predict(Tbl_pred);

Peak = reshape(Peak, [length(hrs), length(days)]);
FWHM = reshape(FWHM, [length(hrs), length(days)]);

