function meteorwindnc_convert(inputRoot, outputRoot, fitacfRoot)
%METEORWINDNC_CONVERT Adjust legacy meteor wind NetCDF files in-place.
%
%   METEORWINDNC_CONVERT()
%       Processes every *.nc file under ~/data/superdarn/meteorwindnc/,
%       writing converted files to the same tree rooted at
%       ~/data/superdarn/meteorwindnc_converted/.
%
%   METEORWINDNC_CONVERT(INPUTROOT, OUTPUTROOT, FITACFROOT)
%       Reads daily files from INPUTROOT and writes annual, per-radar files
%       under OUTPUTROOT/{radar}/. Each output NetCDF file holds every hour
%       for every day of the year in a 24 x 365 (or 366) grid with NaNs
%       where no observations are present. During conversion:
%           * The "hour" coordinate is shifted by +0.5.
%           * "Vx" is renamed to "v" (long_name="meriodional wind",
%             units="(m/s)").
%           * "Vy" is renamed to "u" (long_name="zonal wind",
%             units="(m/s)") and the data are negated.
%           * "sdev_Vx" -> "sdev_v" (long_name="meridional wind error").
%           * "sdev_Vy" -> "sdev_u" (long_name="zonal wind error").
%           * Hourly median transmit frequency ("tfreq") is computed from
%             the fitACF NetCDF files and stored alongside the winds.
%           * "lat" and "long" variables are removed.
%           * All other variables are preserved when they can be mapped to
%             the hour grid.

if nargin < 1 || isempty(inputRoot)
    inputRoot = '~/data/superdarn/meteorwindnc/';
end
if nargin < 2 || isempty(outputRoot)
    outputRoot = '~/data/superdarn/meteorwindnc_converted/';
end
if nargin < 3
    fitacfRoot = '~/data/superdarn/netcdf/';
end
inputRoot = expanduser(inputRoot);
outputRoot = expanduser(outputRoot);
if isempty(fitacfRoot)
    fitacfRoot = '';
else
    fitacfRoot = expanduser(fitacfRoot);
end

files = dir(fullfile(inputRoot, '**', '*.nc'));
if isempty(files)
    fprintf('No NetCDF files found under %s\n', inputRoot);
    return;
end

srcFiles = cell(numel(files), 1);
for k = 1:numel(files)
    srcFiles{k} = fullfile(files(k).folder, files(k).name);
end

dailyResults = cell(numel(srcFiles), 1);
% Process daily files in parallel when the Parallel Computing Toolbox is available.
useParallel = ~isempty(ver('parallel'));
maxWorkers = 8;
if useParallel
    pool = gcp('nocreate');
    if isempty(pool)
        try
            localCluster = parcluster('local');
            desiredWorkers = min(localCluster.NumWorkers, maxWorkers);
            if desiredWorkers < 1
                warning('Local cluster reports zero workers; falling back to serial processing.');
                useParallel = false;
            else
                parpool(localCluster, desiredWorkers);
            end
        catch ME
            warning('Failed to start parallel pool (%s). Falling back to serial processing.', ME.message);
            useParallel = false;
        end
    else
        if pool.NumWorkers > maxWorkers
            warning('Existing parallel pool has %d workers; recreating with limit of %d.', ...
                pool.NumWorkers, maxWorkers);
            delete(pool);
            try
                localCluster = parcluster('local');
                desiredWorkers = min(localCluster.NumWorkers, maxWorkers);
                if desiredWorkers < 1
                    warning('Local cluster reports zero workers; falling back to serial processing.');
                    useParallel = false;
                else
                    parpool(localCluster, desiredWorkers);
                end
            catch ME
                warning('Failed to resize parallel pool (%s). Falling back to serial processing.', ME.message);
                useParallel = false;
            end
        end
    end
end

if useParallel
    parfor k = 1:numel(srcFiles)
        dailyResults{k} = process_daily_file(srcFiles{k}, fitacfRoot);
    end
else
    for k = 1:numel(srcFiles)
        dailyResults{k} = process_daily_file(srcFiles{k}, fitacfRoot);
    end
end

groupList = struct('radar', {}, 'year', {}, 'numDays', {}, 'hourValues', {}, ...
    'dayValues', {}, 'varData', {}, 'varAttrs', {}, 'varOrder', {}, ...
    'sourceFiles', {}, 'fileCount', {});
