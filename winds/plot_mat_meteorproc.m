%% plot_mat_meteorproc.m
clear

%% set inputs
times = datenum(2019, 1, 1):datenum(2020, 1, 1);
radarcode = 'fir';
in_fn_fmt = '~/data/meteor_winds/fir_matlab/{yyyymmdd}.{NAME}.mat';
hr = 0.5:23.5;

%% load
sd.times = times;
sd.hour = hr;
nanarr = nan(length(hr), length(times));
sd.u = nanarr;
sd.v = nanarr;
sd.ct = nanarr;
sd.tfreq_khz = nanarr;
for ti = 1:length(times)
    fn = filename(in_fn_fmt, times(ti), radarcode);
    try
        sd_t = loadstruct(fn);
        fnames = fieldnames(sd_t);
    catch
        fprintf('%s not present\n', fn)
        continue
    end
    for i = 1:length(fnames)
        sd.(fnames{i})(:, ti) = sd_t.(fnames{i});
    end

end
sd.lon = sd_t.lon;
sd.lat = sd_t.lat;


%% 
sd.u_med = movmedian(sd.u, 31, 2);
sd.v_med = movmedian(sd.v, 31, 2);
LTwinds_sd_u = UT_to_LT(sd.u_med, sd.hour, hr, sd.lon);
LTwinds_sd_v = UT_to_LT(sd.v_med, sd.hour, hr, sd.lon);
