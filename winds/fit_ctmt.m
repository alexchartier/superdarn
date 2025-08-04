%% fit_ctmt.m
% Produce a fit to the meteor wind data

yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1, 15);
% sd_radarcodes = {'bks', 'gbr', 'han', 'hok', 'inv', 'kap', 'kod', 'ksr', 'pgr', ...
%     'pyk', 'rkn', 'sas', 'sto', 'wal'};
sd_radarcodes = {'han'};
boresight = -12;
hrs = 0:23;
lons = 0:15:360;
sd_fn_fmt = '~/data/superdarn/meteorwindnc/{yyyy}/{mm}/{yyyymmmdd}.{NAME}.nc';
% mwr_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
% mwr_radars = {'And', 'Jul'};
coeff_fn = '~/data/ctmt/coeffs.mat';

sd_mat_fn = '~/data/superdarn/meteorwindnc/sd_{yyyy}.mat';

comps.d = {'w2', 'w1', 's0', 'e1', 'e2', 'e3'};
comps.sd = {'w4', 'w3', 'w2', 'w1', 's0', 'e1', 'e2', 'e3'};


%% Load
try
    sd = loadstruct(filename(sd_mat_fn, days(1)));
catch
    for ir = 1:length(sd_radarcodes)
        sd.(sd_radarcodes{ir}) = load_sd(sd_fn_fmt, sd_radarcodes{ir}, days, hr);
    end
    savestruct(filename(sd_mat_fn, days(1)), sd)
end

model_coeffs = loadstruct(coeff_fn);

%%
% optimize/modify coefficients

% u and v have identical and uniform amplitude scaling in Jens' model
% Here coeffs provide only amplitude scaling.
% Phase varies nonuniformly in Jens' output
% TODO: Try some of:
% A: No phase scaling
% B: uniform phase scaling
% C: Pick from the 12 options in the coefficients
% D: turn the coefficient phase variations into EOFs
% E: Ask Jeff Forbes for GSWM output
% F: Mean removal or estimation (makes sense for diurnal or shorter waves?)

%% Calculate original CTMT for comparison
ctmt_orig = calc_ctmt_wind(model_coeffs, hrs, lons);  % TODO: see about calculating just one month at a time


%%  Calculate CTMT with the modified coefficients
fit_coeffs = ones(length(comps.d) + length(comps.sd));
mc_tuned = model_coeffs;
dirns = {'u', 'v'};
dsd = {'d', 'sd'};
ct = 0;
for idsd = 1:length(dsd)
    for ic = 1:length(comps.d)
        ct = ct + 1;
        % Tune amplitude only
        for id = 1:length(dirns)
            strn = sprintf('amp_%s_%s', comps.(dsd{idsd}){ic}, dirns{id});
            mc_tuned.(dsd{idsd}).(strn) = mc_tuned.(dsd{idsd}).(strn) * fit_coeffs(ct);
        end
    end
end

ctmt = calc_ctmt_wind(mc_tuned, hrs, lons);  % TODO: see about calculating just one month at a time

%% calculate errors vs SD radars
ti = ismember(days, months);
for ir = 1:length(sd_radarcodes)
    sd_t = sd.(sd_radarcodes{ir});
    sd_t.Vx_med = sd_t.Vx_med(:, ti);
    sd_t.Vx_med_zeromean = sd_t.Vx_med - mean(sd_t.Vx_med, 1);
    sd_t.time = sd_t.time(:, ti);

    comp_vals.(sd_radarcodes{ir}) = calc_ctmt_at_sd(ctmt, sd_t);
end


%%
function comp_vals = calc_ctmt_at_sd(ctmt, sd)
% Interpolate CTMT to the SuperDARN times, location and boresight
Vx_arr = squeeze(ctmt.wind_ut(1, :, :, :, :, :) * sind(sd.boresight) + ...
    ctmt.wind_ut(2, :, :, :, :, :) * cosd(sd.boresight));

sd.month = month(sd.time);
sd.hour = hour(sd.time);
yr = year(sd.time);
finind = ~isnan(sd.time);

comp_vals.Vx_ctmt = zeros([length(ctmt.hours), length(ctmt.months)]);
Vx_ctmt = zeros(size(sd.time)) * NaN;
for it = 1:length(sd.time)
    if isnan(sd.time(it))
        continue
    end

    month = sd.month(it);
    hour = sd.hour(it);

    im = ctmt.months == month;
    ih = ctmt.hours == hour;
    
    Vx_prof = zeros(size(ctmt.alts));
    for ia = 1:length(ctmt.alts)
        Vx_prof(ia) = interp2(ctmt.lats, ctmt.lons, ...
            squeeze(Vx_arr(im, ih, ia, :, :))', sd.pos(1), sd.pos(2));
    end

    [Peak, FWHM] = mwr_ct_model(sd.time(it), sd.pos(1), sd.pos(2));
    model_cts = exp(-((ctmt.alts - Peak).^2 / FWHM.^2));
    Vx_ctmt(it) = sum(Vx_prof .* model_cts) ./ sum(model_cts);
end
comp_vals.Vx_sd = sd.Vx;
comp_vals.chi2 = sum((comp_vals.Vx_sd - comp_vals.Vx_ctmt).^2);

end
