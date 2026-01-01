%% read_diego_files.m
% from  http://saamer-os.fisica.edu.uy/login.php -> orbit repository -> MPD
% files
clear
%% Set inputs
days = datenum(2020, 1, 1):datenum(2020, 12, 31);
in_fn_fmt = '~/data/meteor_winds/riogrande/MPD_{yyyy}/mp{yyyymmdd}.riogrande.mpd';
out_fn_fmt = '~/data/meteor_winds/mat/riogrande_{yyyy}.mat';
% times = [];
% hts = [];
alt_bins = 69:2:121;
hr_bins = 0:24;

%% Load
vals = zeros([length(alt_bins) - 1, length(hr_bins)-1, length(days)]);
for d = 1:length(days)
    disp(datestr(days(d)))
    in_fn = filename(in_fn_fmt, days(d));
    try
        [times, hts, sitename, lat, lon] = read_diego_file(in_fn);
    catch
        fprintf('%s not loaded', in_fn)
        continue
    end
    hrs = (times - floor(times)) * 24;

    for h = 1:length(hr_bins) - 1
        vals(:, h, d) = histcounts(...
            hts(hrs >= hr_bins(h) & hrs < hr_bins(h + 1)), alt_bins);
    end

end

%% Store and save
out.site = sitename;
out.lat = lat;
out.lon = lon;
out.counts = vals;
out.days = days;
out.alt = (alt_bins(1:end-1)' + alt_bins(2:end)') / 2;
out.hour = hr_bins(1:end-1)';
% out.hr_bins = hr_bins;
% out.alt_bins = alt_bins;
out.Time = days + hr_bins(1:end-1)'/24;
savestruct(filename(out_fn_fmt, min(days)), out)

%% Load
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