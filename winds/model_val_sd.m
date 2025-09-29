%% model_val_sd.m
% Validate SuperDARN winds against wind models and MWR data using the ML 
% meteor model

%% Set inputs
yr = 2008;
days = datenum(yr, 1, 1):datenum(yr, 12, 31);
months = datenum(yr, 1:12, 15);
radarcode = 'han';

ml_model_fn = '~/data/meteor_winds/ml_model.mat';
mwr_radars = {'And', 'Jul'};
mwr_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', '_{yyyymmdd}.h5'};
sd_fn_fmt = '~/data/superdarn/meteorwindnc/{yyyy}/{mm}/{yyyymmmdd}.{NAME}.nc';


%% Load
Mdl = loadstruct(ml_model_fn);

sd = load_sd(sd_fn_fmt, radarcode, days, hr);
boresight = sd.boresight; 

ctmt = loadstruct(ctmt_fn);
for i = 1:length(mwr_radars)
    mwr_fn = [filename(mwr_fn_fmt{1}, min(days), mwr_radars{i}), ...
        filename(mwr_fn_fmt{2}, max(days), mwr_radars{i})];
    mwr.(mwr_radars{i}) = load_mwr(mwr_fn, boresight);
end

%% Interpolate CTMT to the SuperDARN location and boresight
Vx_arr = squeeze(ctmt.wind(1, :, :, :, :, :) * sind(boresight) + ...
    ctmt.wind(2, :, :, :, :, :) * cosd(boresight));

ctmt.Vx = zeros([length(ctmt.hours), length(ctmt.months)]);
for im = 1:length(ctmt.months)
    for ih = 1:length(ctmt.hours)
        Vx_prof = zeros(size(ctmt.alts));
        for ia = 1:length(ctmt.alts)
            Vx_prof(ia) = interp2(ctmt.lats, ctmt.lons, ...
                squeeze(Vx_arr(im, ih, ia, :, :))', sd.pos(1), sd.pos(2));
        end

        time = datenum(yr, double(ctmt.months(im)), 15, double(ctmt.hours(ih)), 0, 0);
        % [Peak, FWHM] = mwr_ct_model(time, sd.pos(1), sd.pos(2));
        % TODO: introduce Mdl here
        model_cts = exp(-((ctmt.alts - Peak).^2 / FWHM.^2));
        ctmt.Vx(ih, im) = sum(Vx_prof .* model_cts) ./ sum(model_cts);
    end
end

%% Plotting winds from meteor model vs count-weighting
ti = ismember(months(1), days);
figure
hold on
leg = {};

for im = 1:length(mwr_radars)
    % plot(0:23, mwr.(mwr_radars{im}).Vx_med_avg(:, ti), 'LineWidth', 3)
    % plot(0:23, mwr.(mwr_radars{im}).Vx_med_modelavg(:, ti), 'LineWidth', 3)
    % TODO: convert to local time
    leg = [leg, {sprintf('%s count-weighted', mwr_radars{im}), ...
        sprintf('%s model-weighted', mwr_radars{im})}];
end

xlabel('Hour (UT)')
ylabel(sprintf('January median wind %1.0f° E of N (m/s)', boresight))
xlim([0, 24])
grid on 
grid minor
legend(leg)



