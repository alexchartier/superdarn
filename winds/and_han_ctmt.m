%% and_han_ctmt.m
% Compare the Hankasalmi SuperDARN winds against the Andenes and Juliusruh
% meteor winds, plus the CTMT model


clear

%% Set inputs
sd_fn_fmt = '~/data/superdarn/meteorwindnc/{yyyy}/{mm}/{yyyymmmdd}.{NAME}.nc';
sd_mat_fn_fmt = '~/data/meteor_winds/sd_mat/{YYYY}_{NAME}.mat';
mwr_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
mwr_radar = 'AND';
ctmt_coeff_fn = '~/data/ctmt/coeffs.mat';
ml_model_fn = '~/data/meteor_winds/ml_model.mat';
mem_fn = '~/data/meteor_winds/mem_3_output_v1.nc';
mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';

yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);
radarcode = 'HAN'; % 'han';
hr = 0:23;
Times = months + hr'/24;

%% Load
sd_fn = filename(sd_mat_fn_fmt, min(days), lower(radarcode));
try
    sd = loadstruct(sd_fn);
catch
    sd = load_sd(sd_fn_fmt, radarcode, days, hr);
    savestruct(sd_fn, sd);
end
boresight = sd.boresight; 

mwr_fn = [filename(mwr_fn_fmt{1}, min(days), mwr_radar), ...
    filename(mwr_fn_fmt{2}, max(days), mwr_radar)];
mwr = load_mwr(mwr_fn, boresight);

Mdl = loadstruct(ml_model_fn);
mem = load_mem(mem_fn);
mem_int = interp_mem(mem, mem_fields, Times, sd.pos(1), sd.pos(2));
sw = readtable(sw_fn_csv);
meteor_angles = load_nc(meteor_angle_fn);

ctmt = calc_ctmt_wind(loadstruct(ctmt_coeff_fn), hr, sd.pos(2));
ctmt.wind_lst = cat(3, ctmt.wind_lst, ctmt.wind_lst(:, :, 1, :, :));

%% Run the ML model to get model peak and FWHM at the site
[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, Times, sd.pos(1), sd.pos(2), ...
    mem_int, sw, meteor_angles);

%% Interpolate CTMT to the SuperDARN location and boresight
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
        model_cts = exp(-((ctmt.alts - Mod_Peak(ih2, im)).^2 / ...
            Mod_FWHM(ih2, im).^2));
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

tidx = ismember(round(mwr.Time * 1E5), round(Times * 1E5));
LTwinds_mwr_u = UT_to_LT(mwr.u0_30daymed_avg, mwr.hour', 0:23, mwr.lon);
LTwinds_mwr_v = UT_to_LT(mwr.v0_30daymed_avg, mwr.hour', 0:23, mwr.lon);
LTwinds_sd_u = UT_to_LT(sd.u_med, sd.hour', 0:23, sd.pos(2));
LTwinds_sd_v = UT_to_LT(sd.v_med, sd.hour', 0:23, sd.pos(2));

tiledlayout(2, 3, 'TileSpacing', 'compact')

nexttile
contourf(LTwinds_mwr_u)
colormap(gca, rgb)
title(sprintf('%s (%1.1f°N, %1.1f°E)', ...
    upper(mwr_radar), mwr.lat, mwr.lon))
ylabel(['\bf{Zonal}\rm', newline,'LST (hr)'])
grid on
grid minor
clim([-50, 50])
xticklabels('')

nexttile
contourf(LTwinds_sd_u)
colormap(gca, rgb)
title(sprintf('%s (%1.1f°N, %1.1f°E)', ...
    upper(radarcode), sd.pos(1),sd.pos(2)))
grid on
grid minor
clim([-50, 50])
xticklabels('')
yticklabels('')

nexttile
contourf(ctmt_ui)
colormap(gca, rgb)
title(sprintf('CTMT @ %s', upper(radarcode)))
grid on
grid minor
clim([-50, 50])
xticklabels('')
yticklabels('')

nexttile
contourf(LTwinds_mwr_v)
colormap(gca, rgb)
ylabel(['\bf{Meridional}\rm', newline,'LST (hr)'])
grid on
grid minor
clim([-50, 50])
xlabel("Day of Year")

nexttile
contourf(LTwinds_sd_v)
colormap(gca, rgb)
grid on
grid minor
clim([-50, 50])
yticklabels('')
xlabel("Day of Year")

nexttile
contourf(ctmt_vi)
colormap(gca, rgb)
grid on
grid minor
clim([-50, 50])
yticklabels('')
xlabel("Day of Year")

colorbar
cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Wind (m/s)', 'FontSize', 24)


%% correlations
crr = xcorr2(LTwinds_mwr_u, LTwinds_sd_u);
[ssr, snd] = max(crr(:));
[ij,ji] = ind2sub(size(crr),snd);
fprintf('MWR vs SD: %i, %i\n', ij, ji)



crr = xcorr2(ctmt_vi, LTwinds_sd_v);
[ssr, snd] = max(crr(:));
[ij,ji] = ind2sub(size(crr),snd);
fprintf('CTMT vs SD: %i, %i\n', ij, ji)












