%% rio_fir_ctmt_MPD.m
% Compare the FIR SuperDARN winds against the RIO meteor winds fitted from 
% MPD files, plus the CTMT model

clear

%% Set inputs
days = datenum(2020, 1, 1):datenum(2020,12,31);
hr = 0:23;
sd_fn_fmt = '~/data/superdarn/fit_nc_3_winds/annual/{yyyy}/{NAME}_{yyyy}.nc';
mpd_nc_dir = fullfile(getenv('HOME'), 'data', 'meteor_winds', 'riogrande', 'MPD_2020_nc');
mpd_nc_glob = fullfile(mpd_nc_dir, '2020*_riogrande_winds.nc');

ctmt_coeff_fn = '~/data/ctmt/coeffs.mat';

radarcode = 'fir'; % 'han';
mwr_radar = 'rio';


%% Load
yr = year(min(days)); 
sd_fn = string(filename(sd_fn_fmt, min(days), radarcode));
sd_nc = load_nc(sd_fn);
sd.hour = sd_nc.hour(:);
sd.day_of_year = sd_nc.day_of_year(:);
u_raw = sd_nc.u;
v_raw = sd_nc.v;
if size(u_raw, 1) == numel(sd.day_of_year) && size(u_raw, 2) == numel(sd.hour)
    u_raw = u_raw';
    v_raw = v_raw';
elseif size(u_raw, 1) == numel(sd.hour) && size(u_raw, 2) == numel(sd.day_of_year)
    % already hour x day
else
    error('rio_fir_ctmt:WindShape', 'Unexpected u/v dimensions %s', mat2str(size(u_raw)));
end
sd.u = u_raw;
sd.v = v_raw;
sd.u_med = movmedian(sd.u, 31, 2, "omitnan");
sd.v_med = movmedian(sd.v, 31, 2, "omitnan");
peak_raw = sd_nc.Peak;
fwhm_raw = sd_nc.FWHM;
if size(peak_raw, 1) == numel(sd.day_of_year) && size(peak_raw, 2) == numel(sd.hour)
    peak_raw = peak_raw';
    fwhm_raw = fwhm_raw';
elseif size(peak_raw, 1) == numel(sd.hour) && size(peak_raw, 2) == numel(sd.day_of_year)
    % already hour x day
else
    error('rio_fir_ctmt:PeakShape', 'Unexpected Peak dimensions %s', mat2str(size(peak_raw)));
end
sd.Mod_Peak = peak_raw;
sd.Mod_FWHM = fwhm_raw;
sd.Mod_Peak = fillmissing(sd.Mod_Peak, 'linear', 2, 'EndValues', 'nearest');
sd.Mod_Peak = fillmissing(sd.Mod_Peak, 'linear', 1, 'EndValues', 'nearest');
sd.Mod_FWHM = fillmissing(sd.Mod_FWHM, 'linear', 2, 'EndValues', 'nearest');
sd.Mod_FWHM = fillmissing(sd.Mod_FWHM, 'linear', 1, 'EndValues', 'nearest');
sd.Mod_Peak = fillmissing(sd.Mod_Peak, 'nearest');
sd.Mod_FWHM = fillmissing(sd.Mod_FWHM, 'nearest');
try
    sd.pos = [ncreadatt(sd_fn, '/', 'radar_latitude'), ...
        ncreadatt(sd_fn, '/', 'radar_longitude')];
catch
    sd.pos = [NaN, NaN];
end
% Load Rio Grande MPD winds from daily NetCDF files (2020)
files = dir(mpd_nc_glob);
if isempty(files)
    error('rio_fir_ctmt:NoMPDNetCDF', 'No MPD NetCDF files matched %s', mpd_nc_glob);
end
[~, si] = sort({files.name});
files = files(si);

first_nc = fullfile(files(1).folder, files(1).name);
time_units = ncreadatt(first_nc, 'time', 'units');
time_units = char(time_units);
tok = textscan(time_units, 'hours since %d-%d-%d %d:%d:%d');
if any(cellfun(@isempty, tok))
    error('rio_fir_ctmt:TimeUnits', 'Unexpected time units string: %s', time_units);
