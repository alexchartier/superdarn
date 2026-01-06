function [results, debug] = meteorproc(records, site, varargin)
%METEORPROC Estimate horizontal meteor winds from SuperDARN-style data.
%
%   RESULTS = METEORPROC(RECORDS, SITE) replicates the behaviour of the
%   legacy C implementation meteorproc.c. RECORDS must be a struct array
%   describing the meteor scatter found in one or more CFIT files. Each
%   RECORD must contain at least the fields
%       time    - seconds since 1970-01-01 00:00:00 UTC
%       scan    - scan flag (discarded if negative)
%       frang   - first range gate (km)
%       rsep    - range separation (km)
%       rxrise  - receiver rise time (microseconds)
%       bmnum   - beam number (0-based)
%       num     - number of echoes stored in DATA and RNG
%       rng     - vector of range gate indices for each meteor (0-based)
%       data    - struct array with fields v, p_l, v_e, w_l
%
%   SITE is a structure describing the radar hardware. The required fields
%   are bmsep, boresite, maxbeam, geolat and recrise. If the NETCDF
%   file provides explicit beam headings (e.g., the brng_at_15deg_el
%   attribute), include them in SITE.beam_azimuths_rad (radians, indexed by
%   beam number + 1) to force METEORPROC to use those azimuths instead of
%   deriving them from bmsep/boresite.
%
%   [...] = METEORPROC(..., 'Name', Value, ...) customises the processing.
%   Supported options:
%       'MaxVelocity'    Maximum allowed |v| (default 100 m/s)
%       'MinSN'          Minimum spectral SNR (default 3)
%       'MaxVelocityErr' Maximum velocity error (default 50 m/s)
%       'MaxLineWidth'   Maximum line width (default 25 m/s)
%       'MaxRange'       Highest range gate considered (default 405 km)
%       'MinBeams'       Minimum number of beams with >=2 echoes (default 5)
%       'BeamType'       'meridional' or 'zonal' (controls labelling only)
%       'RequestedHour'  Restrict processing to a specific UT hour (0-23)
%       'PositionFunction' Function handle used to emulate RPosGeo. It must
%                        accept (sct, beam, coord, site, frang_val,
%                        rsep_val, rxrise_val, meteor_height) and return
%                        [rho, lat, lon]. When omitted the location fields
%                        are reported as NaN.
%       'SourceName'     Text included in the header to identify the data
% 
%   The returned RESULTS is a table with one row per processed hour:
%       year, month, day, hour, num_avgs, frang, rsep, vx, vy, lat, lon,
%       sdev_vx, sdev_vy
%
%   When requested, a second output DEBUG is a struct containing per-hour
%   raw vectors used in the fit (azimuth, vlos, sdev):
%       DEBUG.hour   - vector of hours that were fit
%       DEBUG.azimuth{hi} - beam azimuths (rad) used for hour DEBUG.hour(hi)
%       DEBUG.vlos{hi}    - corresponding LOS velocities (m/s)
%       DEBUG.sdev{hi}    - LOS standard deviations (m/s)
%
%   NOTE:
%   -----
%   This MATLAB translation intentionally mirrors the flow of meteorproc.c.
%   It does not implement the CFIT I/O or RPosGeo helpers; they must be
%   provided by the caller. See the documentation and comments for details.

if ~isstruct(records)
    error('meteorproc:RecordsType', 'records must be a struct array.');
end
if ~isscalar(site) || ~isstruct(site)
    error('meteorproc:SiteType', 'site must be a scalar struct.');
end
requiredSiteFields = {'bmsep','boresite','maxbeam','geolat','recrise'};
missing = setdiff(requiredSiteFields, fieldnames(site));
if ~isempty(missing)
    error('meteorproc:SiteFields', ...
        'site struct is missing required fields: %s', strjoin(missing, ', '));
end
if isfield(site,'beam_azimuths_rad')
    if numel(site.beam_azimuths_rad) < site.maxbeam
        error('meteorproc:SiteAzimuths', ...
            'beam_azimuths_rad must have at least maxbeam elements.');
    end
end

