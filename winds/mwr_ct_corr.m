%% mwr_ct_corr.m
% Correlate the mwr counts against geophysical parameters
clear
%%
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
mwr_radars = {'And', 'Jul'};
mwr_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
meteor_angle_fn = '~/data/meteor_winds/angles_v1.nc';
msis_fn_fmt = '~/data/meteor_winds/msis_{yyyy}_%1.1fN_%1.1fE.mat';
yrs = [2008, 2020];
hrs = 0:23;
ref_alt = 90E3;


%% Load
% Solar params
sw = readtable(sw_fn_csv);

% MWR data
for y = 1:length(yrs)
    yr = yrs(y);
    mwr_times = datenum(yr, 1, 1):datenum(yr, 12, 31);
    days = datenum(yr, 1:12, 15); % output months

    for i = 1:length(mwr_radars)
        mwr_fn = [filename(mwr_fn_fmt{1}, min(mwr_times), mwr_radars{i}), ...
            filename(mwr_fn_fmt{2}, max(mwr_times), mwr_radars{i})];
        mwr = load_mwr(mwr_fn, 0);

        % meteor observed params (monthly median)
        [~, Peak, FWHM] = gaussfit_mwr_cts(mwr_fn, days, hrs);

        % Meteor model
        [speed, msis] = meteor_speed_density_model(yr, mwr.lat, mwr.lon, ...
            meteor_angle_fn, msis_fn_fmt);

        % DOY and LT
        Times = days + (hrs/24)';
        DOY = floor(Times(:)) - min(floor(Times(:))) + 1;
        LT = ((Times(:) - floor(Times(:))) + mwr.lon/360) * 24;
        LT(LT < 0) = LT(LT < 0) + 24;
        LT(LT >= 24) = LT(LT >= 24) - 24;

        % Pressure
        pres = zeros(length(days), length(hrs))';
        for l1 = 1:length(hrs)
            for l2 = 1:length(days)
                pres(l1, l2) = calc_msis_pressure(Times(l1, l2), ref_alt, mwr.lat, mwr.lon);
            end
        end


        %% Generate param table
        % Params:
        % abs_lat, LT, F10.7_ADJ, speed, msis, spread, DOY, solar_zenith_angle
        %

        % Create the table:
        Tbl = table;
        Tbl.DOY = DOY(:);        
        Tbl.LT = LT(:);
        Tbl.SinDOY = sin(DOY(:) / 365 * pi);
        Tbl.SinLT = sin(LT(:) / 24 * pi);
        Tbl.Peak = Peak(:);
        Tbl.FWHM = FWHM(:);
        
        Tbl.abs_lat = abs(mwr.lat) * ones(size(DOY(:)));
        Tbl.F107 = interp1(sw.DATE, sw.F10_7_ADJ_CENTER81, ...
            datetime(Times(:), 'ConvertFrom', 'datenum'));
        Tbl.speed = speed(:);
        % Tbl.density = msis(:);
        Tbl.pressure = pres(:);

        if i == 1 && y == 1
            Tbl_full = Tbl;
        else
            Tbl_full = [Tbl_full; Tbl];
        end

    end %loop over radars
end % loop over years

%% Training
% Training: Mdl_peak = fitrsvm(Tbl,'Peak'), Mdl_FWHM = fitrsvm(Tbl, 'FWHM')
Tbl_peak = removevars(Tbl_full, 'FWHM');
Tbl_FWHM = removevars(Tbl_full, 'Peak');
Mdl_peak = fitrsvm(Tbl_peak,'Peak');
Mdl_FWHM = fitrsvm(Tbl_FWHM, 'FWHM');


%% Testing 
% TODO: generate a table matching the model input
yr = 2020;
days = datenum(yr, 1:12, 15); % output months
hrs = 0:23;
mwr_fn = '~/data/meteor_winds/SMR_Jul_Jul_32_20200101_20201231.h5';
mwr = load_mwr(mwr_fn, 0);
[~, Peak, FWHM] = gaussfit_mwr_cts(mwr_fn, days, hrs);

[speed, msis] = meteor_speed_density_model(yr, mwr.lat, mwr.lon, ...
    meteor_angle_fn, msis_fn_fmt);
pres = zeros(length(days), length(hrs))';
for l1 = 1:length(hrs)
    for l2 = 1:length(days)
        pres(l1, l2) = calc_msis_pressure(Times(l1, l2), ref_alt, mwr.lat, mwr.lon);
    end
end

Times = days + (hrs/24)';
DOY = floor(Times(:)) - min(floor(Times(:))) + 1;
LT = ((Times(:) - floor(Times(:))) + mwr.lon/360) * 24;

Tbl_pred = table; 

Tbl_pred.DOY = DOY(:);
Tbl_pred.LT = LT(:);
Tbl_pred.SinDOY = sin(DOY(:)/365 * pi);
Tbl_pred.SinLT = sin(LT(:) / 24 * pi);
Tbl_pred.abs_lat = 55 .* ones(size(LT(:)));

Tbl_pred.F107 = interp1(sw.DATE, sw.F10_7_ADJ_CENTER81, ...
            datetime(Times(:), 'ConvertFrom', 'datenum'));

Tbl_pred.speed = speed(:);
% Tbl_pred.density = msis(:);
Tbl_pred.pressure = pres(:);
Mod.Peak = Mdl_peak.predict(Tbl_pred);
Mod.FWHM = Mdl_FWHM.predict(Tbl_pred);

Mod.Peak = reshape(Mod.Peak, [length(hrs), length(days)]);
Mod.FWHM = reshape(Mod.FWHM, [length(hrs), length(days)]);

%%
clf
subplot(3, 1, 1)
contourf(Mod.Peak)
clim([88, 92])
colorbar
subplot(3, 1, 2)
contourf(Peak)
clim([88, 92])
colorbar
subplot(3, 1, 3)
contourf(Mod.Peak- Peak)
colorbar