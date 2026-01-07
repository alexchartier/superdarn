%% sd_mwr_ctmt_multi.m
% Compare SuperDARN annual winds against multiple meteor wind radars (Rio, Andenes, McMurdo) plus CTMT.
% Uses annual SuperDARN fit_nc_3_winds files (with Peak/FWHM) for weighting instead of the ML model.

clear

%% Case selection
case_name = 'han_and'; % options: 'fir_rio', 'han_and', 'mcm_mcm'

sd_fn_fmt = '~/data/superdarn/fit_nc_3_winds/annual/{yyyy}/{NAME}_{yyyy}.nc';
ctmt_coeff_fn = '~/data/ctmt/coeffs.mat';

switch lower(case_name)
    case 'fir_rio'
        yr = 2019;
        sd_code = 'fir';
        mwr_cfg.type = 'mat';
        mwr_cfg.mat_fn_fmt = '~/data/meteor_winds/notused_mat/riogrande_{yyyy}.mat';
        mwr_cfg.site_name = 'rio';
        climit= [-50, 50];
    case 'han_and'
        yr = 2008;
        sd_code = 'han';
        mwr_cfg.type = 'mat';
        mwr_cfg.mat_fn_fmt = '~/data/meteor_winds/mat/And_{yyyy}.mat';
        mwr_cfg.site_name = 'and';
        climit= [-70, 70];
    case 'mcm_mcm'
        yr = 2019;
        sd_code = 'mcm';
        mwr_cfg.type = 'mat';
        mwr_cfg.mat_fn_fmt = '~/data/meteor_winds/mat/McMurdo_{yyyy}.mat';
        mwr_cfg.site_name = 'mcm';
        climit= [-50, 50];

    otherwise
        error('sd_mwr_ctmt_multi:UnknownCase', 'Unknown case_name: %s', case_name);
end

%% Common time axes
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
hr = 0:23;
n_days = numel(days);
n_hr = numel(hr);

%% Load SuperDARN annual
sd = load_sd_annual(sd_fn_fmt, sd_code, days, n_hr);

%% CTMT
ctmt = calc_ctmt_wind(loadstruct(ctmt_coeff_fn), hr, sd.pos(2));
ctmt.wind_lst = cat(3, ctmt.wind_lst, ctmt.wind_lst(:, :, 1, :, :));

%% Load meteor winds for selected site
mwr = load_mwr_generic(mwr_cfg, days);
n_hr_mwr = numel(mwr.hour);

%% Weight meteor winds by SD Peak/FWHM (hour/day)
Mod_Peak_mwr = nan(n_hr_mwr, n_days);
Mod_FWHM_mwr = nan(n_hr_mwr, n_days);
for di = 1:n_days
    doy = day(datetime(days(di), 'ConvertFrom', 'datenum'), 'dayofyear');
    doy = min(max(doy, 1), size(sd.Mod_Peak, 2));
    Mod_Peak_mwr(:, di) = interp1(sd.hour, sd.Mod_Peak(:, doy), mwr.hour, 'linear', 'extrap');
    Mod_FWHM_mwr(:, di) = interp1(sd.hour, sd.Mod_FWHM(:, doy), mwr.hour, 'linear', 'extrap');
end
Mod_Peak_mwr = fillmissing(Mod_Peak_mwr, 'linear', 2, 'EndValues', 'nearest');
Mod_FWHM_mwr = fillmissing(Mod_FWHM_mwr, 'linear', 2, 'EndValues', 'nearest');
Mod_Peak_mwr = fillmissing(Mod_Peak_mwr, 'linear', 1, 'EndValues', 'nearest');
Mod_FWHM_mwr = fillmissing(Mod_FWHM_mwr, 'linear', 1, 'EndValues', 'nearest');
Mod_Peak_mwr = fillmissing(Mod_Peak_mwr, 'nearest');
Mod_FWHM_mwr = fillmissing(Mod_FWHM_mwr, 'nearest');

