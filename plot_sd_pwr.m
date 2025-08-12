%% Set inputs
times = datenum(2015, 12, 20, 0, 0, 0):10/60/24:datenum(2015, 12, 21);
in_dir = '/Users/chartat1/data/superdarn/grid/';
% in_fn = '/Users/chartat1/data/superdarn/grid/20151220.bks.v3.0.grid.nc';
plt_fn_fmt = '~/data/superdarn/plots/{NAME}/{yyyymmdd_HHMM}_{NAME}.png';

Re = 64E5;
MJDstart = datenum(1858, 11, 17, 0, 0, 0);

%% Load
flist = dir(in_dir);
flist = flist(3:end);
time = [];
XYZ = [];
pwr = [];
for f = 1:length(flist)
    in_fn = [in_dir, '/', flist(f).name];
    D = load_nc(in_fn);
    D.time = (D.mjd_start + D.mjd_end) ./ 2 + MJDstart;
    D.XYZ = sphcart([ones(size(D.vector_glat)) * Re, deg2rad(D.vector_glat), deg2rad(D.vector_glon)]);
    time = [time; D.time];
    XYZ = [XYZ; D.XYZ];
    pwr = [pwr; D.vector_pwr_median];
end

norm_pwr = pwr / 30;
norm_pwr(norm_pwr > 1) = 1;

%% Plot
for t = 1:length(times)
    close
    ti = abs(time - times(t)) < (times(2) - times(1)) / 2;
    earth_example
    scatter3(XYZ(ti, 1), XYZ(ti, 2), XYZ(ti, 3), 50, norm_pwr(ti) * 256, 'filled')

    view(90, 90);
    zoom(1.3)
    text(-Re * 1.1, 0, 0, filename('{yyyy-mm-dd HH:MM} UT', times(t)), ...
        'color', 'w', 'FontSize', 40)

    export_fig(filename(plt_fn_fmt, times(t), 'north'))
    pause(0.1)
    view(-90, -90);
    export_fig(filename(plt_fn_fmt, times(t), 'south'))
    pause(0.1)
end