parser = inputParser;
parser.FunctionName = 'meteorproc';
parser.addParameter('MaxVelocity', 100.0, @(x) isscalar(x) && x > 0);
parser.addParameter('MinSN', 3.0, @(x) isscalar(x) && x > 0);
parser.addParameter('MaxVelocityErr', 50.0, @(x) isscalar(x) && x > 0);
parser.addParameter('MaxLineWidth', 25.0, @(x) isscalar(x) && x > 0);
parser.addParameter('MaxRange', 405, @(x) isscalar(x) && x > 0);
parser.addParameter('MinBeams', 5, @(x) isscalar(x) && x >= 1);
parser.addParameter('BeamType', 'meridional', @(s) ischar(s) || isstring(s));
parser.addParameter('RequestedHour', [], @(x) isempty(x) || (isscalar(x) && x >= 0 && x <= 23));
parser.addParameter('PositionFunction', [], @(f) isempty(f) || isa(f, 'function_handle'));
parser.addParameter('SourceName', "", @(s) ischar(s) || isstring(s));
parser.addParameter('VerboseFits', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opt = parser.Results;
verboseFits = logical(opt.VerboseFits);

bmType = lower(string(opt.BeamType));
if ~(bmType == "meridional" || bmType == "zonal")
    error('meteorproc:InvalidBeamType', 'BeamType must be ''meridional'' or ''zonal''.');
end

METEOR_HEIGHT = 95; % km
mxbm = site.maxbeam;

num = zeros(24, 1);
met = cell(24, 1);
frang = [];
rsep = [];
rxrise = [];
timeVec = [records.time];
dt = datetime(timeVec, 'ConvertFrom', 'posixtime', 'TimeZone', 'UTC');
dv_all = datevec(dt);
yrVec = dv_all(:, 1);
moVec = dv_all(:, 2);
dyVec = dv_all(:, 3);
hrVec = dv_all(:, 4);
mtVec = dv_all(:, 5);
scVec = dv_all(:, 6);

for idx = 1:numel(records)
    rec = records(idx);
    if isempty(frang)
        frang = rec.frang;
        rsep = rec.rsep;
        rxrise = rec.rxrise;
        if rxrise == 0
            rxrise = site.recrise;
        end
    end

    yr = yrVec(idx);
    mo = moVec(idx);
    dy = dyVec(idx);
    hr = hrVec(idx);
    mt = mtVec(idx);
    sc = scVec(idx);

    if ~isempty(opt.RequestedHour) && hr ~= opt.RequestedHour
        continue;
    end
    if rec.scan < 0 || rec.frang == 0 || rec.rsep == 0
        continue;
    end

    hourIdx = hr + 1;
    entry = struct( ...
        'yr', yr, 'mo', mo, 'dy', dy, 'hr', hr, 'mt', mt, 'sc', sc, ...
        'bmnum', rec.bmnum, 'frang', rec.frang, 'rsep', rec.rsep, ...
        'rxrise', rec.rxrise, 'max_gate', 0, 'flg', [], 'vlos', []);

    entry.rxrise = entry.rxrise + (entry.rxrise == 0) * site.recrise;
    entry.max_gate = floor((opt.MaxRange - rec.frang) / rec.rsep);
    if entry.max_gate <= 0
        continue;
    end

    entry.flg = false(entry.max_gate, 1);
    entry.vlos = zeros(entry.max_gate, 1);

    for jj = 1:rec.num
        gate = rec.rng(jj) + 1;
        if gate > entry.max_gate
            continue;
        end
        echo = rec.data(jj);
        if isfield(echo, 'gflg') && ~isempty(echo.gflg) && echo.gflg == 1
            continue; % drop ground scatter echoes
        end
        if abs(echo.v) > opt.MaxVelocity
            continue;
        end
        if echo.p_l < opt.MinSN
            continue;
        end
        if echo.v_e >= opt.MaxVelocityErr
            continue;
        end
        if echo.w_l > opt.MaxLineWidth
            continue;
        end
        entry.flg(gate) = true;
        entry.vlos(gate) = echo.v;
    end

    cnt = num(hourIdx);
    if isempty(met{hourIdx})
        met{hourIdx} = entry;
    else
        met{hourIdx}(cnt + 1) = entry; %#ok<AGROW>
    end
    num(hourIdx) = cnt + 1;
end

if isempty(frang)
    warning('meteorproc:NoData', 'No valid records were ingested.');
    results = table();
    return;
end

coseps = calcCoseps(opt.MaxRange / 2.0, METEOR_HEIGHT);
if verboseFits
    fprintf('# Vlos(max)=%.2f\n# S/N(min)=%.2f\n# range(max)=%d\n', ...
        opt.MaxVelocity, opt.MinSN, opt.MaxRange);
    fprintf('# Verr(max)=%.2f\n# num_beams(min)=%d\n', ...
        opt.MaxVelocityErr, opt.MinBeams);
    fprintf('# w_l(max)=%.2f\n', opt.MaxLineWidth);
    srcStr = strtrim(string(opt.SourceName));
    if strlength(srcStr) > 0
        fprintf('# source=%s\n', srcStr);
    else
        fprintf('# source=unknown\n');
    end
    fprintf('# year month day hour num_avgs Vx(v) Vy(u)\n');
end

rows = cell(0, 13);
hour_log = [];
az_log = {};
vlos_log = {};
sdev_log = {};

hrRange = 0:23;
if ~isempty(opt.RequestedHour)
    hrRange = opt.RequestedHour;
end
printedHeader = false;

for hr = hrRange
    hourIdx = hr + 1;
    cnt = num(hourIdx);
    if cnt == 0
        continue;
    end

    entries = met{hourIdx};
    year = entries(1).yr;
    month = entries(1).mo;
    day = entries(1).dy;

    bm_total = zeros(mxbm, 1);
    bm_count = zeros(mxbm, 1);
    bm_sdtmp = zeros(mxbm, 1);

    num_avgs = 0;
    for ii = 1:cnt
        entry = entries(ii);
        beamIdx = entry.bmnum + 1;
        for jj = 1:entry.max_gate
            if ~entry.flg(jj)
                continue;
            end
            bm_total(beamIdx) = bm_total(beamIdx) + entry.vlos(jj);
            bm_count(beamIdx) = bm_count(beamIdx) + 1;
            num_avgs = num_avgs + 1;
        end
    end

    vlos = zeros(mxbm, 1);
    for ii = 1:mxbm
        if bm_count(ii) > 0
            vlos(ii) = bm_total(ii) / bm_count(ii);
        end
    end

    for ii = 1:cnt
        entry = entries(ii);
        beamIdx = entry.bmnum + 1;
        for jj = 1:entry.max_gate
            if ~entry.flg(jj)
                continue;
            end
            diff = entry.vlos(jj) - vlos(beamIdx);
            bm_sdtmp(beamIdx) = bm_sdtmp(beamIdx) + diff * diff;
        end
    end

    sdev = ones(mxbm, 1);
    for ii = 1:mxbm
        if bm_count(ii) > 1
            sdev(ii) = sqrt(bm_sdtmp(ii) / (bm_count(ii) - 1));
        else
            vlos(ii) = 0;
        end
    end

    beamsUsed = sum(bm_count > 1);
    if beamsUsed < opt.MinBeams
        warning('meteorproc:NotEnoughBeams', ...
            'Hour %02d skipped: only %d beams with >=2 echoes.', hr, beamsUsed);
        continue;
    end

    validIdx = find(bm_count > 1);
    bc = numel(validIdx);
    azimuth = zeros(bc, 1);
    y = zeros(bc, 1);
    sig = zeros(bc, 1);

    for kk = 1:bc
        beamNum = validIdx(kk) - 1;
        azimuth(kk) = calcAzi(beamNum, site);
        y(kk) = vlos(validIdx(kk)) / coseps;
        sig(kk) = sdev(validIdx(kk));
    end

    if verboseFits
    if verboseFits
        fprintf('Fitting %d of %d beams\n', bc, mxbm);
    end
    end

    design = [-cos(azimuth), sin(azimuth)];
    weights = 1 ./ max(sig.^2, eps);
    normal = design' * (design .* weights);
    rhs = design' * (weights .* y);

    if rcond(normal) < eps
        coeffs = pinv(normal) * rhs;
    else
        coeffs = normal \ rhs;
    end
    vx = coeffs(1);
    vy = coeffs(2);
    residuals = ((design * coeffs) - y) .* sqrt(weights);
    chisq = sum(residuals .^ 2); %#ok<NASGU>

    cvm = pinv(normal);
    sdvx = sqrt(max(cvm(1, 1), 0));
    sdvy = sqrt(max(cvm(2, 2), 0));

    frang = entries(1).frang;
    rsep = entries(1).rsep;
    rxrise_val = entries(1).rxrise;

    if isempty(opt.PositionFunction)
        lat = NaN;
        lon = NaN;
    else
        [~, lat, lon] = opt.PositionFunction(0, 7, 3, site, frang, rsep, rxrise_val, METEOR_HEIGHT);
    end

    if ~printedHeader && ~verboseFits
        fprintf('year month day hour num_avgs Vx(v) Vy(u)\n');
        printedHeader = true;
    end
    fprintf('%4d %02d %02d %02d %d %.2f %.2f\n', ...
        year, month, day, hr, num_avgs, vx, vy);

    rows = [rows; {year, month, day, hr, num_avgs, frang, rsep, vx, vy, lat, lon, sdvx, sdvy}]; %#ok<AGROW>
    hour_log(end+1, 1) = hr; %#ok<AGROW>
    az_log{end+1, 1} = azimuth; %#ok<AGROW>
    vlos_log{end+1, 1} = y .* coseps; %#ok<AGROW>
    sdev_log{end+1, 1} = sig; %#ok<AGROW>
end

results = cell2table(rows, 'VariableNames', ...
    {'year', 'month', 'day', 'hour', 'num_avgs', 'frang', 'rsep', ...
     'vx', 'vy', 'lat', 'lon', 'sdev_vx', 'sdev_vy'});

if nargout > 1
    debug = struct();
    debug.hour = hour_log;
    debug.azimuth = az_log;
    debug.vlos = vlos_log;
    debug.sdev = sdev_log;
end

end

function [yr, mo, dy, hr, mt, sc] = epochToDate(epoch)
dv = datevec(epoch/86400 + datenum(1970,1,1));
yr = dv(:, 1);
mo = dv(:, 2);
dy = dv(:, 3);
hr = dv(:, 4);
mt = dv(:, 5);
sc = dv(:, 6);
end

function value = calcCoseps(range, height)
if range <= height
    range = height + 1e-6;
end
epsAng = asin(height ./ range);
value = cos(epsAng);
end

function angle = calcAzi(bmnum, site)
if ~isfield(site,'beam_azimuths_rad') || numel(site.beam_azimuths_rad) < bmnum + 1
    error('meteorproc:MissingAzimuths', ...
        'Explicit beam azimuths are required; site.beam_azimuths_rad missing or too short.');
end
angle = site.beam_azimuths_rad(bmnum + 1);
end
