%% sd_height_resolved.m
% Calculate height-resolved meteor winds from fitACF data


%% Inputs 
in_fn = '/Users/chartat1/Downloads/20240510.cvw.despeck.nc';

times = datenum(2024, 1, 1):datenum(2024, 12, 31);
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
D = load_nc(in_fn);
boresight = ncreadatt(in_fn, '/', 'boresight');
beams = ncreadatt(in_fn, '/', 'beams');


%% Basic filtering
center_beam = beams(floor(length(beams) / 2));
% bi = beams == center_beam;

D.time = D.mjd + datenum(1858, 11, 17);
goodid = (D.v_e < MAX_V_ERR) & (abs(D.v) < MAX_VEL) & (D.w_l < MAX_W_L) ...
    & (D.range < MAX_MET_RANGE) & ~D.gflg & (D.beam == center_beam);

fields = fieldnames(D);
for i = 1:length(fields)
    D.(fields{i}) = D.(fields{i})(goodid);
end


%% Calculate heights (not perfect...)
D.ht = sind(double(D.elv)) .* double(D.range);
fields = fieldnames(D);


%% Loop over days
    %% Loop over hours in the day
    for hri = 1:length(hours)
        ti = (D.time >= floor(min(D.time)) + (hours(hri) - 0.5) / 24 ) & ...
            (D.time < floor(min(D.time)) + (hours(hri) + 0.5) / 24);

        for i = 1:length(fields)
            Dt.(fields{i}) = D.(fields{i})(ti);
        end

        % Beam check
        if length(unique(Dt.beam)) < MIN_BEAMS
            continue
        end

        % Store out
        for htsi = 1:length(heights)
            


            out.v(di, hri, htsi) = median(valid_vels(ri))
        end
    end

%end

%%
% scatter(Dt.lon, Dt.lat, 100, Dt.v, 'filled')
% 
% %% 
% plot(Dt.lon, Dt.lat, '.')





















