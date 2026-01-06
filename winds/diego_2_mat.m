%% diego_2_mat.m
% Convert Diego MPD daily files to a McMurdo-style .mat with winds.
% Winds come from the Rio Grande monthly files (load_rio_wind); counts come from MPD histograms.

clear

%% Set inputs
yr = 2020;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
in_fn_fmt = '~/data/meteor_winds/riogrande/MPD_{yyyy}/mp{yyyymmdd}.riogrande.mpd';
out_fn_fmt = '~/data/meteor_winds/mat/riogrande_{yyyy}.mat';
wind_fn_fmt = ['~/data/meteor_winds/riogrande/Winds/', ...
    'wind_Rio_GW_w_errors_{yyyymm}.txt'];
hr_grid = (0:23)';  % hours of day
alt_centers_default = (69:2:121);

%% Load winds for the year (monthly files)
wind_available = true;
try
    wind = load_rio_wind_year(days, wind_fn_fmt);
catch ME
    warning('diego_2_mat:MissingWinds', ...
        'Could not load winds (%s); continuing with counts only.', ME.message);
    wind_available = false;
end

if wind_available
    day_list = unique(floor(wind.Time));
    n_days = numel(day_list);
    n_hr = numel(hr_grid);
    alt = wind.alt(:);
    n_alt = numel(alt);
    alt_edges = alt_edges_from_centers(alt);

    u = nan(n_alt, n_hr, n_days);
    v = nan(n_alt, n_hr, n_days);
    Time = nan(n_hr, n_days);
    for ti = 1:numel(wind.Time)
        dn = floor(wind.Time(ti));
        di = find(day_list == dn, 1);
        if isempty(di)
            continue;
        end
        hr_val = (wind.Time(ti) - dn) * 24;
        [~, hi] = min(abs(hr_grid - hr_val));
        u(:, hi, di) = wind.u(ti, :)';
        v(:, hi, di) = wind.v(ti, :)';
        Time(hi, di) = wind.Time(ti);
    end
else
    day_list = days;
    n_days = numel(day_list);
    n_hr = numel(hr_grid);
    alt = alt_centers_default(:);
    n_alt = numel(alt);
    alt_edges = alt_edges_from_centers(alt);
    u = [];
    v = [];
    Time = [];
end

%% Counts from MPD files, matched to the same day list
counts = nan(n_alt, n_hr, n_days);
mpd_lat = NaN; mpd_lon = NaN;
for di = 1:n_days
    dn = day_list(di);
    disp(datestr(dn))
    in_fn = filename(in_fn_fmt, dn);
    try
        [times, hts, ~, mpd_lat, mpd_lon] = read_diego_file(in_fn);
    catch
        fprintf('%s not loaded\n', in_fn)
        continue
    end
    hrs = (times - floor(times)) * 24;
    for hi = 1:n_hr
        mask = hrs >= hr_grid(hi) & hrs < hr_grid(hi) + 1;
        counts(:, hi, di) = histcounts(hts(mask), alt_edges);
    end
end

%% Store and save
out.lat = NaN;
out.lon = NaN;
if wind_available
    out.lat = wind.lat;
    out.lon = wind.lon;
end
if any(~isfinite([out.lat, out.lon])) && all(isfinite([mpd_lat, mpd_lon]))
    out.lat = mpd_lat;
    out.lon = mpd_lon;
end
out.counts = counts;
if wind_available
    out.u = u;
    out.v = v;
end
out.alt = alt;
if wind_available
    out.Time = Time;
end
out.hour = hr_grid;
savestruct(filename(out_fn_fmt, min(days)), out)

%% Helpers
function wind = load_rio_wind_year(days, wind_fn_fmt)
for ti = 1:length(days)
    if ti == 1 
       wind = load_rio_wind(filename(wind_fn_fmt, days(ti)));
       fn = fieldnames(wind);
    elseif month(days(ti)) ~= month(days(ti - 1))
        w_t = load_rio_wind(filename(wind_fn_fmt, days(ti)));
        for fi = 1:length(fn)
            wind.(fn{fi}) = cat(1, wind.(fn{fi}), w_t.(fn{fi}));
            wind.alt = w_t.alt;
            wind.lat = w_t.lat;
            wind.lon = w_t.lon;
            wind.hour = w_t.hour;
        end
    end
end
end

function edges = alt_edges_from_centers(centers)
centers = centers(:);
if numel(centers) == 1
    edges = [centers - 0.5; centers + 0.5];
    return;
end
midpoints = movmean(centers, 2, 'Endpoints', 'discard');
edges = [centers(1) - (midpoints(1) - centers(1)); ...
    midpoints; ...
    centers(end) + (centers(end) - midpoints(end))];
end

function [times, hts, sitename, lat, lon] = read_diego_file(in_fn)
txt = asciiread(in_fn);
sitename = strsplit(txt(2, :));
sitename = sitename{2};
location = strsplit(txt(3, :));
location = strsplit(location{2}, ',');
lat = str2double(location{1});
lon = str2double(location{2});
vals = txt(30:end, :);

npts = size(vals, 1);
times = zeros(npts, 1);
hts = zeros(npts, 1);
for i = 1:npts
    line = strsplit(vals(i, :));
    times(i) = datenum(datetime([line{2}, ' ', line{3}], ...
        'InputFormat', 'yyyy/MM/dd HH:mm:ss.SSS'));
    hts(i) = str2double(line{6});
    % Vrad = str2double(line{7});
    % delVr = str2double(line{8});
    % Theta = str2double(line{9});
    % Phi = str2double(line{10});
end
end
