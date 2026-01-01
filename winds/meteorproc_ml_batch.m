function meteorproc_ml_batch(inputPattern, startDate, endDate, varargin)
%METEORPROC_ML_BATCH Run meteorproc, append ML peak/FWHM, and emit daily/annual NetCDFs.
%
%   meteorproc_ml_batch(INPUTPATTERN, STARTDATE, ENDDATE) expands
%   INPUTPATTERN (filename.m-style tokens) for each day in the range,
%   runs METEORPROC on the meteor NetCDF, uses the trained ML model to
%   compute Gaussian peak height and FWHM, writes a daily NetCDF, and
%   aggregates annual per-radar outputs with legacy variable naming.
%
%   Name/Value options:
%       'OutputPattern'  - Output path pattern (default: append ".winds.nc")
%       'AnnualRoot'     - Root/template for annual outputs (default: OutputPattern root)
%       'MakeAnnual'     - Toggle annual aggregation (default: true)
%       'AnglesFile'     - Path to meteor angle NetCDF (default: ~/data/meteor_winds/angles_2008.nc)
%       'MemFile'        - Path to meteor environment model NetCDF (default: ~/data/meteor_winds/mem_3_output_v1.nc)
%       'MLModelFile'    - Path to trained ML model .mat (default: ~/data/meteor_winds/ml_model.mat)
%       'SWFile'         - Path to solar wind CSV (default: ~/data/indices/SW-All.csv)
%       'RadarFreqMHz'   - Observing frequency in MHz for peak adjustment (default: 30)
%       Additional args are passed to METEORPROC_FROM_NETCDF.
%
%   This script depends on filename.m being on the MATLAB path.

if exist('filename', 'file') ~= 2
    error('meteorproc_ml_batch:FilenameFunc', ...
        'filename.m must be on the MATLAB path (e.g., addpath utils/filename.m).');
end
if nargin < 3
    error('meteorproc_ml_batch:Inputs', ...
        'Usage: meteorproc_ml_batch(inputPattern, startDate, endDate, ...)');
end

parser = inputParser;
parser.FunctionName = 'meteorproc_ml_batch';
parser.KeepUnmatched = true;
parser.addParameter('OutputPattern', string(inputPattern) + ".winds.nc", @(s) ischar(s) || isstring(s));
parser.addParameter('AnnualRoot', "", @(s) ischar(s) || isstring(s));
parser.addParameter('MakeAnnual', true, @(x) islogical(x) || isnumeric(x));
parser.addParameter('AnglesFile', '~/data/meteor_winds/angles_2008.nc', @(s) ischar(s) || isstring(s));
parser.addParameter('MemFile', '~/data/meteor_winds/mem_3_output_v1.nc', @(s) ischar(s) || isstring(s));
parser.addParameter('MLModelFile', '~/data/meteor_winds/ml_model.mat', @(s) ischar(s) || isstring(s));
parser.addParameter('SWFile', '~/data/indices/SW-All.csv', @(s) ischar(s) || isstring(s));
parser.addParameter('RadarFreqMHz', [], @(x) (isnumeric(x) && isscalar(x) && x > 0) || isempty(x));
parser.parse(varargin{:});
opts = parser.Results;
passArgs = structToNameValue(parser.Unmatched);

outputPattern = string(opts.OutputPattern);
annualRoot = string(opts.AnnualRoot);
makeAnnual = logical(opts.MakeAnnual);
if isempty(opts.RadarFreqMHz)
    error('meteorproc_ml_batch:MissingRadarFreq', ...
        'Specify radar observing frequency via ''RadarFreqMHz'', no default applied.');
end
radarFreq = double(opts.RadarFreqMHz);

support = load_ml_support(opts);

timeVec = expandDatenum(startDate, endDate);
if isempty(timeVec)
    warning('meteorproc_ml_batch:EmptyRange', 'No days found within the requested span.');
    return;
end

