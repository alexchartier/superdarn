%%
ml_model_fn = '~/data/meteor_winds/ml_model.mat';
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';
mem_fn = '~/data/meteor_winds/mem_3_output_v1.nc';
mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};

hr = 0:23;
mw_radarcode = 'Jul';
koki_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', ...
    '_{yyyymmdd}.h5'};
msis_fn_fmt = '~/data/meteor_winds/msis/msis_{yyyy}_%1.1fN_%1.1fE.mat';

yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);

boresight = 90;

%% Load
koki_fn = [filename(koki_fn_fmt{1}, min(days), mw_radarcode ), ...
    filename(koki_fn_fmt{2}, max(days), mw_radarcode )];
mwr = load_mwr_simple(koki_fn);
Mdl = loadstruct(ml_model_fn);
meteor_angles = load_nc(meteor_angle_fn);
sw = readtable(sw_fn_csv);
mem = load_mem(mem_fn);
mem_int = interp_mem(mem, mem_fields, mwr.Time, mwr.lat, mwr.lon);

[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, mwr.Time, mwr.lat, mwr.lon, ...
    mem_int, sw, meteor_angles);

%TODO: interpolate Mod_Peak, Mod_FWHM to the full year, or similar

%% Calculate observed 
maxct = squeeze(max(mwr.counts, [], 1));
mwr.Vx = sind(boresight) .* mwr.u0 + cosd(boresight) .* mwr.v0;
mwr.Vx_ctwt = nan(size(mwr.Time));
for hri = 1:size(mwr.Time, 1)
    for ti = 1:size(mwr.Time, 2)
        if ~isnan(maxct(hri, ti))
            mwr.Vx_ctwt(hri, ti) = ...
                nansum(mwr.Vx(:, hri, ti) .* mwr.counts(:, hri, ti)) ...
                / nansum(mwr.counts(:, hri, ti));
        end
    end
end


%% Calculate count-modelled 
med_Vx = movmedian(mwr.Vx, 31, 3, "omitnan");
mwr.Vx_modwt = nan(size(mwr.Time));

for hri = 1:size(mwr.Time, 1)
    for ti = 1:size(mwr.Time, 2)
        modcts = normpdf(mwr.alt, Mod_Peak(hri, ti), Mod_FWHM(hri, ti) / 2);
        mwr.Vx_modwt(hri, ti) = ...
            nansum(mwr.Vx(:, hri, ti) .* modcts) ...
            / nansum(modcts);
    end
end

%% Calculate medians
tidx = ismember(days, months);
med = movmedian(mwr.Vx_ctwt, 31, 2, "omitnan");
mwr.Vx_ctwt_med = med(:, tidx);

med = movmedian(mwr.Vx_modwt, 31, 2, "omitnan");
mwr.Vx_modwt_med = med(:, tidx);

%% Plot
rgb = rgb();

climit = [-50, 50];
clf
tiledlayout(2, 1, 'TileSpacing', 'compact')

nexttile
[C, h] = contourf(mwr.Vx_ctwt_med);
clabel(C, h)
colormap(gca, rgb)
set(gca, 'XTickLabels', '')
clim(climit)
grid on
grid minor
ylabel('Hour (UT)')
title('Wind weighted by observed counts')

nexttile
[C, h] = contourf(mwr.Vx_modwt_med);
clabel(C, h)
colormap(gca, rgb)
clim(climit)
grid on
grid minor
ylabel('Hour (UT)')
title('Wind weighted by modeled counts')

cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Height-averaged 31-day median zonal wind (m/s)', 'FontSize', 24)
xlabel(sprintf('Month of %i', yr))
