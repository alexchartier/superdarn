%%
ml_model_fn = '~/data/meteor_winds/ml_model.mat';
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';

hr = 0:23;
mw_radarcode = 'Jul';
koki_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', ...
    '_{yyyymmdd}.h5'};
msis_fn_fmt = '~/data/meteor_winds/msis/msis_{yyyy}_%1.1fN_%1.1fE.mat';

yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);


%% Load
koki_fn = [filename(koki_fn_fmt{1}, min(days), mw_radarcode ), ...
    filename(koki_fn_fmt{2}, max(days), mw_radarcode )];
mwr = load_mwr_simple(koki_fn);
Mdl = loadstruct(ml_model_fn);
meteor_angles = load_nc(meteor_angle_fn);
[Mod_Peak, Mod_FWHM] = run_ml_model(Mdl, mwr, sw, meteor_angles, ...
    msis_fn_fmt);

%TODO: interpolate Mod_Peak, Mod_FWHM to the full year, or similar

%% Calculate observed 
maxct = squeeze(max(mwr.counts, [], 1));
mwr.Vx = sind(sd.boresight) .* mwr.u0 + cosd(sd.boresight) .* mwr.v0;
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

