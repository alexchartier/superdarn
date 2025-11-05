%% Set inputs
clear
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

radarcode = 'FIR'; % 'han';
mwr_radar = 'RIO';

%% Load the winds
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

%% Load meteor function
Times = days + hr'/24;
Mdl = loadstruct(ml_model_fn);
mem = load_mem(mem_fn);
mem_int = interp_mem(mem, mem_fields, Times, sd.pos(1), sd.pos(2));
sw = readtable(sw_fn_csv);
meteor_angles = load_nc(meteor_angle_fn);
[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, Times, sd.pos(1), sd.pos(2), ...
    mem_int, sw, meteor_angles);

%% 
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
mwr.Vx_med_avg = mwr.u0_30daymed_avg * sind(boresight) + ...
    mwr.v0_30daymed_avg  * cosd(boresight);

%% Interpolate CTMT to the SuperDARN location and boresight

yr = unique(year(days));
Vx_arr = squeeze(ctmt.wind_lst(1, :, :, :, :, :) * sind(boresight) + ...
    ctmt.wind_lst(2, :, :, :, :, :) * cosd(boresight));

ctmt.Vx = zeros([length(ctmt.hours), length(ctmt.months)]);
for im = 1:length(ctmt.months)
    for ih = 1:length(ctmt.hours)
        Vx_prof = zeros(size(ctmt.alts));
        for ia = 1:length(ctmt.alts)
            Vx_prof(ia) = interp1(ctmt.lats, ...
                squeeze(Vx_arr(im, ih, ia, :))', sd.pos(1));
        end

        time = datenum(yr, double(ctmt.months(im)), 15, double(ctmt.hours(ih)), 0, 0);
        ih2 =ih; 
        ih2(ih2 > 24) = ih2(ih2 > 24) - 24;
        model_cts = exp(-((ctmt.alts - Mod_Peak(ih2, im)).^2 / ...
            Mod_FWHM(ih2, im).^2));
        ctmt.Vx(ih, im) = sum(Vx_prof .* model_cts) ./ sum(model_cts);
    end
end


%% Temporal interpolation
ctmt_time = [datenum(yr - 1, 12, 15); ...
    datenum(yr, double(ctmt.months), 15); ...
    datenum(yr + 1, 1, 15)];

ctmt_Vx = ctmt.Vx;
ctmt_Vx = cat(2, ctmt_Vx(:, end), ctmt_Vx, ctmt_Vx(:, 1));

ctmt_Vxi = interp2(ctmt_time, 1:25, ctmt_Vx, days, [1:24]');

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
LTwinds_mwr = UT_to_LT(mwr.Vx_med_avg, mwr.hour', 0:23, mwr.lon);
LTwinds_sd = UT_to_LT(sd.Vx_med, sd.hour', 0:23, sd.pos(2));


tiledlayout(3, 1, 'TileSpacing', 'compact')
nexttile
contourf(LTwinds_mwr)
colormap(gca, rgb)
colorbar
ylabel('LST (hr)')
title(sprintf('%s (%1.1f°N, %1.1f°E)', ...
    upper(mwr_radar), mwr.lat, mwr.lon))

grid on
grid minor
clim([-50, 50])
xticklabels('')
cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Wind (m/s)', 'FontSize', 24)

nexttile
contourf(LTwinds_sd)
colormap(gca, rgb)
colorbar
ylabel('LST (hr)')
title(sprintf('%s (%1.1f°N, %1.1f°E)', ...
    upper(radarcode), sd.pos(1),sd.pos(2)))
grid on
grid minor
%clim([-25, 25])
clim([-50, 50])
xticklabels('')
cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Wind (m/s)', 'FontSize', 24)

nexttile
contourf(ctmt_Vxi)
colormap(gca, rgb)
colorbar
ylabel('LST (hr)')
clim([-25, 25])
title(sprintf('CTMT @ %s', upper(radarcode)))
grid on
grid minor
xlabel(sprintf('Day of Year (%i)', yr))
cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Wind (m/s)', 'FontSize', 24)


% %% correlations
% crr = xcorr2(LTwinds_mwr, LTwinds_sd);
% [ssr,snd] = max(crr(:));
% [ij,ji] = ind2sub(size(crr),snd);
% fprintf('%i, %i\n', ij, ji)
% plot(crr(ij, :))
% 




%% correlations
LTwinds_sd(isnan(LTwinds_sd)) = 0;
crr = xcorr2(LTwinds_mwr, LTwinds_sd);
[ssr,snd] = max(crr(:));
[ij,ji] = ind2sub(size(crr),snd);
fprintf('MWR vs SD: %i, %i\n', ij, ji)



crr = xcorr2(ctmt_Vxi, LTwinds_sd);
[ssr,snd] = max(crr(:));
[ij,ji] = ind2sub(size(crr),snd);
fprintf('CTMT vs SD: %i, %i\n', ij, ji)



crr = xcorr2(LTwinds_sd, LTwinds_sd);
[ssr,snd] = max(crr(:));
[ij,ji] = ind2sub(size(crr),snd);
fprintf('SD vs SD (autocorr): %i, %i\n', ij, ji)












