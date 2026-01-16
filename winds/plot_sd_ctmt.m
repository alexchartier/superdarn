%% plot_sd_ctmt.m
% Plot SuperDARN annual winds vs CTMT (LST, zonal/meridional only).

clear

%% Inputs
% days = datenum(2008, 1, 1):datenum(2008, 12, 31);
days = datenum(2010, 1, 1):datenum(2010, 12, 31);
hr = 0:23;
sd_fn_fmt = '~/data/superdarn/fit_nc_3_winds/annual/{yyyy}/{NAME}_{yyyy}.nc';
ctmt_coeff_fn = '~/data/ctmt/coeffs.mat';
radarcode = 'fir';

%% Load SuperDARN annual
yr = year(min(days));
sd_fn = string(filename(sd_fn_fmt, min(days), radarcode));
sd_nc = load_nc(sd_fn);
sd.hour = sd_nc.hour(:);
sd.day_of_year = sd_nc.day_of_year(:);
Mod_Peak = sd_nc.Peak; Mod_FWHM = sd_nc.FWHM;
% Ensure hour x day
if size(Mod_Peak, 1) == numel(sd.day_of_year) && size(Mod_Peak, 2) == numel(sd.hour)
    Mod_Peak = Mod_Peak'; Mod_FWHM = Mod_FWHM';
elseif ~(size(Mod_Peak, 1) == numel(sd.hour) && size(Mod_Peak, 2) == numel(sd.day_of_year))
    error('plot_sd_ctmt:PeakShape', 'Unexpected Peak dimensions %s', mat2str(size(Mod_Peak)));
end
% Fill all-NaN days with column mean across available days
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
% Winds
u_raw = sd_nc.u; v_raw = sd_nc.v;
if size(u_raw, 1) == numel(sd.day_of_year) && size(u_raw, 2) == numel(sd.hour)
    u_raw = u_raw'; v_raw = v_raw';
elseif ~(size(u_raw, 1) == numel(sd.hour) && size(u_raw, 2) == numel(sd.day_of_year))
    error('plot_sd_ctmt:WindShape', 'Unexpected u/v dimensions %s', mat2str(size(u_raw)));
end
sd.u = u_raw;
sd.v = v_raw;
sd.u_med = movmedian(sd.u, 31, 2, "omitnan");
sd.v_med = movmedian(sd.v, 31, 2, "omitnan");
try
    sd.pos = [ncreadatt(sd_fn, '/', 'radar_latitude'), ncreadatt(sd_fn, '/', 'radar_longitude')];
catch
    sd.pos = [NaN, NaN];
end

%% CTMT
ctmt = calc_ctmt_wind(loadstruct(ctmt_coeff_fn), hr, sd.pos(2));
ctmt.wind_lst = cat(3, ctmt.wind_lst, ctmt.wind_lst(:, :, 1, :, :));
ctmt.u = squeeze(ctmt.wind_lst(1, :, :, :, :, :));
ctmt.v = squeeze(ctmt.wind_lst(2, :, :, :, :, :));

% CTMT height-avg to site using SD Peak/FWHM
ctmt.u_i = zeros([length(ctmt.hours), length(ctmt.months)]);
ctmt.v_i = zeros([length(ctmt.hours), length(ctmt.months)]);
month_doys = day(datetime(datenum(yr, double(ctmt.months), 15), 'ConvertFrom', 'datenum'), 'dayofyear');
for im = 1:length(month_doys)
    doy = min(max(month_doys(im), 1), size(Mod_Peak, 2));
    for ih = 1:min(24, size(Mod_Peak, 1))
        u_prof = zeros(size(ctmt.alts));
        v_prof = zeros(size(ctmt.alts));
        for ia = 1:length(ctmt.alts)
            u_prof(ia) = interp1(ctmt.lats, squeeze(ctmt.u(im, ih, ia, :))', sd.pos(1));
            v_prof(ia) = interp1(ctmt.lats, squeeze(ctmt.v(im, ih, ia, :))', sd.pos(1));
        end
        pk = Mod_Peak(ih, doy);
        fw = Mod_FWHM(ih, doy);
        if isnan(pk) || isnan(fw) || fw == 0
            model_cts = ones(size(ctmt.alts));
        else
            model_cts = exp(-((ctmt.alts - pk).^2 / fw.^2));
        end
        ctmt.u_i(ih, im) = sum(u_prof .* model_cts) ./ sum(model_cts);
        ctmt.v_i(ih, im) = sum(v_prof .* model_cts) ./ sum(model_cts);
    end
end

% Temporal interpolation
ctmt_time = [datenum(yr - 1, 12, 15); datenum(yr, double(ctmt.months), 15); datenum(yr + 1, 1, 15)];
ctmt_u = cat(2, ctmt.u_i(:, end), ctmt.u_i, ctmt.u_i(:, 1));
ctmt_ui = interp2(ctmt_time, 1:25, ctmt_u, days, [1:24]');
ctmt_v = cat(2, ctmt.v_i(:, end), ctmt.v_i, ctmt.v_i(:, 1));
ctmt_vi = interp2(ctmt_time, 1:25, ctmt_v, days, [1:24]');

% LST conversion
LTwinds_sd_u = UT_to_LT(sd.u_med, sd.hour', 0:23, sd.pos(2));
LTwinds_sd_v = UT_to_LT(sd.v_med, sd.hour', 0:23, sd.pos(2));

% Plot
rgb = rgb();

figure;
tiledlayout(2, 2, 'TileSpacing', 'compact')

nexttile
contourf(LTwinds_sd_u, 30)
colormap(gca, rgb)
title(sprintf('%s SD (%1.1f\xB0N, %1.1f\xB0E)', upper(radarcode), sd.pos(1), sd.pos(2)))
ylabel(['\bf{Zonal}\rm', newline,'LST (hr)'])
grid on
grid minor
clim([-50, 50])
xticklabels('')

nexttile
contourf(ctmt_ui)
colormap(gca, rgb)
title(sprintf('CTMT  @ %s', upper(radarcode)))
grid on
grid minor
clim([-50, 50])
xticklabels('')
yticklabels('')

nexttile
contourf(LTwinds_sd_v)
colormap(gca, rgb)
ylabel(['\bf{Meridional}\rm', newline,'LST (hr)'])
grid on
grid minor
clim([-50, 50])
xlabel("Day of Year")

nexttile
contourf(ctmt_vi)
colormap(gca, rgb)
grid on
grid minor
clim([-50, 50])
yticklabels('')
xlabel("Day of Year")

cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Wind (m/s)', 'FontSize', 18)
