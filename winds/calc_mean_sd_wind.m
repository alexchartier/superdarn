%% calc_mean_sd_wind.m
clear

%% Set inputs
sd_fn_fmt = '~/data/superdarn/meteorwindnc/{yyyy}/{mm}/{yyyymmmdd}.{NAME}.nc';
sd_mat_fn_fmt = '~/data/meteor_winds/sd_mat/{YYYY}_{NAME}.mat';

SD_sites = {'sye', 'inv', 'ekb', 'gbr', 'tig', 'sze', 'kap', 'szw', 'unw', ...
    'cvw', 'dce', 'hok', 'cve', 'wal', 'fir', 'jme', 'pyk', 'hkw', 'fhe', ...
    'hal', 'sch', 'fhw', 'rkn', 'ice', 'kod', 'mcm', 'bpk', 'pgr', 'icw', ...
    'sys', 'adw', 'sps', 'ade', 'hjw', 'san', 'hje', 'ksr', 'lje', 'sas', ...
    'ljw', 'dcn', 'han', 'bks', 'tst', 'sto', 'lyr', 'zho', 'cly', 'ker'};

yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);
m2 = datenum(yr, 1:13, 1);
hr = 0:23;

%% Load
for s = 1:length(SD_sites)
    sd_fn = filename(sd_mat_fn_fmt, min(days), SD_sites{s});
    try
        sd = loadstruct(sd_fn);
    catch
        sd = load_sd(sd_fn_fmt, SD_sites{s}, days, hr);
        if isstruct(sd)
            savestruct(sd_fn, sd);
        end
    end

end

%%
flist = dir(sprintf('~/data/meteor_winds/sd_mat/%i*', yr));
arr = zeros([length(months)+1, length(flist)-1]);
hem = ones([1, length(flist) - 2]);
sitelist = {};
tidx = ismember(days, months);
for i = 3:length(flist)
    sd = loadstruct([flist(i).folder, '/', flist(i).name]);
    Vx_LT = UT_to_LT(sd.v_med, hr, 0:23, sd.pos(2))';
    arr(1:12, i-2) = nanmean(Vx_LT(tidx, :), 2);
    sitelist = [sitelist, sd.radarcode];
    hem(i-2) = sign(sd.pos(1));
end

%%
rgb = rgb();

colormap(rgb)
i = 0;
for hemi = [1, -1]
    i = i + 1;
    ax(i) = subplot(2, 1, i);

    hemidx = hem== hemi;

    arr2 = arr(:, hemidx);
    arr2 = [arr2, zeros([size(arr2, 1), 1])];
    hC = pcolor(m2, 1:sum(hemidx)+1, arr2');

    
    yticks([1.5:sum(hemidx) + 1]);
    yticklabels(upper(sitelist(hemidx)));
    set(hC, 'LineStyle', 'None')
    clim([-15, 15])


    if i == 2
        ylabel('Southern sites')
        xticks(months)
        datetick('x', 'mmm', 'keepticks', 'keeplimits')

        xlabel('Month of 2008')
    else
        ylabel('Northern sites')
        xticklabels('')
    end
end

pos1 = get(ax(1), 'Position');
pos2 = get(ax(2), 'Position');
pos1(4) = 0.5;
pos1(3) = pos1(3) * 0.9;
pos2(3) = pos2(3) * 0.9;
pos1(2) = 0.45;
pos2(4) = 0.25;
pos2(2) = 0.15;
set(ax(1), 'Position', pos1, 'FontSize', 20)
set(ax(2), 'Position', pos2, 'FontSize', 20)


cb = colorbar('Position', [0.85, 0.12, 0.02, 0.8]);

ylabel(cb, 'Mean Meridional Wind (m/s)', 'FontSize', 20)




