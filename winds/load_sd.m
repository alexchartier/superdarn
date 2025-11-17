function sd = load_sd(sd_fn_fmt, radarcode, days, hours)
%% load_sd.m
%
% sd_fn_fmt = '~/data/superdarn/meteorwindnc/{yyyy}/{mm}/{yyyymmmdd}.{NAME}.nc';
% radarcode = 'han';
% days = datenum(2008, 1, 1):datenum(2008, 12, 31);
% hr = 0:23;
% sd = load_sd(sd_fn_fmt, days, hours)

%% Load each daily file
sd.Vx = zeros(length(hours), length(days)) * NaN;
sd.Vy = zeros(length(hours), length(days)) * NaN;
sd.time = zeros(length(hours), length(days)) * NaN;

for di = 1:length(days)
    sd_fn = filename(sd_fn_fmt, days(di), radarcode);
    try
        sd_t = load_nc(sd_fn);
        good_sd_fn = sd_fn;
    catch
        fprintf('%s not found\n', sd_fn)
        continue
    end

    hri = ismember(hours, sd_t.hour);
    sd.Vx(hri, di) = sd_t.Vx;
    sd.Vy(hri, di) = sd_t.Vy;
    sd.time(hri, di) = days(di) + hours(hri) / 24;
end

try
    sd.pos = [ncreadatt(good_sd_fn, '//', 'lat'), ...
        ncreadatt(good_sd_fn, '//', 'lon')];
catch
    sd = NaN;
    return
end
sd.time = sd.time + 0.5/24; % Shift time to center of hour
sd.hour = [0:23]' + 0.5;
sd.Vx_med = movmedian(sd.Vx, 31, 2, "omitnan");
sd.Vy_med = movmedian(sd.Vy, 31, 2, "omitnan");

boresight = strsplit(ncreadatt(good_sd_fn, '/', 'boresight'), ' ');
sd.boresight = str2double(boresight{1});

sd.u_med = -sd.Vy_med;
sd.v_med = sd.Vx_med;

sd.radarcode = radarcode;










