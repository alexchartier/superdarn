
%% Set inputs
ml_model_fn = '~/data/meteor_winds/ml_model.mat';
sw_fn_csv = '~/data/indices/SW-All.csv';  % from https://celestrak.org/spacedata/
meteor_angle_fn = '~/data/meteor_winds/angles_2008.nc';
mem_fn = '~/data/meteor_winds/mem_3_output_v1.nc';
mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};
hr = 0:23;
yr = 2020;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);
ref_freq = 30;
Times = months + hr'/24;
lats = -90:10:90;
lon = 0;

%% load
Mdl = loadstruct(ml_model_fn);
sw = readtable(sw_fn_csv);
meteor_angles = load_nc(meteor_angle_fn);
mem = load_mem(mem_fn);

%% Loop over lats
outsz = [length(hr), length(months), length(lats)];
Peak = nan(outsz);
FWHM = nan(outsz);
for li= 1:length(lats)
    mem_int = interp_mem(mem, mem_fields, Times, lats(li), lon);

    [Peak(:, :, li), FWHM(:, :, li)] = run_ml_model(...
        Mdl, Times, lats(li), lon, mem_int, sw, meteor_angles, ref_freq);
end

%% Plotting
tiledlayout(2, 2, "TileSpacing",'compact')

for mi = [1, 7]


    nexttile
    [C, h] = contourf(hr, lats, squeeze(Peak(:, mi, :))');
    clabel(C, h)
    colormap(gca, 'default')
    set(gca, 'XTickLabels', '')
    clim([85, 95])
    grid on
    grid minor

    if mi == 1
        ylabel('Lat (°)')
    end
    title(datestr(months(mi), 'mmmm'))
    if mi > 1
        set(gca, 'YTickLabels', '')
    end
end
cb = colorbar;
cb.Layout.Tile = 'east';
ylabel(cb, 'Peak height (km)', 'FontSize', 24)
cb.Position(4) = cb.Position(4) * 0.9;


for mi = [1, 7]
    nexttile
    [C, h] = contourf(hr, lats, squeeze(FWHM(:, mi, :))');
    clabel(C, h)
    colormap(gca, spring)
    clim([4, 12])
    grid on
    grid minor
        xlabel('Local Time (hr)')
    if mi == 1
        ylabel('Lat (°)')
    end
    if mi > 1
        set(gca, 'YTickLabels', '')
    end
    %title('Wind weighted by modeled counts')
end
cb = colorbar('Ticks', [4:11]);
cb.Layout.Tile = 'east';
ylabel(cb, 'Full Width @ Half Max (km)', 'FontSize', 24)
