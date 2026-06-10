%% compute_ml_feature_importance.m
% Compute permutation feature importance for the ML Peak/FWHM models.
%
% Assumes train_ml_model.m has already produced ml_model.mat and uses the
% same input data construction to rebuild the training table.

clear

%% Inputs (mirror train_ml_model.m)
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
radar_dir = '~/data/meteor_winds/mat/';
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';
mem_fn = '~/data/meteor_winds/mem_3_output_v1.nc';
msis_fn_fmt = '~/data/meteor_winds/msis/msis_{yyyy}_%1.1fN_%1.1fE.mat';
ml_model_fn = '~/data/meteor_winds/ml_model.mat';
mwr_freq_fn = '~/data/meteor_winds/mwr_freqs.mat';
hrs = 0:23;
ref_alt = 90E3;
ref_freq = 30;
mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};

%% Load models and ancillary data
Mdl = loadstruct(ml_model_fn);

sw = readtable(sw_fn_csv);
mem = load_mem(mem_fn);
angles = load_nc(meteor_angle_fn);
freqs = loadstruct(mwr_freq_fn);

%% Rebuild training table (same as train_ml_model.m)
flist = dir(radar_dir);
flist = flist(3:end);
Tbl_full = table();
for i = 1:length(flist)
    mwr = loadstruct(fullfile(flist(i).folder, flist(i).name));

    yr = year(min(mwr.Time(:)));
    months = unique(month(floor(mwr.Time(:))))';
    days = datenum(yr, months, 15);
    Times = days + (hrs/24)';

    [~, Peak, FWHM] = gaussfit_mwr_cts(mwr, days, hrs);
    speed = meteor_speed_density_model(Times, mwr.lat, mwr.lon, angles);
    mem_int = interp_mem(mem, mem_fields, Times, mwr.lat, mwr.lon);

    DOY = floor(Times(:)) - datenum(yr, 1, 1) + 1;
    LT = ((Times(:) - floor(Times(:))) + mwr.lon/360) * 24;
    LT(LT < 0) = LT(LT < 0) + 24;
    LT(LT >= 24) = LT(LT >= 24) - 24;

    pres = zeros(length(days), length(hrs))';
    for l1 = 1:length(hrs)
        for l2 = 1:length(days)
            pres(l1, l2) = calc_msis_pressure(Times(l1, l2), ...
                ref_alt, mwr.lat, mwr.lon, sw);
        end
    end

    Tbl = table;
    Tbl.DOY = DOY(:);
    Tbl.LT = LT(:);
    if mwr.lat > 0
        Tbl.SinDOY = sin(DOY(:) / 365 * pi);
    else
        Tbl.SinDOY = sin(DOY(:) / 365 * pi + pi);
    end
    Tbl.SinLT = sin(LT(:) / 24 * pi);
    sitename = split(flist(i).name, '_');
    Tbl.Peak = freq_vs_ht_model(freqs.(sitename{1}), Peak(:), ref_freq);
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

    Tbl_full = [Tbl_full; Tbl];
end

Tbl_train_FWHM = removevars(Tbl_full, {'Peak', 'FWHM'});
Tbl_train_peak = Tbl_train_FWHM;

%% Peak model importance
imp_peak = perm_importance(Mdl.Peak, Tbl_train_peak, Tbl_full.Peak);
imp_peak = sortrows(imp_peak, 'DeltaRMSE', 'descend');
disp('Peak feature importance (raw Delta RMSE and normalized share %):');
disp(imp_peak);

%% FWHM model importance
imp_fwhm = perm_importance(Mdl.FWHM, Tbl_train_FWHM, Tbl_full.FWHM);
imp_fwhm = sortrows(imp_fwhm, 'DeltaRMSE', 'descend');
disp('FWHM feature importance (raw Delta RMSE and normalized share %):');
disp(imp_fwhm);

%% Permutation importance helper (loop to avoid indexing issues)
function tbl = perm_importance(model, X, y)
    feats = X.Properties.VariableNames;
    rows = cell(numel(feats), 1);
    for k = 1:numel(feats)
        rows{k} = local_perm_one(model, X, y, feats{k});
    end
    rows = vertcat(rows{:});  % each row is a 1x3 cell
    tbl = cell2table(rows, 'VariableNames', {'Feature','DeltaRMSE','BaselineRMSE'});
    total_importance = sum(max(tbl.DeltaRMSE, 0), 'omitnan');
    if total_importance == 0
        tbl.NormPctTotalImportance = NaN(height(tbl), 1);
    else
        tbl.NormPctTotalImportance = 100 * max(tbl.DeltaRMSE, 0) ./ total_importance;
    end
end

%% Local function for one feature
function row = local_perm_one(model, X, y, featName)
    yhat = predict(model, X);
    rmse0 = sqrt(mean((y - yhat).^2, 'omitnan'));
    Xp = X;
    Xp.(featName) = Xp.(featName)(randperm(height(Xp)));
    yhatp = predict(model, Xp);
    rmsep = sqrt(mean((y - yhatp).^2, 'omitnan'));
    row = {featName, rmsep - rmse0, rmse0};
end
