%% 

in_fn ='~/data/superdarn/meteorwindnc_converted_annual/fir/fir_2010.nc';


sd = load_nc(in_fn);
sd.lt = sd.hour + sd.lon / 360 * 24 
sd.u_med = movmedian(sd.u, 31, 2, "omitnan");
sd.v_med = movmedian(sd.v, 31, 2, "omitnan");


tiledlayout(1, 2, "TileSpacing",'compact')

colormap('jet')
nexttile
hc = pcolor(sd.day_of_year, sd.hour, sd.v_med);
set(hc, 'LineStyle', 'none')
nexttile
hc = pcolor(sd.day_of_year, sd.hour, sd.u_med);
set(hc, 'LineStyle', 'none')