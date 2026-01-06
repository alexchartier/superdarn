function aggregate_daily_to_annual(inputPattern, startDate, endDate, annualRoot, radarCode)
% aggregate_daily_to_annual Aggregate daily .winds.nc files into annual grids.
%   aggregate_daily_to_annual(INPUTPATTERN, STARTDATE, ENDDATE, ANNUALROOT, RADARCODE)
%   INPUTPATTERN supports filename.m tokens, e.g.
%     '/Users/chartat1/data/superdarn/fit_nc_3_winds/{yyyy}/{mm}/{yyyymmdd}.{NAME}.winds.nc'
%   STARTDATE/ENDDATE are datenums (inclusive). ANNUALROOT is the output root.
%   RADARCODE fills {NAME} if present in the pattern (default 'fir').

if nargin < 1 || isempty(inputPattern)
    inputPattern = '/Users/chartat1/data/superdarn/fit_nc_3_winds/{yyyy}/{mm}/{yyyymmdd}.{NAME}.winds.nc';
end
if nargin < 2 || isempty(startDate)
    error('aggregate_daily_to_annual:MissingStart', 'startDate is required');
end
if nargin < 3 || isempty(endDate)
    endDate = startDate;
end
if nargin < 4 || isempty(annualRoot)
    annualRoot = '/Users/chartat1/data/superdarn/fit_nc_3_winds/annual';
end
if nargin < 5 || isempty(radarCode)
    radarCode = 'fir';
end

timeVec = expandDatenum(startDate, endDate);
if isempty(timeVec)
    warning('aggregate_daily_to_annual:EmptyRange', 'No days found within the requested span.');
    return;
end

annualMap = containers.Map('KeyType', 'char', 'ValueType', 'any');
for t = timeVec
    fn = expandPath(filename(inputPattern, t, radarCode));
    if exist(fn, 'file') ~= 2
        fprintf('Missing %s\n', fn);
        continue;
    end
    try
        data = load_nc(fn);
    catch ME
        warning('aggregate_daily_to_annual:LoadFail', 'Failed to load %s (%s)', fn, ME.message);
        continue;
    end

    hours = data.hour(:);
    if isempty(hours)
        continue;
    end
    yr = yearSafe(datetime(t, 'ConvertFrom', 'datenum'));
    dayOfYear = day(datetime(t, 'ConvertFrom', 'datenum'), 'dayofyear');

    % Build results table from available vars
    results = table;
    results.year = repmat(yr, numel(hours), 1);
    results.month = repmat(month(datetime(t, 'ConvertFrom', 'datenum')), numel(hours), 1);
    results.day = repmat(day(datetime(t, 'ConvertFrom', 'datenum')), numel(hours), 1);
    results.hour = hours;

    if isfield(data, 'num_avgs'), results.num_avgs = data.num_avgs(:); end
    if isfield(data, 'frang'), results.frang = data.frang(:); end
    if isfield(data, 'rsep'), results.rsep = data.rsep(:); end
    if isfield(data, 'vx'), results.vx = data.vx(:); end
    if isfield(data, 'vy'), results.vy = data.vy(:); end
    if isfield(data, 'lat'), results.lat = data.lat(:); end
    if isfield(data, 'lon'), results.lon = data.lon(:); end
    if isfield(data, 'sdev_vx'), results.sdev_vx = data.sdev_vx(:); end
    if isfield(data, 'sdev_vy'), results.sdev_vy = data.sdev_vy(:); end
    if isfield(data, 'Peak'), results.Peak = data.Peak(:); end
    if isfield(data, 'FWHM'), results.FWHM = data.FWHM(:); end
    if isfield(data, 'tfreq'), results.tfreq = data.tfreq(:); end

    site = struct();
    site.code = lower(string(radarCode));
    site.geolat = attributeValue(ncinfo(fn).Attributes, 'radar_latitude', NaN);
    site.geolon = attributeValue(ncinfo(fn).Attributes, 'radar_longitude', NaN);

    annualMap = updateAnnualStandalone(annualMap, results, site, t, fn);
end

% Flush all accumulated years
keys = annualMap.keys;
for i = 1:numel(keys)
    group = annualMap(keys{i});
    flushAnnualStandalone(struct(keys{i}, group), group.year, annualRoot);
end
end

function annualMap = updateAnnualStandalone(annualMap, results, site, datenumDay, sourceFile)
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
exclude = {'hour', 'lat', 'lon', 'long', 'latitude', 'longitude', 'year', 'month', 'day'};
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

function flushAnnualStandalone(annualMap, yearToFlush, annualRoot)
keys = fieldnames(annualMap);
for i = 1:numel(keys)
    group = annualMap.(keys{i});
    if group.year ~= yearToFlush || group.fileCount == 0
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
    fprintf('Writing annual %s\n', dstFile);
    write_group_file_standalone(group, dstFile);
end
end

function write_group_file_standalone(group, dstFile)
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
netcdf.putAtt(ncid, ncGlobal, 'history', sprintf('%s: aggregated by aggregate_daily_to_annual', datestr(now, 31)));

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

function attrs = variableMetadata(name)
attrs = struct();
switch name
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
    dv = datevec(val);
    yrs = dv(:, 1);
elseif isdatetime(val)
    yrs = year(val);
else
    yrs = NaN;
end
end