annualMap = containers.Map('KeyType', 'char', 'ValueType', 'any');
for idx = 1:numel(timeVec)
    t = timeVec(idx);
    inFile = expandPath(filename(char(inputPattern), t, [], filesep));
    if isempty(inFile) || exist(inFile, 'file') ~= 2
        warning('meteorproc_ml_batch:MissingInput', 'Skipping %s (file not found).', inFile);
        continue;
    end
    outFile = expandPath(filename(char(outputPattern), t, [], filesep));
    fprintf('Processing %s -> %s\n', inFile, outFile);

    try
        [results, site] = run_meteorproc_with_site(inFile, passArgs{:});
    catch ME
        warning('meteorproc_ml_batch:MeteorprocFailed', '%s failed (%s)', inFile, ME.message);
        continue;
    end
    if isempty(results)
        warning('meteorproc_ml_batch:EmptyResults', 'No valid winds for %s.', inFile);
        continue;
    end

    % Compute ML peak/FWHM for the full day and attach to the table.
    try
        [peakVals, fwhmVals] = compute_ml_profile(results, site, t, support, radarFreq);
        results.Peak = map_hour_values(results.hour, peakVals);
        results.FWHM = map_hour_values(results.hour, fwhmVals);
    catch ME
        warning('meteorproc_ml_batch:MLModelFailed', 'ML model failed for %s (%s)', inFile, ME.message);
        results.Peak = nan(height(results), 1);
        results.FWHM = nan(height(results), 1);
    end

    writeResultsNetCDF(outFile, results, inFile);

    if makeAnnual
        try
            annualMap = updateAnnual(annualMap, results, site, t, inFile);
            % Flush when crossing a year boundary or at the end.
            nextYear = [];
            if idx < numel(timeVec)
                nextYear = year(datetime(timeVec(idx + 1), 'ConvertFrom', 'datenum'));
            end
            thisYear = year(datetime(t, 'ConvertFrom', 'datenum'));
            if isempty(nextYear) || nextYear ~= thisYear
                root = annualRoot;
                if strlength(root) == 0
                    % Use output pattern root by stripping filename portion.
                    [rootDir, ~, ~] = fileparts(outFile);
                    root = rootDir;
                end
                flushAnnual(annualMap, thisYear, root);
            end
        catch ME
            warning('meteorproc_ml_batch:AnnualFailed', 'Annual aggregation failed for %s (%s)', inFile, ME.message);
        end
    end
end
end

function [results, site] = run_meteorproc_with_site(ncfile, varargin)
% Wrap meteorproc_from_netcdf to also return the site metadata.
parser = inputParser;
parser.KeepUnmatched = true;
parser.addParameter('RadarCode', inferCode(ncfile));
parser.addParameter('Site', struct());
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

function [peakVals, fwhmVals] = compute_ml_profile(results, site, datenumDay, support, radarFreq)
% Build a full-day time grid, interpolate MEM, and run the ML model.
hrs = (0:23).';
Times = repmat(datenum(datetime(datevec(datenumDay)) + hours(hrs)), 1, 2); % 24 x 2 to satisfy interp_mem
mem_int = interp_mem(support.mem, support.mem_fields, Times, site.geolat, site.geolon);
[peakGrid, fwhmGrid] = run_ml_model(support.Mdl, Times, site.geolat, site.geolon, ...
    mem_int, support.sw, support.meteor_angles, radarFreq);
% Use first column (hours) for output.
peakVals = peakGrid(:, 1);
fwhmVals = fwhmGrid(:, 1);
end

function vals = map_hour_values(hours, dailyVector)
vals = nan(size(hours));
for i = 1:numel(hours)
    h = hours(i);
    if h >= 0 && h <= 23 && h == floor(h)
        vals(i) = dailyVector(h + 1);
    end
end
end

function support = load_ml_support(opts)
support.sw = readtable(expandPath(opts.SWFile));
support.meteor_angles = load_nc(expandPath(opts.AnglesFile));
support.mem = load_mem(expandPath(opts.MemFile));
support.mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};
mdlStruct = load(expandPath(opts.MLModelFile));
flds = fieldnames(mdlStruct);
if ismember('Mdl', flds)
    support.Mdl = mdlStruct.Mdl;
else
    support.Mdl = mdlStruct.(flds{1});
