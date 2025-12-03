%% Inputs/load

in_fn ='~/data/superdarn/meteorwindnc_converted_annual/han/han_2008.nc';
lon = 26.6;
% lon = -58.979;

sd = load_nc(in_fn);
% sd.lon = ncreadatt(in_fn, '/', 'lon');
sd.lt = sd.hour + lon / 360 * 24;
sd.lt(sd.lt < 0) = sd.lt(sd.lt < 0) + 24;
sd.lt(sd.lt >= 24) = sd.lt(sd.lt >= 24) - 24;
sd.u_med = movmedian(sd.u, 31, 2, "omitnan");
sd.v_med = movmedian(sd.v, 31, 2, "omitnan");

[lt, lti] = sort(sd.lt);

%% Plotting
close
tiledlayout(1, 2, "TileSpacing",'compact')

colormap('jet')
nexttile
contourf(sd.day_of_year, lt, sd.v_med(lti, :), 50, 'LineStyle', 'none');
clim([-40, 40])
title('2008 HAN meridional')

nexttile
contourf(sd.day_of_year, lt, sd.u_med(lti, :), 50, 'LineStyle', 'none')
clim([-40, 40])
title('2008 HAN zonal')

colorbar
cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Wind (m/s)', 'FontSize', 24)
