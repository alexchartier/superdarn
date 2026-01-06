function plot_sd_vectors(debug, titleStr)
% plot_sd_vectors Plot per-hour LOS vectors used in meteorproc fit.
%   plot_sd_vectors(DEBUG, TITLESTR) expects DEBUG from meteorproc second
%   output and plots azimuth vs vlos for each hour with data.
%
% Example:
%   [res, dbg] = meteorproc(records, site, ...);
%   plot_sd_vectors(dbg, 'FIR 2019-05-30 LOS vectors');

if nargin < 2
    titleStr = 'LOS vectors';
end

hours = debug.hour;
n = numel(hours);
cols = ceil(sqrt(n));
rows = ceil(n / cols);

figure;
tiledlayout(rows, cols, 'TileSpacing', 'compact');
for i = 1:n
    nexttile;
    az = debug.azimuth{i};
    vlos = debug.vlos{i};
    scatter(az * 180/pi, vlos, 20, 'filled');
    xlabel('Azimuth (deg)');
    ylabel('v_{los} (m/s)');
    title(sprintf('Hour %02d', hours(i)));
    grid on; grid minor;
end
sgtitle(titleStr);
