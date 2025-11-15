%% rio_fir_ctmt.m
% Compare the FIR SuperDARN winds against the RIO 
% meteor winds, plus the CTMT model

clear

%% Set inputs
days = datenum(2019, 1, 1):datenum(2019,12,31);
hr = 0:23;
sd_fn_fmt = '~/data/superdarn/meteorwindnc/{yyyy}/{mm}/{yyyymmmdd}.{NAME}.nc';
sd_mat_fn_fmt = '~/data/meteor_winds/sd_mat/{YYYY}_{NAME}.mat';
wind_fn_fmt = ['~/data/meteor_winds/riogrande/Winds/', '' ...
    'wind_Rio_GW_w_errors_{yyyymm}.txt'];

ctmt_coeff_fn = '~/data/ctmt/coeffs.mat';
ml_model_fn = '~/data/meteor_winds/ml_model.mat';
mem_fn = '~/data/meteor_winds/mem_3_output_v1.nc';
mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';

radarcode = 'fir'; % 'han';
mwr_radar = 'rio';


%% Load
yr = year(min(days));
sd_fn = filename(sd_mat_fn_fmt, min(days), radarcode);
try
    sd = loadstruct(sd_fn);
catch
    sd = load_sd(sd_fn_fmt, radarcode, days, hr);
    savestruct(sd_fn, sd);
end
boresight = sd.boresight; 

for ti = 1:length(days)
    if ti == 1 
       mwr = load_rio_wind(filename(wind_fn_fmt, days(ti)));
       fn = fieldnames(mwr);
    elseif month(days(ti)) ~= month(days(ti - 1))
        mwr_t = load_rio_wind(filename(wind_fn_fmt, days(ti)));
        for fi = 1:length(fn)
            mwr.(fn{fi}) = cat(1, mwr.(fn{fi}), mwr_t.(fn{fi}));
            mwr.alt = mwr_t.alt;
            mwr.lat = mwr_t.lat;
            mwr.lon = mwr_t.lon;
            mwr.hour = mwr_t.hour;

        end
        
    end
end

ctmt = calc_ctmt_wind(loadstruct(ctmt_coeff_fn), hr, sd.pos(2));
ctmt.wind_lst = cat(3, ctmt.wind_lst, ctmt.wind_lst(:, :, 1, :, :));


Mdl = loadstruct(ml_model_fn);
mem = load_mem(mem_fn);
sw = readtable(sw_fn_csv);
meteor_angles = load_nc(meteor_angle_fn);

%% MWR height-avg
Times = days + hr'/24;
mem_int = interp_mem(mem, mem_fields, Times, mwr.lat, mwr.lon);
[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, Times, mwr.lat, mwr.lon, ...
    mem_int, sw, meteor_angles);

mwr.Time = reshape(mwr.Time, 24, 365);
mwr.u_3d = permute(reshape(mwr.u, [24, 365, length(mwr.alt)]), [3, 1, 2]);
mwr.v_3d = permute(reshape(mwr.v, [24, 365, length(mwr.alt)]), [3, 1, 2]);
mwr.u_modwt = zeros(24, 365);
mwr.v_modwt = zeros(24, 365);
for hri = 1:size(mwr.Time, 1)
    for ti = 1:size(mwr.Time, 2)
        modcts = normpdf(mwr.alt, Mod_Peak(hri, ti), Mod_FWHM(hri, ti) / 2);
        mwr.u_modwt(hri, ti) = nansum(mwr.u_3d(:, hri, ti) .* modcts) ...
            / nansum(modcts);
        mwr.v_modwt(hri, ti) = nansum(mwr.v_3d(:, hri, ti) .* modcts) ...
            / nansum(modcts);
    end
end

mwr.u0_30daymed_avg = movmedian(mwr.u_modwt, 31, 2, "omitnan");
mwr.v0_30daymed_avg = movmedian(mwr.v_modwt, 31, 2, "omitnan");


%% Interpolate and height-avg CTMT to the SuperDARN location and boresight
mem_int = interp_mem(mem, mem_fields, Times, sd.pos(1), sd.pos(2));
[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, Times, sd.pos(1), sd.pos(2), ...
    mem_int, sw, meteor_angles);

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



crr = xcorr2(ctmt_u, LTwinds_sd_u);
[ssr, snd] = max(crr(:));
[ij,ji] = ind2sub(size(crr),snd);
fprintf('CTMT vs SD: %i, %i\n', ij, ji)