groupIndex = containers.Map('KeyType', 'char', 'ValueType', 'double');

for k = 1:numel(dailyResults)
    daily = dailyResults{k};
    if isempty(daily) || ~daily.success
        if ~isempty(daily) && ~isempty(daily.error)
            warning('Skipping %s (%s)', daily.sourceFile, daily.error);
        end
        continue;
    end

    key = lower(sprintf('%s_%04d', daily.radar, daily.year));
    if ~isKey(groupIndex, key)
        idx = numel(groupList) + 1;
        groupIndex(key) = idx;
        groupList(idx) = init_group(daily.radar, daily.year);
    else
        idx = groupIndex(key);
    end

    group = groupList(idx);
    group = ingest_daily_file(group, daily);
    groupList(idx) = group;
end

if isempty(groupList)
    fprintf('No annual groups were created from %s\n', inputRoot);
    return;
end

for idx = 1:numel(groupList)
    group = groupList(idx);
    if group.fileCount == 0
        continue;
    end
    dstDir = fullfile(outputRoot, group.radar);
    if ~exist(dstDir, 'dir')
        mkdir(dstDir);
    end
    dstFile = fullfile(dstDir, sprintf('%s_%04d.nc', group.radar, group.year));
    fprintf('Writing %s from %d files\n', dstFile, group.fileCount);
    try
        write_group_file(group, dstFile);
    catch ME
        warning('Failed to write %s (%s)', dstFile, ME.message);
    end
end
end

function meta = parse_file_metadata(srcFile)
[~, baseName, ~] = fileparts(srcFile);
parts = strsplit(baseName, '.');
if numel(parts) < 2
    error('Filename must be DATE.RADAR.nc (got %s)', baseName);
end
dateToken = parts{1};
radar = lower(parts{2});
if numel(dateToken) < 9
    error('Unrecognized date token in %s', baseName);
end
year = str2double(dateToken(1:4));
monthToken = dateToken(5:7);
dayToken = dateToken(8:end);
monthNum = month_from_token(monthToken);
dayNum = str2double(dayToken);
if isnan(year) || isnan(dayNum)
    error('Invalid date components in %s', baseName);
end
dn = datenum(year, monthNum, dayNum);
dayOfYear = round(dn - datenum(year, 1, 0));
meta = struct('srcFile', srcFile, 'radar', radar, 'year', year, ...
    'month', monthNum, 'day', dayNum, 'dayOfYear', dayOfYear, ...
    'datenum', dn);
end

