%% implement something like C++ meteorproc algorithm in MATLAB

%% Set inputs
times = datenum(2019, 1, 1):datenum(2020, 1, 1);
radarcode = 'fir';
in_fn_fmt = '~/data/superdarn/netcdf/fir/{yyyymmdd}.{NAME}.v2.5.nc';
out_fn_fmt = '~/data/meteor_winds/fir_matlab/{yyyymmdd}.{NAME}.mat';
Vlos_max = 50;  % line-of-sight velocity
SNR_min = 3;  % signal-to-noise ratio
range_max = 405; % virtual range
Verr_max = 50; % velocity error

nbeams_min = 5;
hrs = 0:23;


%% loop over times
for ti = 1:length(times)
    %% Setup storage
    time = times(ti);
    clear out
    out.u = nan(size(hrs));
    out.v = nan(size(hrs));
    out.tfreq_khz = nan(size(hrs));
    out.ct = nan(size(hrs));

    %% Load
    sd_fn = filename(in_fn_fmt, time, radarcode);
    try
        sd = load_sd_met(sd_fn);
    catch
        fprintf('Could not load %s\n', sd_fn)
        continue
    end

    %% Remove values >Vlos, <SNR_min, >range, >Verr, >w_l
    goodidx = ...
        (sd.range < range_max) & ...
        (abs(sd.v) < Vlos_max) & ...
        (sd.p_l > SNR_min) & ...
        (sd.v_e < Verr_max) & ...
        (sd.gflg == 0);

    for i = 1:length(sd.vars)
        sd.(sd.vars{i}) = sd.(sd.vars{i})(goodidx);
    end
    sd.hr = (sd.mjd - floor(sd.mjd)) * 24;

    %% Load 
    % fit 1 hour's data at a time
    for hi = 1:length(hrs)
        bmavg = nan(size(sd.brng));
        bmstd = nan(size(sd.brng));
        hri = sd.hr > hrs(hi) & sd.hr < hrs(hi) + 1;
        for bmi = 1:length(sd.brng)
            bmidx = sd.beam == bmi-1;
            bmavg(bmi) = median(sd.v(hri & bmidx));
            nobs(bmi) = sum(hri & bmidx);
        end

        % skip if <nbeams available
        if sum(~isnan(bmavg)) < nbeams_min
            continue
        end
        [u, v] = optimize(bmavg, nobs, sd.brng);
        out.u(hi) = u;
        out.v(hi) = v;
        out.tfreq_khz(hi) = nanmedian(sd.tfreq(hri));
        out.ct(hi) = sum(nobs);
    end
    out.lat = sd.radarlat;
    out.lon = sd.radarlon;
    out_fn = filename(out_fn_fmt, time, radarcode);
    fprintf('Saved to %s\n', out_fn)
    savestruct(out_fn, out)

end

%% 
function [u, v] = optimize(bmavg, nobs, brngs)
% Hx = z
% x = [u, v]
% H = [cos(theta) .* v + sin(theta) .* u; ...]; for all theta
% z = avg winds in each direction
% arg. min. (abs(z - Hx) ./ stdev(z))

finind = ~isnan(bmavg);
brngs = brngs(finind);
bmavg = bmavg(finind);
nobs = nobs(finind);

fn = @(x) ...
    sum(abs((cosd(brngs) .* x(2) + sind(brngs) .* x(1)) - bmavg) .* nobs);
x = fminsearch(fn, [0, 0]);
u = x(1);
v = x(2);
end



%% Load a superdarn file with the bearing info
function sd = load_sd_met(sd_fn)
sd = load_nc(sd_fn);
sd.vars = fieldnames(sd);
sd.brng = ncreadatt(sd_fn, '/', 'brng_at_15deg_el');
sd.radarlat = ncreadatt(sd_fn, '/', 'lat');
sd.radarlon = ncreadatt(sd_fn, '/', 'lon');
end
