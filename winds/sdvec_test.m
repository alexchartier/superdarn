function sdvec_test(hr_plot, useDerivedAz)
% sdvec_test Optional args: hour, useDerivedAz (boolean).
% useDerivedAz=true forces beam headings from bmsep/boresight instead of brng_at_15deg_el.
addpath('/Users/chartat1/superdarn/winds');  % meteorproc.m, plot_sd_vectors.m

% ncfile = '/Users/chartat1/data/superdarn/fit_nc_3/2019/05/20190530.fir.nc';
ncfile = '/Users/chartat1/data/superdarn/fit_nc_3/2019/12/20191201.fir.a.nc';



if nargin < 1
    hr_plot = [];
end
if nargin < 2
    useDerivedAz = false;
end

% Helper
function val = attributeValue(attrs, name, default)
idx = find(strcmpi({attrs.Name}, name), 1);
if isempty(idx), val = default; else, val = attrs(idx).Value; end
end

% Build site from attributes
info = ncinfo(ncfile); attrs = info.Attributes;
bmsep_attr  = attributeValue(attrs, 'bmsep', NaN);
boresite_attr = attributeValue(attrs, 'boresight', NaN);
site.code     = "fir";
site.bmsep    = abs(bmsep_attr);
site.boresite = boresite_attr;
site.geolat   = attributeValue(attrs, 'lat', NaN);
site.geolon   = attributeValue(attrs, 'lon', NaN);
site.alt      = attributeValue(attrs, 'alt', 0);
beamList      = attributeValue(attrs, 'beams', []);
beamAzDeg     = attributeValue(attrs, 'brng_at_15deg_el', []);
site.maxbeam  = numel(beamList);
site.recrise  = 0;
if useDerivedAz
    bmnums = 0:(site.maxbeam - 1);
    derived_az_deg = bmsep_attr .* (bmnums - (site.maxbeam/2 - 0.5)) + boresite_attr;
    site.beam_azimuths_rad = deg2rad(double(derived_az_deg(:)));
else
    site.beam_azimuths_rad = deg2rad(double(beamAzDeg(:)));
end

% Read raw vars
mjd   = double(ncread(ncfile, 'mjd'));
beam  = double(ncread(ncfile, 'beam'));
range = double(ncread(ncfile, 'range'));
v     = double(ncread(ncfile, 'v'));
p_l   = double(ncread(ncfile, 'p_l'));
v_e   = double(ncread(ncfile, 'v_e'));
w_l   = double(ncread(ncfile, 'w_l'));

% Derived
epoch   = (mjd - 40587.0) * 86400.0;
timeKey = round(epoch * 1000); % ms
uniqueRange = unique(range);
frang = uniqueRange(1);
rsep  = uniqueRange(2) - uniqueRange(1);
gate  = int32(round((range - frang) ./ rsep));

% Build records (same as buildMeteorRecords)
combo = [timeKey(:), beam(:)];
[~, ~, grpIdx] = unique(combo, 'rows', 'stable');
counts = accumarray(grpIdx, 1);
[~, sortOrder] = sort(grpIdx);

template = struct('time', 0, 'scan', 0, ...
    'bmnum', 0, 'frang', frang, 'rsep', rsep, ...
    'rxrise', site.recrise, 'num', 0, 'rng', [], 'data', []);

records = repmat(template, numel(counts), 1);
idxStart = 1;
for g = 1:numel(counts)
    len = counts(g);
    grpIndices = sortOrder(idxStart:idxStart + len - 1);
    idxStart = idxStart + len;

    ranges = gate(grpIndices);
    vel    = v(grpIndices);
    snr    = p_l(grpIndices);
    verr   = v_e(grpIndices);

    rec = template;
    rec.time = epoch(grpIndices(1));
    rec.bmnum = beam(grpIndices(1));
    rec.num = len;
    rec.rng = ranges(:);
    rec.data = struct( ...
        'v',   num2cell(vel(:)), ...
        'p_l', num2cell(snr(:)), ...
        'v_e', num2cell(verr(:)), ...
        'w_l', num2cell(w_l(grpIndices(:))));
    records(g) = rec;
end
records = reshape(records, 1, []);

% Run meteorproc with debug and plot
[res, dbg] = meteorproc(records, site, 'SourceName', ncfile);
plot_sd_vectors(dbg, 'FIR 2019-05-30 LOS vectors');

% Quiver plot for one hour (first hour with data)
if ~isempty(dbg.hour)
    % Use the requested hour if provided, otherwise default to first available
    if ~isempty(hr_plot)
        hi = find(dbg.hour == hr_plot, 1);
        if isempty(hi)
            warning('Requested hour %g not in debug; using first available hour %g', hr_plot, dbg.hour(1));
            hi = 1;
            hr_plot = dbg.hour(1);
        end
    else
        hi = 1;
        hr_plot = dbg.hour(1);
    end
    az = dbg.azimuth{hi};
    vlos = dbg.vlos{hi};
    figure;
    polarplot(az, vlos, 'k.', 'MarkerSize', 12); hold on;
    % Mark beam azimuths at perimeter
    rmax = max(abs([vlos(:); 1])); % avoid zero radius
    if isfield(site, 'beam_azimuths_rad') && ~isempty(site.beam_azimuths_rad)
        polarplot(site.beam_azimuths_rad, rmax * ones(size(site.beam_azimuths_rad)), ...
            'bx', 'MarkerSize', 8, 'LineWidth', 1);
    end
    ridx = find(res.hour == hr_plot, 1);
    if ~isempty(ridx)
        % meteorproc vx is meridional (positive south), vy is zonal (positive east)
        fit_u = res.vy(ridx);       % east
        fit_v = -res.vx(ridx);      % north (flip sign)
        fit_mag = hypot(fit_u, fit_v);
        fit_ang = atan2(fit_u, fit_v); % angle from north, clockwise after axes settings
        polarplot([fit_ang, fit_ang], [0, fit_mag], 'r-', 'LineWidth', 2);
        legend({'LOS vectors', 'Beam azimuths', 'Fitted (u east, v north)'}, 'Location', 'best');
        fitTitle = sprintf('Hour %02d LOS (black), beams (blue), fit (red) u=%.2f v=%.2f', ...
            hr_plot, fit_u, fit_v);
    else
        legend({'LOS vectors', 'Beam azimuths'}, 'Location', 'best');
        fitTitle = sprintf('Hour %02d LOS vectors (no fit found)', hr_plot);
    end
    pax = gca;
    pax.ThetaZeroLocation = 'top';
    pax.ThetaDir = 'clockwise';
    title(fitTitle);
end

end
