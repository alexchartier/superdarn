%% calc_mean_sd_wind.m
clear

%% Set inputs
annual_dir_fmt = '~/data/superdarn/fit_nc_3_winds/annual/%04d/';

yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);
m2 = datenum(yr, 1:13, 1);
hr = 0:23;

%% Load annual SuperDARN winds and compute monthly means (meridional)
annual_dir = expandPath(sprintf(annual_dir_fmt, yr));
files = dir(fullfile(annual_dir, sprintf('*_%04d.nc', yr)));
arr = nan(length(months) + 1, numel(files));
hem = nan(1, numel(files));
sitelist = cell(1, numel(files));
col = 0;

for f = 1:numel(files)
    sd_fn = fullfile(files(f).folder, files(f).name);
    parts = regexp(files(f).name, '([a-z0-9]+)_\d{4}\.nc', 'tokens', 'once');
    radar_code = parts{1};

    try
        hour = double(ncread(sd_fn, 'hour'));
        day_of_year = double(ncread(sd_fn, 'day_of_year'));
        v_sd = ncread(sd_fn, 'v'); % expect day_of_year x hour
        lon = ncreadatt(sd_fn, '/', 'radar_longitude');
        lat = ncreadatt(sd_fn, '/', 'radar_latitude');
    catch ME
        warning('calc_mean_sd_wind:ReadFail', 'Failed to read %s (%s)', sd_fn, ME.message);
        continue
    end

    hr_len = numel(hour);
    day_len = numel(day_of_year);
    if size(v_sd, 1) == day_len && size(v_sd, 2) == hr_len
        v_hr_day = permute(v_sd, [2, 1]); % to hours x days
    elseif size(v_sd, 1) == hr_len && size(v_sd, 2) == day_len
        v_hr_day = v_sd; % already hours x days
    else
        warning('calc_mean_sd_wind:DimMismatch', ...
            'Unexpected v dimensions %s for %s', mat2str(size(v_sd)), sd_fn);
        continue
    end

    v_med = movmedian(v_hr_day, 31, 2, 'omitnan');

    % Convert to local solar time
    LT_v = UT_to_LT(v_med, hour(:)', 0:23, lon);

    % Map mid-month days and average over hours
    sd_days = datenum(yr, 1, 1) + day_of_year(:)' - 1;
    tidx = ismember(sd_days, months);
    if ~any(tidx)
        fprintf('No mid-month days for %s\n', radar_code);
        continue
    end
    col = col + 1;
    arr(1:length(months), col) = nanmean(LT_v(:, tidx), 1)';
    hem(col) = sign(lat);
    sitelist{col} = radar_code;
end

% Trim unused columns
arr = arr(:, 1:col);
hem = hem(1:col);
sitelist = sitelist(1:col);
if col == 0
    error('calc_mean_sd_wind:NoData', 'No annual SuperDARN files found for %d.', yr);
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

function path = expandPath(rawPath)
if isempty(rawPath)
    path = '';
    return;
end
if size(rawPath, 1) > 1
    rawPath = rawPath(1, :);
end
path = strtrim(rawPath);
if startsWith(path, "~")
    path = fullfile(getenv('HOME'), path(2:end));
end
path = strrep(path, '\', filesep);
path = strrep(path, '//', '/');
end