end
offset_hours = double(tok{4}) + double(tok{5})/60 + double(tok{6})/3600;
time_raw = double(ncread(first_nc, 'time'));
hour_grid = time_raw(:)' + offset_hours;
n_hr = numel(hour_grid);
mwr.hour = hour_grid(:);
mwr.alt = ncread(first_nc, 'alt');
mwr.lat = ncreadatt(first_nc, '/', 'site_latitude_deg');
mwr.lon = ncreadatt(first_nc, '/', 'site_longitude_deg');

n_alt = numel(mwr.alt);
n_days = numel(files);
mwr.u = nan(n_hr * n_days, n_alt);
mwr.v = nan(n_hr * n_days, n_alt);
mwr.Time = nan(n_hr * n_days, 1);

for fi = 1:n_days
    ncfile = fullfile(files(fi).folder, files(fi).name);
    time_units = ncreadatt(ncfile, 'time', 'units');
    time_units = char(time_units);
    tok = textscan(time_units, 'hours since %d-%d-%d %d:%d:%d');
    if any(cellfun(@isempty, tok))
        error('rio_fir_ctmt:TimeUnits', 'Unexpected time units string in %s: %s', files(fi).name, time_units);
    end
    offset_hours = double(tok{4}) + double(tok{5})/60 + double(tok{6})/3600;
    time_raw = double(ncread(ncfile, 'time'));
    hrs_this = time_raw(:)' + offset_hours;
    if numel(hrs_this) ~= n_hr
        error('rio_fir_ctmt:HourCount', 'Unexpected hour dimension in %s', files(fi).name);
    end
    if any(abs(hrs_this(:) - mwr.hour) > 1e-6)
        error('rio_fir_ctmt:HourGridChange', 'Hour grid changed in %s', files(fi).name);
    end

    u_raw = ncread(ncfile, 'u');
    v_raw = ncread(ncfile, 'v');
    if size(u_raw, 1) == n_hr
        u_mat = u_raw;
        v_mat = v_raw;
    elseif size(u_raw, 2) == n_hr
        u_mat = u_raw';
        v_mat = v_raw';
    else
        error('rio_fir_ctmt:MPDWindShape', 'Unexpected u/v dimensions %s in %s', mat2str(size(u_raw)), files(fi).name);
    end

    base_dn = datenum(double(tok{1}), double(tok{2}), double(tok{3}));
    time_dn = base_dn + hrs_this(:) / 24;

    idx0 = (fi - 1) * n_hr + 1;
    idx1 = idx0 + n_hr - 1;
    mwr.u(idx0:idx1, :) = u_mat;
    mwr.v(idx0:idx1, :) = v_mat;
    mwr.Time(idx0:idx1) = time_dn;
end

ctmt = calc_ctmt_wind(loadstruct(ctmt_coeff_fn), hr, sd.pos(2));
ctmt.wind_lst = cat(3, ctmt.wind_lst, ctmt.wind_lst(:, :, 1, :, :));

%% Prepare Mod Peak/FWHM from SuperDARN annual file
if mod(numel(mwr.Time), n_hr) ~= 0
    error('rio_fir_ctmt:TimeGrid', 'MPD time array length (%d) not divisible by %d-hour grid', numel(mwr.Time), n_hr);
end
mwr_days = numel(mwr.Time) / n_hr;
mwr.Time = reshape(mwr.Time, n_hr, mwr_days);
mwr_doy = day(datetime(mwr.Time(:), 'ConvertFrom', 'datenum'), 'dayofyear');
mwr_doy = reshape(mwr_doy, size(mwr.Time));
Mod_Peak_mwr = nan(size(mwr.Time));
Mod_FWHM_mwr = nan(size(mwr.Time));
for di = 1:size(mwr.Time, 2)
    doy = mwr_doy(1, di);
    doy = min(max(doy, 1), size(sd.Mod_Peak, 2));
    Mod_Peak_mwr(:, di) = interp1(sd.hour, sd.Mod_Peak(:, doy), mwr.hour, 'linear', 'extrap');
    Mod_FWHM_mwr(:, di) = interp1(sd.hour, sd.Mod_FWHM(:, doy), mwr.hour, 'linear', 'extrap');
