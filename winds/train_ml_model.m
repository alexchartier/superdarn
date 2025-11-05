%% mwr_ct_corr.m
% Correlate the mwr counts against geophysical parameters
clear

%%
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
radar_dir = '~/data/meteor_winds/mat/';
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';
mem_fn = '~/data/meteor_winds/mem_3_output_v1.nc';
msis_fn_fmt = '~/data/meteor_winds/msis/msis_{yyyy}_%1.1fN_%1.1fE.mat';
ml_model_fn = '~/data/meteor_winds/ml_model.mat';
hrs = 0:23;
ref_alt = 90E3;

mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};


%% Load
% Solar params
sw = readtable(sw_fn_csv);
mem = load_mem(mem_fn);
angles = load_nc(meteor_angle_fn);

%% Generate model input
% MWR data
flist = dir(radar_dir);
flist = flist(3:end);
for i = 1:length(flist)
    mwr = loadstruct([flist(i).folder, '/', flist(i).name]);

    yr = year(min(mwr.Time(:)));
    months = unique(month(floor(mwr.Time(:))))';
    days = datenum(yr, months, 15);
    Times = days + (hrs/24)';

    % meteor observed params (monthly median)
    [~, Peak, FWHM] = gaussfit_mwr_cts(mwr, days, hrs);

    % Meteor model
    speed = meteor_speed_density_model(Times, mwr.lat, mwr.lon, angles);

    % MEM model interpolation
    mem_int = interp_mem(mem, mem_fields, Times, mwr.lat, mwr.lon);

    % DOY and LT
    DOY = floor(Times(:)) - datenum(yr, 1, 1) + 1;
    LT = ((Times(:) - floor(Times(:))) + mwr.lon/360) * 24;
    LT(LT < 0) = LT(LT < 0) + 24;
    LT(LT >= 24) = LT(LT >= 24) - 24;

    % Pressure
    pres = zeros(length(days), length(hrs))';
    for l1 = 1:length(hrs)
        for l2 = 1:length(days)
            pres(l1, l2) = calc_msis_pressure(Times(l1, l2), ...
                ref_alt, mwr.lat, mwr.lon, sw);
        end
    end

    %% Generate param table
    Tbl = table;
    Tbl.DOY = DOY(:);
    Tbl.LT = LT(:);
    if mwr.lat > 0
        Tbl.SinDOY = sin(DOY(:) / 365 * pi);
    else
        Tbl.SinDOY = sin(DOY(:) / 365 * pi + pi);
    end
    Tbl.SinLT = sin(LT(:) / 24 * pi);
    Tbl.Peak = Peak(:);
    Tbl.FWHM = FWHM(:);
    Tbl.lat = mwr.lat * ones(size(DOY(:)));
    Tbl.abs_lat = abs(mwr.lat) * ones(size(DOY(:)));
    Tbl.F107 = interp1(sw.DATE, sw.F10_7_ADJ_CENTER81, ...
        datetime(Times(:), 'ConvertFrom', 'datenum'));
    Tbl.speed = speed(:);
    Tbl.pressure = pres(:);
    Tbl.norm_pressure = normalize(pres(:));

    for fi = 1:length(mem_fields)
        Tbl.(mem_fields{fi}) = mem_int.(mem_fields{fi})(:);
    end

    if i == 1
        Tbl_full = Tbl;
    else
        Tbl_full = [Tbl_full; Tbl];
    end

end 

%% Training
Tbl_train_FWHM = removevars(Tbl_full, {'Peak', 'FWHM'});
Tbl_train_peak = Tbl_train_FWHM; %removevars(Tbl_train_FWHM, mem_fields);
Mdl.Peak = fitrsvm(Tbl_train_peak, Tbl_full.Peak);
Mdl.FWHM = fitrsvm(Tbl_train_FWHM, Tbl_full.FWHM);

savestruct(ml_model_fn, Mdl)
fprintf('Saved to %s\n', ml_model_fn)

% %% Testing
% close all
% flist = dir(radar_dir);
% flist = flist(3:end);
% for i = 1:length(flist)
%     fn = [flist(i).folder, '/', flist(i).name];
%     mwr = loadstruct(fn);
%
%     yr = year(min(mwr.Time(:)));
%     months = unique(month(floor(mwr.Time(:))))';
%     days = datenum(yr, months, 15);
%     Times = days + (hrs/24)';
%
%     % meteor observed params (monthly median)
%     [~, Peak, FWHM] = gaussfit_mwr_cts(mwr, days, hrs);
%
%     % Pressure
%     pres = zeros(length(days), length(hrs))';
%     for l1 = 1:length(hrs)
%         for l2 = 1:length(days)
%             pres(l1, l2) = calc_msis_pressure(Times(l1, l2), ref_alt, mwr.lat, mwr.lon);
%         end
%     end
%
%     tiledlayout(2, 1, "TileSpacing",'compact')
%     nexttile
%     contourf(FWHM)
%     title(fn)
%     colorbar
%
%     nexttile
%     contourf(pres)
%     colorbar
%
%
%     figure
% end