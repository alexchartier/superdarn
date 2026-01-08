function aggregate_winds_annual(yearIn, radarCode, inputPattern, annualRoot)
%AGGREGATE_WINDS_ANNUAL Build annual winds NetCDF(s) from daily .winds.nc files.
%   AGGREGATE_WINDS_ANNUAL(YEAR, RADARCODE, INPUTPATTERN, ANNUALROOT) scans the
%   daily SuperDARN winds files for the specified YEAR/RADARCODE and writes an
%   annual grid NetCDF under ANNUALROOT. Defaults mirror meteorproc_ml_batch
%   outputs and work on macOS or Linux paths without extra arguments:
%       aggregate_winds_annual(2019, 'mcm')
%
%   If RADARCODE is empty or omitted, the function discovers all radar codes
%   present under the input directory for that year and processes each one.
%
%   Missing days are left NaN; only existing daily files are included.
%
%   Inputs:
%       YEAR          - Calendar year to aggregate (scalar, required)
%       RADARCODE     - 3-letter radar code (default: '', meaning all found)
%       INPUTPATTERN  - Daily winds path pattern (filename.m tokens)
%                       Default macOS:  ~/data/superdarn/fit_nc_3_winds/{yyyy}/{mm}/{yyyymmdd}.{NAME}.winds.nc
%                       Default Linux: /project/superdarn/data/fit_nc_3_winds/{yyyy}/{mm}/{yyyymmdd}.{NAME}.winds.nc
%       ANNUALROOT    - Output root for annual files (default mirrors meteorproc_ml_batch)

if nargin < 1 || isempty(yearIn)
    error('aggregate_winds_annual:MissingYear', 'YEAR is required.');
end
if nargin < 2
    radarCode = '';
end

if ismac
    defaultInputPattern = '~/data/superdarn/fit_nc_3_winds/{yyyy}/{mm}/{yyyymmdd}.{NAME}*.winds.nc';
    defaultAnnualRoot = '/Users/chartat1/data/superdarn/fit_nc_3_winds/annual';
else
    defaultInputPattern = '/project/superdarn/data/fit_nc_3_winds/{yyyy}/{mm}/{yyyymmdd}.{NAME}*.winds.nc';
    defaultAnnualRoot = '/project/superdarn/data/fit_nc_3_winds/annual';
end
if nargin < 3 || isempty(inputPattern)
    inputPattern = defaultInputPattern;
end
if nargin < 4 || isempty(annualRoot)
    annualRoot = defaultAnnualRoot;
end

yr = yearSafe(yearIn);
if ~isscalar(yr) || isnan(yr)
    error('aggregate_winds_annual:BadYear', 'YEAR must be a scalar year.');
end

radarList = string(radarCode);
if strlength(radarCode) == 0
    % Discover all radars present under the input directory for this year.
    samplePath = expandPath(filename(inputPattern, datenum(yr, 1, 1), 'tmp'));
    baseDir = fileparts(samplePath);
    baseDir = strrep(baseDir, 'tmp', '');
    yearDir = fileparts(baseDir);
    listing = dir(fullfile(yearDir, '**', sprintf('%04d*.winds.nc', yr)));
    radarList = strings(0, 1);
    for li = 1:numel(listing)
        tok = regexp(listing(li).name, '\\d{8}\\.([A-Za-z]{3})\\.winds', 'tokens', 'once');
        if ~isempty(tok)
            radarList(end+1, 1) = lower(string(tok{1})); %#ok<AGROW>
        end
    end
    radarList = unique(radarList);
    if isempty(radarList)
        warning('aggregate_winds_annual:NoRadarsFound', ...
            'No daily winds files found for %d under %s.', yr, yearDir);
        return;
    end
end

fprintf('[aggregate_winds_annual] Year: %d, Radars: %s\n', yr, strjoin(radarList, ', '));
fprintf('[aggregate_winds_annual] Input pattern : %s\n', char(inputPattern));
fprintf('[aggregate_winds_annual] Annual root   : %s\n', char(annualRoot));

timeVec = datenum(yr, 1, 1):datenum(yr, 12, 31);
annualMap = containers.Map('KeyType', 'char', 'ValueType', 'any');
filesSeen = 0;

for rk = 1:numel(radarList)
    rc = radarList(rk);
    for t = timeVec
        patternPath = expandPath(filename(inputPattern, t, rc));
        matches = {};
        if contains(patternPath, '*')
            listing = dir(patternPath);
            for li = 1:numel(listing)
                if listing(li).isdir
                    continue;
                end
                matches{end+1} = fullfile(listing(li).folder, listing(li).name); %#ok<AGROW>
            end
        else
            if exist(patternPath, 'file') == 2
                matches = {patternPath};
            end
        end
        if isempty(matches)
            continue;
        end
        matches = select_preferred_matches(matches);
        for mi = 1:numel(matches)
            fn = matches{mi};
            try
                data = load_nc(fn);
            catch ME
                warning('aggregate_winds_annual:LoadFail', 'Failed to load %s (%s)', fn, ME.message);
                continue;
            end
            hours = data.hour(:);
            if isempty(hours)
                continue;
            end
            results = table;
            results.year = repmat(yearSafe(datetime(t, 'ConvertFrom', 'datenum')), numel(hours), 1);
            results.month = repmat(month(datetime(t, 'ConvertFrom', 'datenum')), numel(hours), 1);
            results.day = repmat(day(datetime(t, 'ConvertFrom', 'datenum')), numel(hours), 1);
            results.hour = hours;
            flds = {'num_avgs','frang','rsep','u','v','sdev_u','sdev_v','Peak','FWHM','tfreq','lat','lon','vx','vy','sdev_vx','sdev_vy'};
            for i = 1:numel(flds)
                f = flds{i};
                if isfield(data, f)
                    results.(f) = data.(f)(:);
                end
            end
            site = struct();
            site.code = lower(string(rc));
            site.geolat = attributeValue(ncinfo(fn).Attributes, 'radar_latitude', NaN);
            site.geolon = attributeValue(ncinfo(fn).Attributes, 'radar_longitude', NaN);
            annualMap = updateAnnual(annualMap, results, site, t, fn);
            filesSeen = filesSeen + 1;
        end
    end
