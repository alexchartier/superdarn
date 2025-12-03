%% fir_annual_plot.m

clear

%% Set inputs
days = datenum(2010, 1, 1):datenum(2011,1, 1);
months = datenum(2010, 1:12, 15);
hr = 0:23;
sd_fn_fmt = '~/data/superdarn/meteorwindnc/{yyyy}/{mm}/{yyyymmmdd}.{NAME}.nc';
sd_mat_fn_fmt = '~/data/meteor_winds/sd_mat/{YYYY}_{NAME}.mat';
ctmt_coeff_fn = '~/data/ctmt/coeffs.mat';
ml_model_fn = '~/data/meteor_winds/ml_model.mat';
mem_fn = '~/data/meteor_winds/mem_3_output_v1.nc';
mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';
radarcode = 'fir'; % 'han';


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


%% Plot 

LTwinds_sd_u = UT_to_LT(sd.u_med, sd.hour', hr, sd.pos(2));
LTwinds_sd_v = UT_to_LT(sd.v_med, sd.hour', hr, sd.pos(2));
LTwinds_sd_u(abs(LTwinds_sd_u) > 50) = NaN;
tiledlayout(1, 2, 'TileSpacing', 'compact')



nexttile
contourf(days, lt, LTwinds_sd_v)
colormap(gca, jet)
title('Meridional')
grid on
grid minor
clim([-40, 40])
ylabel('LST (hr)')
datetick('x', 'mmm', 'keepticks', 'keeplimits')


nexttile
contourf(days, lt, LTwinds_sd_u)
colormap(gca, jet)
title('Zonal')
grid on
grid minor
clim([-40, 40])
datetick('x', 'mmm', 'keepticks', 'keeplimits')
yticklabels('')




colorbar
cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Wind (m/s)', 'FontSize', 24)