function group = init_group(radar, year)
numDays = days_in_year(year);
group = struct();
group.radar = lower(radar);
group.year = year;
group.numDays = numDays;
group.hourValues = ((0:23)' + 0.5);
group.dayValues = 1:numDays;
group.varData = struct();
group.varAttrs = struct();
group.varOrder = {};
group.sourceFiles = {};
group.fileCount = 0;
end

function daily = process_daily_file(srcFile, fitacfRoot)
daily = struct('success', false, 'error', '', 'sourceFile', srcFile, ...
    'radar', '', 'year', NaN, 'dayIndex', NaN, 'hourIdx', [], ...
    'validMask', [], 'variables', struct('name', {}, 'attributes', {}, ...
    'values', {}), 'tfreqHourly', []);
try
    meta = parse_file_metadata(srcFile);
    daily.radar = meta.radar;
    daily.year = meta.year;
    daily.dayIndex = meta.dayOfYear;

    info = ncinfo(srcFile);
    hourValues = ncread(srcFile, 'hour');
    hourIdx = hour_indices_from_values(hourValues, 24);
    validMask = ~isnan(hourIdx);

    daily.hourIdx = hourIdx;
    daily.validMask = validMask;

    varEntries = struct('name', {}, 'attributes', {}, 'values', {});
    for v = 1:numel(info.Variables)
        var = info.Variables(v);
        if should_skip_variable(var.Name)
            continue;
        end
        if numel(var.Dimensions) ~= 1 || var.Dimensions(1).Length ~= numel(hourIdx)
            continue;
        end

        data = ncread(srcFile, var.Name);
        data = reshape(data, [], 1);
        if numel(data) ~= numel(hourIdx)
            continue;
        end

        newName = map_variable_name(var.Name);
        data = double(transform_variable_data(var.Name, data));
        fillIdx = find(strcmp({var.Attributes.Name}, '_FillValue'), 1);
        if ~isempty(fillIdx)
            fillVal = double(var.Attributes(fillIdx).Value);
            data(data == fillVal) = NaN;
        end

        entry = struct('name', newName, 'attributes', var.Attributes, ...
            'values', data);
        varEntries(end+1) = entry; %#ok<AGROW>
    end
    daily.variables = varEntries;

    daily.tfreqHourly = compute_hourly_tfreq(meta, fitacfRoot, 24);
    daily.success = true;
catch ME
    daily.error = ME.message;
end
end

function group = ingest_daily_file(group, daily)
dayIndex = daily.dayIndex;
if dayIndex < 1 || dayIndex > group.numDays
    error('Day-of-year %d is outside valid range for %d', dayIndex, group.year);
end

hourIdx = daily.hourIdx;
validMask = daily.validMask;
if isempty(hourIdx) || isempty(validMask) || ~any(validMask)
    warning('No valid hours found in %s', daily.sourceFile);
    return;
end

for v = 1:numel(daily.variables)
    varEntry = daily.variables(v);
    newName = varEntry.name;
    data = varEntry.values;

    if ~isfield(group.varData, newName)
        group.varData.(newName) = nan(numel(group.hourValues), group.numDays);
        group.varAttrs.(newName) = varEntry.attributes;
        group.varOrder{end+1} = newName; %#ok<AGROW>
    end

    arr = group.varData.(newName);
    arr(hourIdx(validMask), dayIndex) = data(validMask);
    group.varData.(newName) = arr;
end

group.fileCount = group.fileCount + 1;
group.sourceFiles{end+1} = daily.sourceFile;

tfreqHourly = daily.tfreqHourly;
if ~isempty(tfreqHourly)
    varName = 'tfreq';
    if ~isfield(group.varData, varName)
        unitsAttr = struct('Name', 'units', 'Value', 'kHz');
        longAttr = struct('Name', 'long_name', 'Value', 'Median transmit frequency');
        group.varData.(varName) = nan(numel(group.hourValues), group.numDays);
        group.varAttrs.(varName) = [unitsAttr, longAttr];
        group.varOrder{end+1} = varName; %#ok<AGROW>
    end
    arr = group.varData.(varName);
    arr(:, dayIndex) = tfreqHourly;
    group.varData.(varName) = arr;
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
    if isfield(group.varAttrs, name)
        attrs = group.varAttrs.(name);
    else
        attrs = struct('Name', {}, 'Value', {});
    end
    copy_attributes(ncid, varid, attrs, name);
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
netcdf.putAtt(ncid, ncGlobal, 'history', sprintf('%s: aggregated by meteorwindnc_convert', datestr(now, 31)));

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

function tf = should_skip_variable(varName)
tf = any(strcmpi(varName, {'hour', 'lat', 'lon', 'long', 'latitude', 'longitude'}));
end

function newName = map_variable_name(name)
switch name
    case 'Vx'
        newName = 'v';
    case 'Vy'
        newName = 'u';
    case 'sdev_Vx'
        newName = 'sdev_v';
    case 'sdev_Vy'
        newName = 'sdev_u';
    otherwise
        newName = name;
end
end

function data = transform_variable_data(name, data)
switch name
    case 'Vy'
        data = -data;
    otherwise
        % no-op
end
end

function dayCount = days_in_year(year)
if (mod(year, 4) == 0 && mod(year, 100) ~= 0) || mod(year, 400) == 0
    dayCount = 366;
else
    dayCount = 365;
end
end

function monthNum = month_from_token(token)
months = {'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', ...
    'Sep', 'Oct', 'Nov', 'Dec'};
idx = find(strcmpi(token, months), 1);
if isempty(idx)
    error('Invalid month token "%s"', token);
end
monthNum = idx;
end

function idx = hour_indices_from_values(values, hourCount)
values = double(values(:));
idx = floor(values) + 1;
invalid = isnan(values) | values < 0 | values >= hourCount;
idx(invalid) = NaN;
end

function tfreqHourly = compute_hourly_tfreq(meta, fitacfRoot, hourCount)
if hourCount <= 0 || isempty(fitacfRoot) || ~exist(fitacfRoot, 'dir')
    tfreqHourly = [];
    return;
end

fitFile = find_fitacf_file(meta, fitacfRoot);
if isempty(fitFile)
    tfreqHourly = [];
    return;
end

try
    tfreqVals = double(ncread(fitFile, 'tfreq'));
    mjdVals = double(ncread(fitFile, 'mjd'));
catch ME
    warning('Failed to read tfreq from %s (%s)', fitFile, ME.message);
    tfreqHourly = [];
    return;
end

if isempty(tfreqVals) || isempty(mjdVals)
    tfreqHourly = [];
    return;
end

mjdVals = mjdVals(:);
tfreqVals = tfreqVals(:);
targetMJD = floor(meta.datenum - datenum(1858, 11, 17));
sameDay = floor(mjdVals) == targetMJD;
if ~any(sameDay)
    tfreqHourly = [];
    return;
end

mjdVals = mjdVals(sameDay);
tfreqVals = tfreqVals(sameDay);
fracDay = mjdVals - targetMJD;
hourIdx = floor(fracDay * 24) + 1;
valid = hourIdx >= 1 & hourIdx <= hourCount & ~isnan(tfreqVals);
hourIdx = hourIdx(valid);
tfreqVals = tfreqVals(valid);
if isempty(hourIdx)
    tfreqHourly = [];
    return;
end

tfreqHourly = nan(hourCount, 1);
for h = 1:hourCount
    vals = tfreqVals(hourIdx == h);
    if ~isempty(vals)
        tfreqHourly(h) = median(vals, 'omitnan');
    end
end
end

function fitFile = find_fitacf_file(meta, fitacfRoot)
fitFile = '';
if isempty(fitacfRoot) || ~exist(fitacfRoot, 'dir')
    return;
end

yearDir = fullfile(fitacfRoot, sprintf('%04d', meta.year));
if ~exist(yearDir, 'dir')
    return;
end

patterns = {
    fullfile(yearDir, sprintf('%02d', meta.month));
    yearDir
    };

dateStr = sprintf('%04d%02d%02d', meta.year, meta.month, meta.day);
for i = 1:numel(patterns)
    baseDir = patterns{i};
    if ~exist(baseDir, 'dir')
        continue;
    end
    searchPattern = fullfile(baseDir, sprintf('%s.%s*.nc', dateStr, meta.radar));
    listing = dir(searchPattern);
    if ~isempty(listing)
        [~, idx] = max([listing.datenum]);
        fitFile = fullfile(listing(idx).folder, listing(idx).name);
        return;
    end
end
end

function copy_attributes(ncid, varid, attributes, varName)
for a = 1:numel(attributes)
    attr = attributes(a);
    if strcmp(attr.Name, '_FillValue')
        continue; % already applied through netcdf.defVarFill
    end
    netcdf.putAtt(ncid, varid, attr.Name, attr.Value);
end

switch varName
    case 'v'
        netcdf.putAtt(ncid, varid, 'long_name', 'meriodional wind');
        netcdf.putAtt(ncid, varid, 'units', '(m/s)');
    case 'u'
        netcdf.putAtt(ncid, varid, 'long_name', 'zonal wind');
        netcdf.putAtt(ncid, varid, 'units', '(m/s)');
    case 'sdev_v'
        netcdf.putAtt(ncid, varid, 'long_name', 'meridional wind error');
        netcdf.putAtt(ncid, varid, 'units', '(m/s)');
    case 'sdev_u'
        netcdf.putAtt(ncid, varid, 'long_name', 'zonal wind error');
        netcdf.putAtt(ncid, varid, 'units', '(m/s)');
    case 'tfreq'
        netcdf.putAtt(ncid, varid, 'long_name', 'Median transmit frequency');
        netcdf.putAtt(ncid, varid, 'units', 'kHz');
end
end

function pathStr = expanduser(pathStr)
if startsWith(pathStr, '~')
    pathStr = fullfile(getenv('HOME'), pathStr(2:end));
end
pathStr = char(pathStr);
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
