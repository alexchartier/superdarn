%%
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_v3.nc';
msis_fn_fmt = '~/data/meteor_winds/msis_{yyyy}_%1.1fN_%1.1fE.mat';
ml_model_fn = '~/data/meteor_winds/ml_model.mat';



%% Compare against Koki's radar
Mdl = loadstruct(ml_model_fn);


mwr = loadstruct('~/data/meteor_winds/notused_mat/Jul_2020.mat');
mwr = loadstruct('~/data/meteor_winds/mat/Jul_2008.mat');
yr = year(min(mwr.Time(:)));
days = datenum(yr, 1:12, 15); % output months
hrs = 0:23;

[~, Peak, FWHM] = gaussfit_mwr_cts(mwr, days, hrs);
[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, mwr, sw_fn_csv, meteor_angle_fn, ...
    msis_fn_fmt);

%% Plot
rmse_peak = rmse(Mod_Peak, Peak, 'all');
rmse_fwhm = rmse(Mod_FWHM, FWHM, 'all');
fprintf('Peak RMSE: %1.1f\n', rmse_peak)
fprintf('FWHM RMSE: %1.1f\n', rmse_peak)

ms = 10;
tiledlayout(1, 2, 'TileSpacing','compact')
nexttile
plot(Peak(:), Mod_Peak(:), '.', 'MarkerSize', ms)
lim =[85, 95];
xlim(lim)
ylim(lim)
grid on
grid minor

nexttile
plot(FWHM(:), Mod_FWHM(:), '.', 'MarkerSize', ms)
lim =[5, 12];
xlim(lim)
ylim(lim)
grid on
grid minor