end
end

function annualMap = updateAnnual(annualMap, results, site, datenumDay, sourceFile)
% Aggregate daily results into annual per-radar maps.
if ~istable(results) || height(results) == 0
    return;
end
radar = lower(string(site.code));
dv = datevec(datenumDay);
yr = dv(1);
dayOfYear = day(datetime(datenumDay, 'ConvertFrom', 'datenum'), 'dayofyear');
key = sprintf('%s_%04d', radar, yr);

if ~isKey(annualMap, key)
    group.radar = radar;
    group.year = yr;
    group.numDays = days_in_year(yr);
    group.hourValues = ((0:23)' + 0.5);
    group.dayValues = 1:group.numDays;
    group.varData = struct();
    group.varAttrs = struct();
    group.varOrder = {};
    group.sourceFiles = {};
    group.fileCount = 0;
    annualMap(key) = group;
end
group = annualMap(key);

hourIdx = floor(results.hour) + 1;
validHour = hourIdx >= 1 & hourIdx <= 24;
hourIdx = hourIdx(validHour);
vars = results.Properties.VariableNames;
exclude = {'hour', 'lat', 'lon', 'long', 'latitude', 'longitude'};
for vi = 1:numel(vars)
    name = vars{vi};
    if any(strcmpi(name, exclude))
        continue;
    end
    values = results.(name);
    values = transform_variable_data(name, values);
    values = values(validHour);
    targetName = map_variable_name(name);
    if ~isfield(group.varData, targetName)
        group.varData.(targetName) = nan(24, group.numDays);
        group.varAttrs.(targetName) = variableMetadata(targetName);
        group.varOrder{end+1} = targetName; %#ok<AGROW>
    end
    arr = group.varData.(targetName);
    arr(hourIdx, dayOfYear) = double(values(:));
    group.varData.(targetName) = arr;
end
group.fileCount = group.fileCount + 1;
group.sourceFiles{end+1} = sourceFile;
annualMap(key) = group;
end

function flushAnnual(annualMap, yearToFlush, annualRoot)
keys = annualMap.keys;
for i = 1:numel(keys)
    key = keys{i};
    group = annualMap(key);
    if group.year ~= yearToFlush || group.fileCount == 0
        continue;
    end
    dstDir = fullfile(expandPath(annualRoot), char(group.radar));
    if ~exist(dstDir, 'dir')
        mkdir(dstDir);
    end
    dstFile = fullfile(dstDir, sprintf('%s_%04d.nc', group.radar, group.year));
    fprintf('Writing annual %s\n', dstFile);
    write_group_file(group, dstFile);
    remove(annualMap, key);
end
end

function path = expandPath(rawPath)
if isempty(rawPath)
    path = '';
    return;
end
if size(rawPath, 1) > 1
    rawPath = rawPath(1, :);
end
path = strtrim(rawPath);
if startsWith(path, "~")
    path = fullfile(getenv('HOME'), path(2:end));
end
path = strrep(path, '\', filesep);
path = strrep(path, '//', '/');
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

function vec = expandDatenum(startDate, endDate)
startNum = toDatenum(startDate);
endNum = toDatenum(endDate);
if isnan(startNum) || isnan(endNum)
    vec = [];
    return;
end
if endNum < startNum
    [startNum, endNum] = deal(endNum, startNum);
end
vec = startNum:endNum;
end

function num = toDatenum(val)
if isdatetime(val)
    num = datenum(val);
elseif isnumeric(val)
    if isscalar(val)
        num = val;
    elseif numel(val) >= 3
        num = datenum(val(1), val(2), val(3));
    else
        num = NaN;
    end
else
    num = NaN;
end
end

function writeResultsNetCDF(outFile, results, sourceFile)
if isempty(results)
    return;
end
outDir = fileparts(outFile);
if ~isempty(outDir) && ~exist(outDir, 'dir')
    mkdir(outDir);
end
if exist(outFile, 'file')
    delete(outFile);
end

recordDim = {'record', height(results)};
varNames = results.Properties.VariableNames;
for i = 1:numel(varNames)
    data = results.(varNames{i});
    if iscell(data)
        error('meteorproc_ml_batch:UnsupportedType', ...
            'Variable %s is not numeric; cannot write to NetCDF.', varNames{i});
    end
    nccreate(outFile, varNames{i}, 'Dimensions', recordDim, ...
        'Datatype', class(data));
    ncwrite(outFile, varNames{i}, data);
    attrs = variableMetadata(varNames{i});
    attrNames = fieldnames(attrs);
    for a = 1:numel(attrNames)
        ncwriteatt(outFile, varNames{i}, attrNames{a}, attrs.(attrNames{a}));
    end
end
ncwriteatt(outFile, '/', 'description', 'Hourly meteor winds with ML peak/FWHM');
ncwriteatt(outFile, '/', 'generated', datestr(now, 'yyyy-mm-ddTHH:MM:SS'));
if nargin >= 3 && ~isempty(sourceFile)
    ncwriteatt(outFile, '/', 'source', sourceFile);
end
end

function attrs = variableMetadata(name)
attrs = struct();
switch name
    case 'year'
        attrs.long_name = 'Calendar year';
        attrs.units = 'year';
    case 'month'
        attrs.long_name = 'Month of year';
        attrs.units = 'month';
    case 'day'
        attrs.long_name = 'Day of month';
        attrs.units = 'day';
    case 'hour'
        attrs.long_name = 'Hour (UT)';
        attrs.units = 'hour';
    case 'num_avgs'
        attrs.long_name = 'Number of vlos samples included in averages';
        attrs.units = 'count';
    case 'frang'
        attrs.long_name = 'First range gate';
        attrs.units = 'km';
    case 'rsep'
        attrs.long_name = 'Range separation';
        attrs.units = 'km';
    case 'vx'
        attrs.long_name = 'Meridional wind component (positive southward)';
        attrs.units = 'm/s';
    case 'vy'
        attrs.long_name = 'Zonal wind component (positive eastward)';
        attrs.units = 'm/s';
    case 'vm'
        attrs.long_name = 'Line-of-sight velocity on vm beam';
        attrs.units = 'm/s';
    case 'vm_lat'
        attrs.long_name = 'Latitude of vm beam intersection';
        attrs.units = 'deg';
    case 'vm_lon'
        attrs.long_name = 'Longitude of vm beam intersection';
        attrs.units = 'deg';
    case 'lat'
        attrs.long_name = 'Geographic latitude of fit';
        attrs.units = 'deg';
    case 'lon'
        attrs.long_name = 'Geographic longitude of fit';
        attrs.units = 'deg';
    case 'sdev_vx'
        attrs.long_name = 'Uncertainty of Vx';
        attrs.units = 'm/s';
    case 'sdev_vy'
        attrs.long_name = 'Uncertainty of Vy';
        attrs.units = 'm/s';
    case 'Peak'
        attrs.long_name = 'Meteor model Gaussian peak height';
        attrs.units = 'km';
    case 'FWHM'
        attrs.long_name = 'Meteor model Gaussian full width at half maximum';
        attrs.units = 'km';
    case 'v'
        attrs.long_name = 'meridional wind';
        attrs.units = '(m/s)';
    case 'u'
        attrs.long_name = 'zonal wind';
        attrs.units = '(m/s)';
    case 'sdev_v'
        attrs.long_name = 'meridional wind error';
        attrs.units = '(m/s)';
    case 'sdev_u'
        attrs.long_name = 'zonal wind error';
        attrs.units = '(m/s)';
end
end

function newName = map_variable_name(name)
switch name
    case 'vx'
        newName = 'v';
    case 'Vx'
        newName = 'v';
    case 'vy'
        newName = 'u';
    case 'Vy'
        newName = 'u';
    case 'sdev_vx'
        newName = 'sdev_v';
    case 'sdev_Vx'
        newName = 'sdev_v';
    case 'sdev_vy'
        newName = 'sdev_u';
    case 'sdev_Vy'
        newName = 'sdev_u';
    otherwise
        newName = name;
end
end

function values = transform_variable_data(name, values)
switch name
    case {'Vy', 'vy'}
        values = -values;
    otherwise
        % no-op
end
end

function write_group_file(group, dstFile)
tmpFile = [dstFile, '.tmp'];
delete_if_exists(tmpFile);

ncid = netcdf.create(tmpFile, 'NETCDF4');
cleanup = onCleanup(@() safeClose(ncid));

dimHour = netcdf.defDim(ncid, 'hour', numel(group.hourValues));
dimDay = netcdf.defDim(ncid, 'day_of_year', group.numDays);

hourVarId = netcdf.defVar(ncid, 'hour', netcdf.getConstant('NC_DOUBLE'), dimHour);
netcdf.putAtt(ncid, hourVarId, 'long_name', 'hour of day (centered)');
netcdf.putAtt(ncid, hourVarId, 'units', 'hours');

dayVarId = netcdf.defVar(ncid, 'day_of_year', netcdf.getConstant('NC_INT'), dimDay);
netcdf.putAtt(ncid, dayVarId, 'long_name', 'day of year');
netcdf.putAtt(ncid, dayVarId, 'units', 'day');

nanFill = NaN;
varIds = struct();
for i = 1:numel(group.varOrder)
    name = group.varOrder{i};
    varid = netcdf.defVar(ncid, name, netcdf.getConstant('NC_DOUBLE'), [dimHour, dimDay]);
    netcdf.defVarFill(ncid, varid, false, nanFill);
    attrs = group.varAttrs.(name);
    attrNames = fieldnames(attrs);
    for a = 1:numel(attrNames)
        netcdf.putAtt(ncid, varid, attrNames{a}, attrs.(attrNames{a}));
    end
    varIds.(name) = varid;
end

ncGlobal = netcdf.getConstant('NC_GLOBAL');
netcdf.putAtt(ncid, ncGlobal, 'title', 'Annual meteor wind grid (24 x 365/366)');
netcdf.putAtt(ncid, ncGlobal, 'radar', group.radar);
netcdf.putAtt(ncid, ncGlobal, 'year', group.year);
netcdf.putAtt(ncid, ncGlobal, 'days_in_year', group.numDays);
netcdf.putAtt(ncid, ncGlobal, 'source_file_count', group.fileCount);
if ~isempty(group.sourceFiles)
    netcdf.putAtt(ncid, ncGlobal, 'first_source_file', group.sourceFiles{1});
end
netcdf.putAtt(ncid, ncGlobal, 'history', sprintf('%s: aggregated by meteorproc_ml_batch', datestr(now, 31)));

netcdf.endDef(ncid);

netcdf.putVar(ncid, hourVarId, group.hourValues);
netcdf.putVar(ncid, dayVarId, int32(group.dayValues));
for i = 1:numel(group.varOrder)
    name = group.varOrder{i};
    netcdf.putVar(ncid, varIds.(name), group.varData.(name));
end

netcdf.close(ncid);
delete(cleanup);
delete_if_exists(dstFile);
movefile(tmpFile, dstFile, 'f');
end

function delete_if_exists(filename)
if exist(filename, 'file')
    delete(filename);
end
end

function safeClose(ncid)
if ~isempty(ncid)
    try
        netcdf.close(ncid);
    catch
    end
end
end

function data = load_nc(ncfile)
info = ncinfo(ncfile);
data = struct();
for v = 1:numel(info.Variables)
    name = info.Variables(v).Name;
    data.(name) = ncread(ncfile, name);
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

% ---- Minimal copies from meteorproc_from_netcdf to access site/records ----
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
    error('meteorproc_ml_batch:RangeResolution', ...
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
    error('meteorproc_ml_batch:MissingAttribute', ...
        'NetCDF file is missing bmsep or boresight attributes.');
end
if isnan(geolat) || isnan(geolon)
    warning('meteorproc_ml_batch:MissingLatLon', ...
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

function dayCount = days_in_year(year)
if (mod(year, 4) == 0 && mod(year, 100) ~= 0) || mod(year, 400) == 0
    dayCount = 366;
else
    dayCount = 365;
end
end
