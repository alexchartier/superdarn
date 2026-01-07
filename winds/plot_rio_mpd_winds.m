%% Plot height-averaged Rio Grande MPD winds for 2020
clear

% Inputs
nc_glob = fullfile(getenv('HOME'), 'data/meteor_winds/riogrande/MPD_2020_nc/2020*_riogrande_winds.nc');
lon = -67.7;  % Rio Grande longitude (deg, east positive)
lt_grid = (0:23)';        % desired local time grid

files = dir(nc_glob);
if isempty(files)
    error('No files matched %s', nc_glob);
end
[~, si] = sort({files.name});
files = files(si);
ndays = numel(files);

% Determine time/alt lengths from first file (use offset from time units)
first_file = fullfile(files(1).folder, files(1).name);
time0 = ncread(first_file, 'time');
time_units = ncreadatt(first_file, 'time', 'units');
tok = regexp(time_units, 'hours since \\d{4}-\\d{2}-\\d{2}[ T](\\d{2}):(\\d{2}):(\\d{2})', 'tokens', 'once');
offset_hours = 0;
if ~isempty(tok)
    offset_hours = str2double(tok{1}) + str2double(tok{2})/60 + str2double(tok{3})/3600;
end
alt = ncread(first_file, 'alt');
alt = alt(:);
hrs = mod(double(time0(:))' + offset_hours, 24);  % row vector of hour-of-day bin centers
ntime = numel(hrs);

u_ut = nan(ntime, ndays);
v_ut = nan(ntime, ndays);
counts_tot = nan(ntime, ndays);
peak_ut = nan(ntime, ndays);
fwhm_ut = nan(ntime, ndays);
doy = nan(ndays, 1);

for ii = 1:ndays
    ncfile = fullfile(files(ii).folder, files(ii).name);
    u = ncread(ncfile, 'u');
    v = ncread(ncfile, 'v');
    cts = ncread(ncfile, 'counts');    % integer counts

    % Ensure orientation is [time x alt]
    if size(u, 1) ~= ntime && size(u, 2) == ntime
        u = u';
        v = v';
        cts = cts';
    elseif size(u, 1) ~= ntime
        error('Unexpected shape for u in %s (got %dx%d, expected %d rows)', files(ii).name, size(u,1), size(u,2), ntime);
    end
    if size(cts, 2) ~= numel(alt)
        error('Unexpected altitude dimension in %s (got %d, expected %d)', files(ii).name, size(cts, 2), numel(alt));
    end

    csum = sum(cts, 2);                % total meteors per hour
    u_avg = nansum(u .* double(cts), 2) ./ csum;
    v_avg = nansum(v .* double(cts), 2) ./ csum;
    u_avg = u_avg(:);
    v_avg = v_avg(:);
    if numel(u_avg) ~= ntime
        error('Unexpected time dimension in %s (got %d, expected %d)', files(ii).name, numel(u_avg), ntime);
    end
    u_avg(csum == 0) = NaN;
    v_avg(csum == 0) = NaN;

    u_ut(:, ii) = u_avg;
    v_ut(:, ii) = v_avg;
    counts_tot(:, ii) = csum;

    % Fit Gaussian count profile by hour to estimate peak height and FWHM
    for tt = 1:ntime
        prof = double(cts(tt, :));
        good = isfinite(prof) & prof > 0;
        if nnz(good) < 3
            continue
        end
        try
            f = fit(alt(good), prof(good)', 'gauss1');
            peak_ut(tt, ii) = f.b1;
            if f.c1 > 0
                fwhm_ut(tt, ii) = 2 * sqrt(log(2)) * f.c1;  % convert fit width to FWHM
            end
        catch
            % Leave NaN on failed fits
        end
    end

    daystr = files(ii).name(1:8);      % yyyymmdd from filename prefix
    tt = datetime(daystr, 'InputFormat', 'yyyyMMdd');
    doy(ii) = day(tt, 'dayofyear');
end

% Convert to local time
u_lt = UT_to_LT(u_ut, hrs, lt_grid, lon);
v_lt = UT_to_LT(v_ut, hrs, lt_grid, lon);
cts_lt = UT_to_LT(counts_tot, hrs, lt_grid, lon);
peak_lt = UT_to_LT(peak_ut, hrs, lt_grid, lon);
fwhm_lt = UT_to_LT(fwhm_ut, hrs, lt_grid, lon);

% 31-day running medians (time dimension is columns)
u_lt = movmedian(u_lt, 31, 2, 'omitnan');
v_lt = movmedian(v_lt, 31, 2, 'omitnan');
peak_lt = movmedian(peak_lt, 31, 2, 'omitnan');
fwhm_lt = movmedian(fwhm_lt, 31, 2, 'omitnan');



%% Plot
clim = [-30, 30];
rgb = rgb();

figure
tiledlayout(4, 1, 'TileSpacing', 'compact')

nexttile
contourf(doy, lt_grid, u_lt, 'LineStyle', 'none')
colormap(gca, rgb)
colorbar
set(gca, 'XTickLabel', '')
ylabel('Local Time (hr)')
title('Rio Grande MPD Zonal Wind (east, m/s)')
caxis(clim)

nexttile
contourf(doy, lt_grid, v_lt, 'LineStyle', 'none')
colormap(gca, rgb)
colorbar
set(gca, 'XTickLabel', '')
ylabel('Local Time (hr)')
title('Rio Grande MPD Meridional Wind (north, m/s)')
caxis(clim)

nexttile
contourf(doy, lt_grid, peak_lt, 'LineStyle', 'none')
colormap(gca, rgb)
colorbar
set(gca, 'XTickLabel', '')
ylabel('Local Time (hr)')
title('MPD Meteor Count Gaussian Peak Height (km)')
caxis([80, 105])

nexttile
contourf(doy, lt_grid, fwhm_lt, 'LineStyle', 'none')
colormap(gca, rgb)
colorbar
xlabel("Day of Year")
ylabel('Local Time (hr)')
title('MPD Meteor Count Gaussian FWHM (km)')
caxis([4, 16])