mwr.u_modwt = nan(n_hr_mwr, n_days);
mwr.v_modwt = nan(n_hr_mwr, n_days);
for hri = 1:n_hr_mwr
    for di = 1:n_days
        u_prof = mwr.u_3d(:, hri, di);
        v_prof = mwr.v_3d(:, hri, di);
        if all(isnan(u_prof)) && all(isnan(v_prof))
            continue;
        end
        model_cts = normpdf(mwr.alt, Mod_Peak_mwr(hri, di), Mod_FWHM_mwr(hri, di) / 2);
        mwr.u_modwt(hri, di) = nansum(u_prof .* model_cts) ./ nansum(model_cts);
        mwr.v_modwt(hri, di) = nansum(v_prof .* model_cts) ./ nansum(model_cts);
    end
end

mwr.u0_30daymed_avg = movmedian(mwr.u_modwt, 31, 2, "omitnan");
mwr.v0_30daymed_avg = movmedian(mwr.v_modwt, 31, 2, "omitnan");

%% Interpolate and height-avg CTMT to the SuperDARN location
month_doys = day(datetime(datenum(yr, double(ctmt.months), 15), 'ConvertFrom', 'datenum'), 'dayofyear');
Mod_Peak_month = nan(length(sd.hour), length(month_doys));
Mod_FWHM_month = nan(length(sd.hour), length(month_doys));
for mi = 1:length(month_doys)
    doy = min(max(month_doys(mi), 1), size(sd.Mod_Peak, 2));
    Mod_Peak_month(:, mi) = sd.Mod_Peak(:, doy);
    Mod_FWHM_month(:, mi) = sd.Mod_FWHM(:, doy);
end
Mod_Peak_month = fillmissing(Mod_Peak_month, 'linear', 2, 'EndValues', 'nearest');
Mod_FWHM_month = fillmissing(Mod_FWHM_month, 'linear', 2, 'EndValues', 'nearest');
Mod_Peak_month = fillmissing(Mod_Peak_month, 'linear', 1, 'EndValues', 'nearest');
Mod_FWHM_month = fillmissing(Mod_FWHM_month, 'linear', 1, 'EndValues', 'nearest');
Mod_Peak_month = fillmissing(Mod_Peak_month, 'nearest');
Mod_FWHM_month = fillmissing(Mod_FWHM_month, 'nearest');

ctmt.u = squeeze(ctmt.wind_lst(1, :, :, :, :, :)); 
ctmt.v = squeeze(ctmt.wind_lst(2, :, :, :, :, :));

