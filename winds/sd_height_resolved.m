%% sd_height_resolved.m
% Calculate height-resolved meteor winds from fitACF data


%% Inputs
in_fn_fmt = '~/data/netcdf/{YYYYmmdd}.han.v3.0.nc';
data_fn = '~/data/netcdf/sd.mat';

preproc = false;

times = datenum(2016, 1, 1):datenum(2016, 12, 31);
hours = 0:23;
heights = 70:10:110;

MAX_VEL = 100.0;
MIN_SN = 3.0;
MAX_MET_RANGE = 405;
VM_BEAM = 2;
BM_TYPE = 0;
MAX_V_ERR = 50;
MAX_W_L = 25.0;
MIN_BEAMS = 5;
METEOR_HEIGHT = 95;


%% Setup output storage
zarr = zeros(length(days), length(hours), length(heights)) * NaN;
out.v = zarr;
out.v_e = zarr;
out.elv = zarr;


%% Load
if preproc
    loaded = 0;
    for t = 1:length(times)
        % Load daily file
        in_fn = filename(in_fn_fmt, times(t));
        if ~isfile(in_fn)
            continue
        end

        boresight = ncreadatt(in_fn, '/', 'boresight');
        beams = ncreadatt(in_fn, '/', 'beams');
        Dt = load_nc(in_fn);

        % center_beam = beams(floor(length(beams) / 2));

        % Index and downasmple
        Dt.time = Dt.mjd + datenum(1858, 11, 17);
        goodid = (Dt.v_e < MAX_V_ERR) & (abs(Dt.v) < MAX_VEL) & (Dt.w_l < MAX_W_L) ...
            & (Dt.range < MAX_MET_RANGE) & ~Dt.gflg; % & (Dt.beam == center_beam);

        fields = fieldnames(Dt);
        for i = 1:length(fields)
            Dt.(fields{i}) = Dt.(fields{i})(goodid);
        end

        % store in holder
        if ~loaded
            D = Dt;
            loaded = 1;
        else
            for i = 1:length(fields)
                D.(fields{i}) = [D.(fields{i}); Dt.(fields{i})];
            end
        end
    end

    savestruct(data_fn, D)
end

D = loadstruct(data_fn);


%% Calculate heights (not perfect...)
D.ht = sind(double(D.elv)) .* double(D.range);
fields = fieldnames(D);


%% Loop over days
% Note: Interferometer data is often complete nonsense
times_hr = (times' + hours/24)';
% times_hr = times_hr(:);
zarr = zeros([size(times_hr)]) * NaN;
out.v = zarr;
out.counts = zarr;
for di = 1:size(zarr, 1)
    for hri = 1:size(zarr, 2)
        ti = (D.time >= times_hr(di, hri) - (0.5 / 24)) & ...
            (D.time < times_hr(di, hri) + (0.5 / 24));
        clear Dt
        for i = 1:length(fields)
            Dt.(fields{i}) = D.(fields{i})(ti);
        end
        % if sum(ti) > 0
        %     disp(1)
        % end

        % % Beam check
        % if length(unique(Dt.beam)) < MIN_BEAMS
        %     continue
        % end

        out.counts(di, hri) = sum(ti);
        out.v(di, hri) = median(Dt.v);
        % for hti = 1:size(zarr, 3)
        %     valid_vels = 
        % 
        % end
    end
end




%%
% scatter(Dt.lon, Dt.lat, 100, Dt.v, 'filled')
%
% %%
% plot(Dt.lon, Dt.lat, '.')





















