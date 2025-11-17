function results = meteorproc_from_netcdf(ncfile, varargin)
%METEORPROC_FROM_NETCDF Run meteor wind fitting on a NetCDF meteor catalog.
%
%   RESULTS = METEORPROC_FROM_NETCDF(NCFILE) reads the SuperDARN NetCDF file
%   referenced by NCFILE (e.g., ~/data/.../20190113.fir.v2.5.nc), rebuilds
%   CFIT-style beam records, and invokes METEORPROC to produce the hourly
%   vector winds. Radar metadata (latitude, boresite, beam headings, range
%   spacing, etc.) are read directly from the NetCDF global attributes such
%   as brng_at_15deg_el, so no external hardware tables are required. The
%   helper accepts several Name/Value pairs:
%
%       'RadarCode'     - 3-letter SuperDARN radar code (default inferred
%                         from NCFILE)
%       'Site'          - Struct overriding the metadata derived from the
%                         NetCDF file. Must contain the fields required by
%                         METEORPROC.
%
%   Any additional Name/Value pairs are forwarded to METEORPROC so that you
%   can override filtering thresholds (MaxVelocity, RequestedHour, etc.).

parser = inputParser;
parser.FunctionName = 'meteorproc_from_netcdf';
parser.KeepUnmatched = true;
parser.addParameter('RadarCode', inferCode(ncfile), @(s) ischar(s) || isstring(s));
parser.addParameter('Site', struct(), @(s) isstruct(s) || isempty(s));
parser.parse(varargin{:});
opts = parser.Results;

fileData = readMeteorNetCDF(ncfile);

if isempty(fieldnames(opts.Site))
    site = buildSiteFromAttributes(ncfile, fileData, opts.RadarCode);
else
    site = opts.Site;
end

records = buildMeteorRecords(fileData, site);

meteorArgs = structToNameValue(parser.Unmatched);
meteorArgs = [meteorArgs, {'SourceName', char(ncfile)}];
results = meteorproc(records, site, meteorArgs{:});

end

function data = readMeteorNetCDF(ncfile)
ncfile = char(ncfile);
data.mjd = double(ncread(ncfile, 'mjd'));
data.beam = double(ncread(ncfile, 'beam'));
data.range = double(ncread(ncfile, 'range'));
data.v = double(ncread(ncfile, 'v'));
data.p_l = double(ncread(ncfile, 'p_l'));
data.v_e = double(ncread(ncfile, 'v_e'));
data.epoch = (data.mjd - 40587.0) * 86400.0;
data.timeKey = round(data.epoch * 1000); % milliseconds
uniqueRange = unique(data.range);
if numel(uniqueRange) < 2
    error('meteorproc_from_netcdf:RangeResolution', ...
        'Unable to determine range separation from NetCDF file.');
end
data.frang = uniqueRange(1);
data.rsep = uniqueRange(2) - uniqueRange(1);
data.gate = int32(round((data.range - data.frang) ./ data.rsep));
data.numPoints = numel(data.mjd);
end

function records = buildMeteorRecords(data, site)
combo = [data.timeKey(:), data.beam(:)];
[~, ~, grpIdx] = unique(combo, 'rows', 'stable');
counts = accumarray(grpIdx, 1);
[~, sortOrder] = sort(grpIdx);

template = struct('time', 0, 'scan', 0, ...
    'bmnum', 0, 'frang', data.frang, 'rsep', data.rsep, ...
    'rxrise', site.recrise, 'num', 0, 'rng', [], 'data', []);
records = repmat(template, numel(counts), 1);

idxStart = 1;
for g = 1:numel(counts)
    len = counts(g);
    grpIndices = sortOrder(idxStart:idxStart + len - 1);
    idxStart = idxStart + len;

    ranges = data.gate(grpIndices);
    vel = data.v(grpIndices);
    snr = data.p_l(grpIndices);
    verr = data.v_e(grpIndices);
    beam = data.beam(grpIndices(1));

    rec = template;
    rec.time = data.epoch(grpIndices(1));
    rec.bmnum = beam;
    rec.num = len;
    rec.rng = ranges(:);
    rec.data = struct( ...
        'v', num2cell(vel(:)), ...
        'p_l', num2cell(snr(:)), ...
        'v_e', num2cell(verr(:)), ...
        'w_l', num2cell(zeros(len, 1)));

    records(g) = rec;
end
records = reshape(records, 1, []);
end

function site = buildSiteFromAttributes(ncfile, data, radarCode)
info = ncinfo(ncfile);
attrs = info.Attributes;
attr = @(name, default) attributeValue(attrs, name, default);

bmsep = attr('bmsep', NaN);
boresite = attr('boresight', NaN);
geolat = attr('lat', NaN);
geolon = attr('lon', NaN);
alt = attr('alt', 0);
beamList = attr('beams', []);
beamAzDeg = attr('brng_at_15deg_el', []);

if isnan(bmsep) || isnan(boresite)
    error('meteorproc_from_netcdf:MissingAttribute', ...
        'NetCDF file is missing bmsep or boresight attributes.');
end
if isnan(geolat) || isnan(geolon)
    warning('meteorproc_from_netcdf:MissingLatLon', ...
        'lat/lon attributes not found; using 0 for geographic position.');
    geolat = 0;
    geolon = 0;
end

if isempty(beamList)
    beamList = unique(data.beam(:))';
end

site = struct();
site.code = lower(string(radarCode));
site.bmsep = double(bmsep);
site.boresite = double(boresite);
site.maxbeam = numel(beamList);
site.geolat = double(geolat);
site.geolon = double(geolon);
site.alt = double(alt);
site.recrise = 0;

if ~isempty(beamAzDeg)
    site.beam_azimuths_rad = deg2rad(double(beamAzDeg(:)));
end
end

function val = attributeValue(attrs, name, default)
idx = find(strcmpi({attrs.Name}, name), 1);
if isempty(idx)
    val = default;
else
    val = attrs(idx).Value;
end
end

function args = structToNameValue(s)
if isempty(fieldnames(s))
    args = {};
    return;
end
names = fieldnames(s);
values = struct2cell(s);
args = reshape([names.'; values.'], 1, []);
end

function code = inferCode(ncfile)
[~, name, ~] = fileparts(ncfile);
parts = split(name, '.');
if numel(parts) >= 2
    code = parts{2};
else
    code = "fir";
end
end

function radians = deg2rad(degrees)
radians = degrees .* (pi / 180);
end