ctmt.u_i = zeros([length(ctmt.hours), length(ctmt.months)]);
ctmt.v_i = zeros([length(ctmt.hours), length(ctmt.months)]);
for im = 1:length(ctmt.months)
    for ih = 1:length(ctmt.hours)
        u_prof = zeros(size(ctmt.alts));
        v_prof = zeros(size(ctmt.alts));
        for ia = 1:length(ctmt.alts)
            u_prof(ia) = interp1(ctmt.lats, ...
                squeeze(ctmt.u(im, ih, ia, :))', sd.pos(1));
            v_prof(ia) = interp1(ctmt.lats, ...
                squeeze(ctmt.v(im, ih, ia, :))', sd.pos(1));
        end
        ih2 = ih;
        ih2(ih2 > 24) = ih2(ih2 > 24) - 24;
        model_cts = exp(-((ctmt.alts - Mod_Peak_month(ih2, im)).^2 / ...
            Mod_FWHM_month(ih2, im).^2));
        ctmt.u_i(ih, im) = sum(u_prof .* model_cts) ./ sum(model_cts);
        ctmt.v_i(ih, im) = sum(v_prof .* model_cts) ./ sum(model_cts);
    end
end

%% Temporal interpolation
ctmt_time = [datenum(yr - 1, 12, 15); ...
    datenum(yr, double(ctmt.months), 15); ...
    datenum(yr + 1, 1, 15)];

ctmt_u = ctmt.u_i;
ctmt_u = cat(2, ctmt_u(:, end), ctmt_u, ctmt_u(:, 1));
ctmt_ui = interp2(ctmt_time, 1:25, ctmt_u, days, [1:24]');

ctmt_v = ctmt.v_i;
ctmt_v = cat(2, ctmt_v(:, end), ctmt_v, ctmt_v(:, 1));
ctmt_vi = interp2(ctmt_time, 1:25, ctmt_v, days, [1:24]');
 
%% Plot 

rgb = rgb();
contour_levels = 30;
line_levels = 11;
level_list = [-100:10:100];

LTwinds_mwr_u = UT_to_LT(mwr.u0_30daymed_avg, mwr.hour', 0:23, mwr.lon);
LTwinds_mwr_v = UT_to_LT(mwr.v0_30daymed_avg, mwr.hour', 0:23, mwr.lon);
LTwinds_sd_u = UT_to_LT(sd.u_med, sd.hour', 0:23, sd.pos(2));
LTwinds_sd_v = UT_to_LT(sd.v_med, sd.hour', 0:23, sd.pos(2));
tiledlayout(2, 3, 'TileSpacing', 'compact')

minmax = @(x) [min(x(:), [], 'omitnan'), max(x(:), [], 'omitnan')];
fprintf('Subplot min/max (m/s):\n');
fprintf('  MWR zonal:   [%0.1f, %0.1f]\n', minmax(LTwinds_mwr_u));
fprintf('  SD zonal:    [%0.1f, %0.1f]\n', minmax(LTwinds_sd_u));
fprintf('  CTMT zonal:  [%0.1f, %0.1f]\n', minmax(ctmt_ui));
fprintf('  MWR merid.:  [%0.1f, %0.1f]\n', minmax(LTwinds_mwr_v));
fprintf('  SD merid.:   [%0.1f, %0.1f]\n', minmax(LTwinds_sd_v));
fprintf('  CTMT merid.: [%0.1f, %0.1f]\n', minmax(ctmt_vi));

nexttile
contourf(LTwinds_mwr_u, contour_levels, 'LineStyle', 'none')
hold on
contour(LTwinds_mwr_u, level_list, 'LineColor', [0.2 0.2 0.2], 'ShowText', 'on')
colormap(gca, rgb)
title(sprintf('%s (MWR, %1.1f°N, %1.1f°E)', ...
    upper(mwr_cfg.site_name), mwr.lat, mwr.lon))
ylabel(['\bf{Zonal}\rm', newline,'LST (hr)'])
grid on
grid minor
clim(climit)
xticklabels('')
hold off

nexttile
contourf(LTwinds_sd_u, contour_levels, 'LineStyle', 'none')
hold on
contour(LTwinds_sd_u, level_list, 'LineColor', [0.2 0.2 0.2], 'ShowText', 'on')
colormap(gca, rgb)
title(sprintf('%s (SD, %1.1f°N, %1.1f°E)', ...
    upper(sd_code), sd.pos(1),sd.pos(2)))
grid on
grid minor
clim(climit)
xticklabels('')
yticklabels('')
hold off

nexttile
contourf(ctmt_ui, contour_levels, 'LineStyle', 'none')
hold on
contour(ctmt_ui, level_list, 'LineColor', [0.2 0.2 0.2], 'ShowText', 'on')
colormap(gca, rgb)
title(sprintf('CTMT @ %s', upper(sd_code)))
grid on
grid minor
clim(climit)
xticklabels('')
yticklabels('')
hold off



nexttile
contourf(LTwinds_mwr_v, contour_levels, 'LineStyle', 'none')
hold on
contour(LTwinds_mwr_v, level_list, 'LineColor', [0.2 0.2 0.2], 'ShowText', 'on')
colormap(gca, rgb)
ylabel(['\bf{Meridional}\rm', newline,'LST (hr)'])
grid on
grid minor
clim(climit)
xlabel("Day of Year")
hold off


nexttile
contourf(LTwinds_sd_v, contour_levels, 'LineStyle', 'none')
hold on
contour(LTwinds_sd_v, level_list, 'LineColor', [0.2 0.2 0.2], 'ShowText', 'on')
colormap(gca, rgb)
grid on
grid minor
clim(climit)
yticklabels('')
xlabel("Day of Year")
hold off


nexttile
contourf(ctmt_vi, contour_levels, 'LineStyle', 'none')
hold on
contour(ctmt_vi, level_list, 'LineColor', [0.2 0.2 0.2], 'ShowText', 'on')
colormap(gca, rgb)
grid on
grid minor
clim(climit)
yticklabels('')
xlabel("Day of Year")
hold off


colorbar
cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Wind (m/s)', 'FontSize', 24)

%% correlations
crr = xcorr2(LTwinds_mwr_u, LTwinds_sd_u);
[ssr, snd] = max(crr(:));
[ij,ji] = ind2sub(size(crr),snd);
fprintf('MWR vs SD: %i, %i\n', ij, ji)

crr = xcorr2(ctmt_ui, LTwinds_sd_u);
[ssr, snd] = max(crr(:));
[ij,ji] = ind2sub(size(crr),snd);
fprintf('CTMT vs SD: %i, %i\n', ij, ji)


%% ---- Helpers ----
function sd = load_sd_annual(sd_fn_fmt, radarcode, days, n_hr)
sd_fn = string(filename(sd_fn_fmt, min(days), radarcode));
if ~isfile(sd_fn)
    error('sd_mwr_ctmt_multi:MissingAnnual', 'SuperDARN annual file not found: %s', sd_fn);
end
sd_nc = load_nc(sd_fn);
sd.hour = sd_nc.hour(:);
sd.day_of_year = sd_nc.day_of_year(:);
u_raw = sd_nc.u;
v_raw = sd_nc.v;
Mod_Peak = sd_nc.Peak;
Mod_FWHM = sd_nc.FWHM;
if size(u_raw, 1) == numel(sd.day_of_year) && size(u_raw, 2) == numel(sd.hour)
    u_raw = u_raw';
    v_raw = v_raw';
elseif ~(size(u_raw, 1) == numel(sd.hour) && size(u_raw, 2) == numel(sd.day_of_year))
    error('sd_mwr_ctmt_multi:WindShape', 'Unexpected u/v dimensions %s', mat2str(size(u_raw)));
end
if size(Mod_Peak, 1) == numel(sd.day_of_year) && size(Mod_Peak, 2) == numel(sd.hour)
    Mod_Peak = Mod_Peak';
    Mod_FWHM = Mod_FWHM';
elseif ~(size(Mod_Peak, 1) == numel(sd.hour) && size(Mod_Peak, 2) == numel(sd.day_of_year))
    error('sd_mwr_ctmt_multi:PeakShape', 'Unexpected Peak dimensions %s', mat2str(size(Mod_Peak)));
end
colMean = nanmean(Mod_Peak, 2);
for d = 1:size(Mod_Peak, 2)
    if all(isnan(Mod_Peak(:, d)))
        Mod_Peak(:, d) = colMean;
        Mod_FWHM(:, d) = nanmean(Mod_FWHM, 2);
    end
end
Mod_Peak = fillmissing(Mod_Peak, 'linear', 2, 'EndValues', 'nearest');
Mod_FWHM = fillmissing(Mod_FWHM, 'linear', 2, 'EndValues', 'nearest');
Mod_Peak = fillmissing(Mod_Peak, 'linear', 1, 'EndValues', 'nearest');
Mod_FWHM = fillmissing(Mod_FWHM, 'linear', 1, 'EndValues', 'nearest');
Mod_Peak = fillmissing(Mod_Peak, 'nearest');
Mod_FWHM = fillmissing(Mod_FWHM, 'nearest');
sd.Mod_Peak = Mod_Peak;
sd.Mod_FWHM = Mod_FWHM;
sd.u = u_raw;
sd.v = v_raw;
sd.v_med = movmedian(sd.v, 31, 2, "omitnan");
sd.u_med = movmedian(sd.u, 31, 2, "omitnan");
try
    sd.pos = [ncreadatt(sd_fn, '/', 'radar_latitude'), ...
        ncreadatt(sd_fn, '/', 'radar_longitude')];
catch
    sd.pos = [NaN, NaN];
end
if any(~isfinite(sd.pos))
    fallback = fallback_sd_pos(radarcode);
    missing = ~isfinite(sd.pos);
    sd.pos(missing) = fallback(missing);
end
if any(~isfinite(sd.pos))
    error('sd_mwr_ctmt_multi:MissingPosition', ...
        'Radar lat/lon missing in %s; add attributes or extend fallback map.', sd_fn);
end
if isempty(sd.hour) || any(~isfinite(sd.hour))
    sd.hour = ((0:n_hr-1)' + 0.5);
end
sd.radarcode = radarcode;
end

function mwr = load_mwr_generic(cfg, days)
switch lower(cfg.type)
    case 'mat'
        mat_fn = filename(cfg.mat_fn_fmt, min(days));
        base = loadstruct(mat_fn);
        base_time = base.Time(:);
        if isempty(base_time)
            error('sd_mwr_ctmt_multi:EmptyMat', 'No Time data in %s', mat_fn);
        end
        if ~isfield(base, 'u') || ~isfield(base, 'v')
            error('sd_mwr_ctmt_multi:NoWinds', 'Missing u/v in %s', mat_fn);
        end
        hour_grid = unique(mod(base_time(:) * 24, 24));
        base_u = reshape(permute(base.u, [2, 3, 1]), [], numel(base.alt));
        base_v = reshape(permute(base.v, [2, 3, 1]), [], numel(base.alt));
        base_lat = getfield_if_exist(base, 'lat', NaN);
        base_lon = getfield_if_exist(base, 'lon', NaN);
        mwr = assemble_mwr_profiles(days, hour_grid, base.alt, base_time, base_u, base_v, base_lat, base_lon);
    otherwise
        error('sd_mwr_ctmt_multi:BadMwrType', 'Unhandled mwr type %s', cfg.type);
end
end

function val = getfield_if_exist(s, name, default)
if isfield(s, name)
    val = s.(name);
else
    val = default;
end
end

function mwr = assemble_mwr_profiles(days, hour_grid, alt, time_vec, u_mat, v_mat, lat, lon)
hour_grid = hour_grid(:);
alt = alt(:);
n_hr = numel(hour_grid);
n_days = numel(days);
n_alt = numel(alt);
u_grid = nan(n_alt, n_hr, n_days);
v_grid = nan(n_alt, n_hr, n_days);
time_grid = nan(n_hr, n_days);
for t = 1:numel(time_vec)
    dn = floor(time_vec(t));
    di = find(days == dn, 1);
    if isempty(di)
        continue;
    end
    hr_val = (time_vec(t) - dn) * 24;
    [~, hi] = min(abs(hour_grid - hr_val));
    u_grid(:, hi, di) = u_mat(t, :)';
    v_grid(:, hi, di) = v_mat(t, :)';
    time_grid(hi, di) = time_vec(t);
end
mwr.u_3d = u_grid;
mwr.v_3d = v_grid;
mwr.Time = time_grid;
mwr.alt = alt;
mwr.hour = hour_grid;
mwr.lat = lat;
mwr.lon = lon;
end

function pos = fallback_sd_pos(code)
% Fallback radar coordinates for common SuperDARN sites (lat, lon).
sd_codes = {'sye','inv','ekb','gbr','tig','sze','kap','szw','unw','cvw', ...
    'dce','hok','cve','wal','fir','jme','pyk','hkw','fhe','hal','sch', ...
    'fhw','rkn','ice','kod','mcm','bpk','pgr','icw','sys','adw','sps', ...
    'ade','hjw','san','hje','ksr','lje','sas','ljw','dcn','han','bks', ...
    'tst','sto','lyr','zho','cly','ker'};
sd_coords = [ ...
    -69.01 39.61
    68.413 -133.769
    56.43568 58.57142
    53.31753 -60.46424
    -43.40012 147.21627
    41.83265 111.93369
    49.3926 -82.32184
    41.83272 111.93093
    -46.5133 168.37569
    43.27101 -120.35856
    -75.08952 123.35125
    43.5319 143.6146
    43.27053 -120.35642
    37.8573 -75.51019
    -51.8314 -58.9793
    46.76656 130.48594
    63.77258 -20.54476
    43.5374 143.6073
    38.85877 -99.38843
    -75.62 -26.219
    54.8 -66.8
    38.85909 -99.39061
    62.828 -92.113
    63.77443 -20.54167
    57.61215 -152.19116
    -77.83777 166.657
    -34.6271 138.466
    53.98 -122.59
    63.77396 -20.54578
    -69.0 39.58
    51.89337 -176.63121
    -89.995 118.291
    51.89309 -176.62827
    42.885 83.709
    -71.67714 -2.82816
    42.885 83.709
    58.69206 -156.65922
    42.82406 129.42244
    52.16 -106.53
    42.8267 129.41775
    -75.08629 123.3599
    62.31357 26.60562
    37.10211 -77.95033
    53.32 -60.46
    63.86045 -21.0315
    78.15338 16.07342
    -69.37669 76.36646
    70.487 -68.504
    -49.35073 70.26652];
idx = find(strcmpi(code, sd_codes), 1);
if isempty(idx)
    pos = [NaN, NaN];
else
    pos = sd_coords(idx, :);
end
end