end
Mod_Peak_mwr = fillmissing(Mod_Peak_mwr, 'linear', 2, 'EndValues', 'nearest');
Mod_Peak_mwr = fillmissing(Mod_Peak_mwr, 'linear', 1, 'EndValues', 'nearest');
Mod_FWHM_mwr = fillmissing(Mod_FWHM_mwr, 'linear', 2, 'EndValues', 'nearest');
Mod_FWHM_mwr = fillmissing(Mod_FWHM_mwr, 'linear', 1, 'EndValues', 'nearest');
Mod_Peak_mwr = fillmissing(Mod_Peak_mwr, 'nearest');
Mod_FWHM_mwr = fillmissing(Mod_FWHM_mwr, 'nearest');

%% MWR height-avg
mwr.u_3d = permute(reshape(mwr.u, [n_hr, mwr_days, length(mwr.alt)]), [3, 1, 2]);
mwr.v_3d = permute(reshape(mwr.v, [n_hr, mwr_days, length(mwr.alt)]), [3, 1, 2]);
mwr.u_modwt = zeros(n_hr, mwr_days);
mwr.v_modwt = zeros(n_hr, mwr_days);
for hri = 1:size(mwr.Time, 1)
    for ti = 1:size(mwr.Time, 2)
        modcts = normpdf(mwr.alt, Mod_Peak_mwr(hri, ti), Mod_FWHM_mwr(hri, ti) / 2);
        mwr.u_modwt(hri, ti) = nansum(mwr.u_3d(:, hri, ti) .* modcts) ...
            / nansum(modcts);
        mwr.v_modwt(hri, ti) = nansum(mwr.v_3d(:, hri, ti) .* modcts) ...
            / nansum(modcts);
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
Mod_FWHM_month = fillmissing(Mod_FWHM_month, 'linear', 2, 'EndValues', 'nearest');

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

        time = datenum(yr, double(ctmt.months(im)), 15, ...
            double(ctmt.hours(ih)), 0, 0);
        ih2 =ih;
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
climit  = [-30, 30];
rgb = [ ...
    94    79   162
    50   136   189
   102   194   165
   171   221   164
   230   245   152
   255   255   191
   254   224   139
   253   174    97
   244   109    67
   213    62    79
   158     1    66  ] / 255;

LTwinds_mwr_u = UT_to_LT(mwr.u0_30daymed_avg, mwr.hour', 0:23, mwr.lon);
LTwinds_mwr_v = UT_to_LT(mwr.v0_30daymed_avg, mwr.hour', 0:23, mwr.lon);
LTwinds_sd_u = UT_to_LT(sd.u_med, sd.hour', 0:23, sd.pos(2));
LTwinds_sd_v = UT_to_LT(sd.v_med, sd.hour', 0:23, sd.pos(2));
LTwinds_sd_u(abs(LTwinds_sd_u) > 50) = NaN;
tiledlayout(2, 3, 'TileSpacing', 'compact')

nexttile
contourf(LTwinds_mwr_u)
colormap(gca, rgb)
title(sprintf('%s (%1.1f°N, %1.1f°E)', ...
    upper(mwr_radar), mwr.lat, mwr.lon))
ylabel(['\bf{Zonal}\rm', newline,'LST (hr)'])
grid on
grid minor
clim(climit)
xticklabels('')

nexttile
contourf(LTwinds_sd_u)
colormap(gca, rgb)
title(sprintf('%s (%1.1f°N, %1.1f°E)', ...
    upper(radarcode), sd.pos(1),sd.pos(2)))
grid on
grid minor
clim(climit)
xticklabels('')
yticklabels('')

nexttile
contourf(ctmt_ui)
colormap(gca, rgb)
title(sprintf('CTMT @ %s', upper(radarcode)))
grid on
grid minor
clim(climit)
xticklabels('')
yticklabels('')



nexttile
contourf(LTwinds_mwr_v)
colormap(gca, rgb)
ylabel(['\bf{Meridional}\rm', newline,'LST (hr)'])
grid on
grid minor
clim(climit)
xlabel("Day of Year")


nexttile
contourf(LTwinds_sd_v)
colormap(gca, rgb)
grid on
grid minor
clim(climit)
yticklabels('')
xlabel("Day of Year")


nexttile
contourf(ctmt_vi)
colormap(gca, rgb)
grid on
grid minor
clim(climit)
yticklabels('')
xlabel("Day of Year")


colorbar
cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Wind (m/s)', 'FontSize', 24)
