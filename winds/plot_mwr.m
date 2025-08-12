%% plot_mwr.m
mwr_radars = {'And'};
mwr_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);
hr = 0:23;
alt = 80:2:100;
boresight = -12;

%% load
for i = 1:length(mwr_radars)
    mwr_fn = [filename(mwr_fn_fmt{1}, min(days), mwr_radars{i}), ...
        filename(mwr_fn_fmt{2}, max(days), mwr_radars{i})];
    mwrs.(mwr_radars{i}) = load_mwr(mwr_fn, boresight);
end
mwr = mwrs.And;


%% 
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

%% Plot
tidx = mwr.Time(1, :) >= mwr.Time(1) & mwr.Time(1, :) <= mwr.Time(31*24);
tiledlayout(2,1, 'TileSpacing', 'compact', 'Padding', 'tight'); 
nexttile

[C, h] = contourf(mwr.Time(1, tidx), alt, squeeze(mwr.u0_raw(:, 1, tidx)));
clabel(C, h)

colormap(gca, rgb)
ylabel('Alt (km)')
clim([-80, 80])
c = colorbar;
c.Label.String = 'Zonal Wind (m/s)';
set(gca, 'XTickLabels', '')
grid on 
grid minor



nexttile
[C, h] = contourf(mwr.Time(1, tidx), alt, squeeze(mwr.counts(:, 1, tidx)));
clabel(C, h)
colormap(gca, 'gray')
clim([0, 100])
c = colorbar;
c.Label.String = 'Meteor counts (#)';
grid on 
grid minor
ylabel('Alt (km)')
datetick('x', 'dd/mmm', 'keepticks', 'keeplimits')
