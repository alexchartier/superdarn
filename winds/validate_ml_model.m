%%
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';
msis_fn_fmt = '~/data/meteor_winds/msis/msis_{yyyy}_%1.1fN_%1.1fE.mat';
ml_model_fn = '~/data/meteor_winds/ml_model.mat';
mem_fn = '~/data/meteor_winds/mem_3_output_v1.nc';
mwr_fn = '~/data/meteor_winds/notused_mat/Jul_2008.mat';
mwr_freq_fn = '~/data/meteor_winds/mwr_freqs.mat';
ref_freq = 30;
mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};


%% Compare against a radar
sw = readtable(sw_fn_csv);
freqs = loadstruct(mwr_freq_fn);
Mdl = loadstruct(ml_model_fn);
mwr = loadstruct(mwr_fn);
mem = load_mem(mem_fn);


yr = year(min(mwr.Time(:)));
days = datenum(yr, 1:12, 15); % output months
hrs = 0:23;

[~, Peak, FWHM] = gaussfit_mwr_cts(mwr, days, hrs);
Peak = Peak(:);
[~, fn, ~] = fileparts(mwr_fn);
sitename = split(fn, '_');


meteor_angles = load_nc(meteor_angle_fn);
mem_int = interp_mem(mem, mem_fields, mwr.Time, mwr.lat, mwr.lon);
[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, mwr.Time, mwr.lat, mwr.lon, ...
    mem_int, sw, meteor_angles, freqs.(mwr_freq_field(sitename{1})));

times = days + hrs'/24;
ti = ismember(round(mwr.Time * 1E5), round(times * 1E5));

Mod_Peak = reshape(Mod_Peak(ti), size(Peak));
Mod_FWHM = reshape(Mod_FWHM(ti), size(FWHM));

%% Plot
rmse_peak = rmse(Mod_Peak, Peak, 'all');
rmse_fwhm = rmse(Mod_FWHM, FWHM, 'all');

bias_peak = mean(Mod_Peak(:) - Peak(:));
bias_fwhm = mean(Mod_FWHM(:) - FWHM(:));

corr_peak = corr2(Peak(:), Mod_Peak(:));
corr_fwhm = corr2(FWHM(:), Mod_FWHM(:));

fprintf('Peak RMSE: %1.2f Bias: %1.2f Corr: %1.2f\n', ...
    rmse_peak, bias_peak, corr_peak)
fprintf('FWHM RMSE: %1.2f Bias: %1.2f Corr: %1.2f\n', ...
    rmse_fwhm, bias_fwhm, corr_fwhm)
coeff1 = polyfit(Peak(:), Mod_Peak(:), 1);
coeff2 = polyfit(FWHM(:), Mod_FWHM(:), 1);
ms = 10;
tiledlayout(1, 2, 'TileSpacing','compact')
nexttile
plot(Peak(:), Mod_Peak(:), '.', 'MarkerSize', ms)
lim =[86, 96];
xlim(lim)
ylim(lim)
xlabel('Observed Peak (km)')
ylabel('Modeled Peak (km)')
grid on
grid minor

nexttile
plot(FWHM(:), Mod_FWHM(:), '.', 'MarkerSize', ms)
lim = [4, 12];
xlim(lim)
ylim(lim)
xlabel('Observed FWHM (km)')
ylabel('Modeled FWHM (km)')
grid on
grid minor