end

if filesSeen == 0
    fprintf('[aggregate_winds_annual] No daily files found; nothing to write.\n');
else
    flushAnnual(annualMap, yr, annualRoot);
end
end

%%
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
    group.lat = site.geolat;
    group.lon = site.geolon;
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
        if group.year == yearToFlush && group.fileCount == 0
            fprintf('[aggregate_winds_annual] Skipping %s_%04d (no files accumulated)\n', group.radar, group.year);
        end
        continue;
    end
    annualRootExpanded = char(expandPath(annualRoot));
    if ~exist(annualRootExpanded, 'dir')
        mkdir(annualRootExpanded);
    end
    dstDir = fullfile(annualRootExpanded, sprintf('%04d', group.year));
    if ~exist(dstDir, 'dir')
        mkdir(dstDir);
    end
    dstFile = fullfile(dstDir, sprintf('%s_%04d.nc', group.radar, group.year));
    fprintf('Writing annual %s (files: %d)\n', dstFile, group.fileCount);
    write_group_file(group, dstFile);
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
netcdf.putAtt(ncid, ncGlobal, 'radar_latitude', group.lat);
netcdf.putAtt(ncid, ncGlobal, 'radar_longitude', group.lon);
if ~isempty(group.sourceFiles)
    netcdf.putAtt(ncid, ncGlobal, 'first_source_file', group.sourceFiles{1});
end
netcdf.putAtt(ncid, ncGlobal, 'history', sprintf('%s: aggregated by aggregate_winds_annual', datestr(now, 31)));

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

function preferred = select_preferred_matches(matches)
% Prefer base file (e.g., mcm) over qualifiers (mcm.a, mcm.b, ...).
prefMap = containers.Map('KeyType', 'char', 'ValueType', 'char');
rankMap = containers.Map('KeyType', 'char', 'ValueType', 'double');
for i = 1:numel(matches)
    filePath = matches{i};
    [radar, qual] = parse_radar_and_quality(filePath);
    if strlength(radar) == 0
        continue;
    end
    rnk = quality_rank(qual);
    key = char(radar);
    if ~isKey(rankMap, key) || rnk < rankMap(key)
        rankMap(key) = rnk;
        prefMap(key) = filePath;
    end
end
radars = prefMap.keys;
radars = sort(radars);
preferred = cell(numel(radars), 1);
for i = 1:numel(radars)
    preferred{i} = prefMap(radars{i});
end
if isempty(preferred)
    preferred = matches;
end
end

function [radar, qual] = parse_radar_and_quality(path)
[~, base, ~] = fileparts(path);
m = regexp(base, '\\.(?<radar>[A-Za-z]{3})(?:\\.(?<qual>[A-Za-z0-9]+))?\\.winds$', 'names');
if isempty(m)
    radar = "";
    qual = "";
    return;
end
radar = lower(string(m.radar));
if isfield(m, 'qual') && ~isempty(m.qual)
    qual = lower(string(m.qual));
else
    qual = "";
end
end

function rnk = quality_rank(qual)
if strlength(qual) == 0
    rnk = 0;
    return;
end
q = char(qual);
rnk = 1 + double(lower(q(1)));
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
    case 'Peak'
        attrs.long_name = 'Meteor model Gaussian peak height';
        attrs.units = 'km';
    case 'FWHM'
        attrs.long_name = 'Meteor model Gaussian full width at half maximum';
        attrs.units = 'km';
    case 'tfreq'
        attrs.long_name = 'Transmit frequency (median, per hour)';
        attrs.units = 'MHz';
    case 'num_avgs'
        attrs.long_name = 'Number of vlos samples included in averages';
        attrs.units = 'count';
    case 'frang'
        attrs.long_name = 'First range gate';
        attrs.units = 'km';
    case 'rsep'
        attrs.long_name = 'Range separation';
        attrs.units = 'km';
    case 'sdev_vx'
        attrs.long_name = 'Uncertainty of Vx';
        attrs.units = 'm/s';
    case 'sdev_vy'
        attrs.long_name = 'Uncertainty of Vy';
        attrs.units = 'm/s';
    case 'vx'
        attrs.long_name = 'Meridional wind component (positive southward)';
        attrs.units = 'm/s';
    case 'vy'
        attrs.long_name = 'Zonal wind component (positive eastward)';
        attrs.units = 'm/s';
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
% mirror meteorproc_ml_batch: no sign flip here
switch name
    otherwise
        % no-op
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

function dayCount = days_in_year(year)
if (mod(year, 4) == 0 && mod(year, 100) ~= 0) || mod(year, 400) == 0
    dayCount = 366;
else
    dayCount = 365;
end
end

function yrs = yearSafe(val)
if isnumeric(val)
    if isscalar(val) && val >= 1000 && val < 10000
        % Treat plain numeric (e.g., 2019) as a calendar year, not a datenum.
        yrs = val;
    else
        dv = datevec(val);
        yrs = dv(:, 1);
    end
elseif isdatetime(val)
    yrs = year(val);
else
    yrs = NaN;
end
end
