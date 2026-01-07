function meteorproc_ml_batch(inputPattern, startDate, endDate, varargin)
%METEORPROC_ML_BATCH Run meteorproc, append ML peak/FWHM, and emit daily/annual NetCDFs.
%
%   meteorproc_ml_batch(INPUTPATTERN, STARTDATE, ENDDATE) expands
%   INPUTPATTERN (filename.m-style tokens) for each day in the range,
%   runs METEORPROC on the meteor NetCDF, uses the trained ML model to
%   compute Gaussian peak height and FWHM, writes a daily NetCDF, and
%   aggregates annual per-radar outputs with legacy variable naming.
%   For a full-year rebuild from existing daily files, run aggregate_winds_annual.m.
%
%   Name/Value options (platform defaults below):
%       'OutputPattern'  - Output path pattern (default: platform-specific, supports *)
%       'AnnualRoot'     - Root/template for annual outputs (default: platform-specific)
%       'MakeAnnual'     - Toggle annual aggregation (default: true)
%       'AnglesFile'     - Path to meteor angle NetCDF (default: platform-specific)
%       'MemFile'        - Path to meteor environment model NetCDF (default: platform-specific)
%       'MLModelFile'    - Path to trained ML model .mat (default: platform-specific)
%       'SWFile'         - Path to solar wind CSV (default: platform-specific)
%       'FilterGroundScatter' - Toggle removal of ground scatter (gflg==1) before processing (default: true)
%       Radar frequency is derived from the input NetCDF tfreq variable
%       (per-hour median, converted to MHz). No default/override is applied.
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

if ismac
    defaultInputPattern = '/Users/chartat1/data/superdarn/fit_nc_3/{yyyy}/{mm}/{yyyymmdd}*.nc';
    defaultOutputPattern = '/Users/chartat1/data/superdarn/fit_nc_3_winds/{yyyy}/{mm}/{yyyymmdd}*.winds.nc';
    defaultAnnualRoot = '/Users/chartat1/data/superdarn/fit_nc_3_winds/annual';
    defaultAngles = '/Users/chartat1/data/meteor_winds/angles_2008.nc';
    defaultMem = '/Users/chartat1/data/meteor_winds/mem_3_output_v1.nc';
    defaultML = '/Users/chartat1/data/meteor_winds/ml_model.mat';
    defaultSW = '/Users/chartat1/data/indices/SW-All.csv';
else
    defaultInputPattern = '/project/superdarn/data/fit_nc_3/{yyyy}/{mm}/{yyyymmdd}*.nc';
    defaultOutputPattern = '/project/superdarn/data/fit_nc_3_winds/{yyyy}/{mm}/{yyyymmdd}*.winds.nc';
    defaultAnnualRoot = '/project/superdarn/data/fit_nc_3_winds/annual';
    defaultAngles = '/project/superdarn/data/meteorwind_ancillary/angles_2008.nc';
    defaultMem = '/project/superdarn/data/meteorwind_ancillary/mem_3_output_v1.nc';
    defaultML = '/project/superdarn/data/meteorwind_ancillary/ml_model.mat';
    defaultSW = '/project/superdarn/data/meteorwind_ancillary/SW-All.csv';
end

if nargin < 1 || isempty(inputPattern)
    inputPattern = defaultInputPattern;
end

parser = inputParser;
parser.FunctionName = 'meteorproc_ml_batch';
parser.KeepUnmatched = true;

parser.addParameter('OutputPattern', string(inputPattern) + ".winds.nc", @(s) ischar(s) || isstring(s));
parser.addParameter('AnnualRoot', defaultAnnualRoot, @(s) ischar(s) || isstring(s));
parser.addParameter('MakeAnnual', true, @(x) islogical(x) || isnumeric(x));
parser.addParameter('AnglesFile', defaultAngles, @(s) ischar(s) || isstring(s));
parser.addParameter('MemFile', defaultMem, @(s) ischar(s) || isstring(s));
parser.addParameter('MLModelFile', defaultML, @(s) ischar(s) || isstring(s));
parser.addParameter('SWFile', defaultSW, @(s) ischar(s) || isstring(s));
parser.addParameter('FilterGroundScatter', true, @(x) islogical(x) || isnumeric(x));
parser.addParameter('UseParallel', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('MaxWorkers', 4, @(x) isempty(x) || (isscalar(x) && isnumeric(x) && x >= 1));
parser.parse(varargin{:});
opts = parser.Results;
passArgs = structToNameValue(parser.Unmatched);
filterGroundScatter = logical(opts.FilterGroundScatter);

outputPattern = string(opts.OutputPattern);
annualRoot = string(opts.AnnualRoot);
makeAnnual = logical(opts.MakeAnnual);
hasParallel = ~isempty(ver('parallel'));
capRequested = [];
if ~isempty(opts.MaxWorkers)
    capRequested = floor(double(opts.MaxWorkers));
end
maxWorkersAvailable = 1;
clusterObj = [];
clusterType = "processes";
if hasParallel
    % Prefer threads to avoid per-worker MATLAB processes.
    try
        clusterObj = parcluster('threads');
        clusterType = "threads";
        maxWorkersAvailable = max(1, clusterObj.NumWorkers);
    catch
        clusterObj = parcluster('local');
        maxWorkersAvailable = max(1, clusterObj.NumWorkers - 4);
        clusterType = "processes";
    end
end
if isempty(capRequested)
    capWorkers = min(maxWorkersAvailable, 4); % default cap to keep memory down
else
    capWorkers = min(maxWorkersAvailable, capRequested);
end

if isempty(opts.UseParallel)
    useParallel = hasParallel && capWorkers > 1;
else
    useParallel = logical(opts.UseParallel) && hasParallel && capWorkers > 1;
end

pool = [];
if useParallel
    pool = gcp('nocreate');
    if isempty(pool) || pool.NumWorkers ~= capWorkers || ~strcmpi(pool.Cluster.Type, clusterType)
        if ~isempty(pool)
            delete(pool);
        end
        pool = parpool(clusterObj, capWorkers);
    end
end

support = [];
supportConst = [];
if useParallel
    supportConst = parallel.pool.Constant(@() load_ml_support(opts));
else
    support = load_ml_support(opts);
end
defaultOutputDirTemplate = fileparts(defaultOutputPattern);

timeVec = expandDatenum(startDate, endDate);
if isempty(timeVec)
    warning('meteorproc_ml_batch:EmptyRange', 'No days found within the requested span.');
    return;
end

fprintf('[meteorproc_ml_batch] Input pattern : %s\n', char(inputPattern));
fprintf('[meteorproc_ml_batch] Output pattern: %s\n', char(outputPattern));
fprintf('[meteorproc_ml_batch] Annual root   : %s\n', char(annualRoot));
fprintf('[meteorproc_ml_batch] Angles : %s\n', expandPath(opts.AnglesFile));
fprintf('[meteorproc_ml_batch] MEM    : %s\n', expandPath(opts.MemFile));
fprintf('[meteorproc_ml_batch] ML model: %s\n', expandPath(opts.MLModelFile));
fprintf('[meteorproc_ml_batch] SW file : %s\n', expandPath(opts.SWFile));
fprintf('[meteorproc_ml_batch] Date range: %s to %s (%d days)\n', ...
    datestr(timeVec(1), 'yyyy-mm-dd'), datestr(timeVec(end), 'yyyy-mm-dd'), numel(timeVec));
if useParallel
    fprintf('[meteorproc_ml_batch] Parallel pool workers: %d (cap %d, available %d, type %s)\n', pool.NumWorkers, capWorkers, maxWorkersAvailable, clusterType);
else
    fprintf('[meteorproc_ml_batch] Running serially (parallel toolbox unavailable or disabled).\n');
end

annualMap = containers.Map('KeyType', 'char', 'ValueType', 'any');
radarYearsSeen = strings(0, 1);
lastMonth = NaN;
totalFiles = 0;
for idx = 1:numel(timeVec)
    t = timeVec(idx);
    curMonth = month(datetime(t, 'ConvertFrom', 'datenum'));
    if isnan(lastMonth) || curMonth ~= lastMonth
        fprintf('[meteorproc_ml_batch] Starting month %04d-%02d\n', yearSafe(datetime(t, 'ConvertFrom', 'datenum')), curMonth);
        lastMonth = curMonth;
    end

    inPatternPath = expandPath(filename(char(inputPattern), t, [], filesep));
    matches = {};
    if contains(inPatternPath, '*')
        listing = dir(inPatternPath);
        for li = 1:numel(listing)
            if ~listing(li).isdir
                fn = listing(li).name;
                if endsWith(fn, '.winds.nc')
                    continue;
                end
                matches{end+1} = fullfile(listing(li).folder, fn); %#ok<AGROW>
            end
        end
    else
        matches = {inPatternPath};
    end

    if isempty(matches)
        warning('meteorproc_ml_batch:MissingInput', 'No files matched %s', inPatternPath);
        continue;
    end
    matches = select_preferred_matches(matches);
    fprintf('[meteorproc_ml_batch] %s matched %d file(s) after radar preference filtering\n', datestr(t, 'yyyy-mm-dd'), numel(matches));

    outPatternPath = expandPath(filename(char(outputPattern), t, [], filesep));
    [outDirTemplate, outNameTemplate, ~] = fileparts(outPatternPath);
    fallbackOutDir = fileparts(expandPath(filename(char(defaultOutputPattern), t, [], filesep)));

    numMatches = numel(matches);
    taskResults = cell(numMatches, 1);
    taskOutFiles = cell(numMatches, 1);
    taskSites = cell(numMatches, 1);
    taskTimes = repmat(t, numMatches, 1);
    taskInFiles = matches;

    for mi = 1:numMatches
        inFile = matches{mi};
        [~, inBase, ~] = fileparts(inFile);
        if contains(outNameTemplate, '*') || isempty(outNameTemplate)
            outName = [inBase, '.winds.nc'];
        else
            outName = [outNameTemplate, '.nc'];
        end
        outDir = outDirTemplate;
        if isempty(outDir)
            outDir = fallbackOutDir;
        end
        if strcmp(outDir, fileparts(inFile))
            outDir = fallbackOutDir;
        end
        taskOutFiles{mi} = fullfile(outDir, outName);
        taskSites{mi} = [];
    end

    if useParallel
        constRef = supportConst;
        parfor mi = 1:numMatches
            inFile = taskInFiles{mi};
            outFile = taskOutFiles{mi};
            taskResults{mi} = process_single_file(inFile, outFile, t, constRef.Value, filterGroundScatter, passArgs);
        end
    else
        for mi = 1:numMatches
            inFile = taskInFiles{mi};
            outFile = taskOutFiles{mi};
            taskResults{mi} = process_single_file(inFile, outFile, t, support, filterGroundScatter, passArgs);
        end
    end

    for mi = 1:numMatches
        res = taskResults{mi};
        if isempty(res) || ~res.success
            if ~isempty(res) && ~isempty(res.message)
                warning('meteorproc_ml_batch:FileFailed', '%s', res.message);
            end
            continue;
        end
        outFile = res.outFile;
        outDir = fileparts(outFile);
        if ~exist(outDir, 'dir')
            mkdir(outDir);
        end
        writeResultsNetCDF(outFile, res.results, res.inFile, res.site);
        totalFiles = totalFiles + 1;
        radarYearsSeen(end + 1, 1) = string(lower(res.site.code)) + "_" + sprintf('%04d', yearSafe(datetime(res.t, 'ConvertFrom', 'datenum'))); %#ok<AGROW>

        if makeAnnual
            try
                annualMap = updateAnnual(annualMap, res.results, res.site, res.t, res.inFile);
                % Flush when crossing a year boundary or at the end.
                nextYear = [];
                if idx < numel(timeVec)
                nextYear = yearSafe(datetime(timeVec(idx + 1), 'ConvertFrom', 'datenum'));
            end
            thisYear = yearSafe(datetime(t, 'ConvertFrom', 'datenum'));
                if isempty(nextYear) || nextYear ~= thisYear
                    root = annualRoot;
            if strlength(root) == 0
                [rootDir, ~, ~] = fileparts(outFile);
                root = rootDir;
            end
            flushAnnual(annualMap, thisYear, root);
                end
            catch ME
                warning('meteorproc_ml_batch:AnnualFailed', 'Annual aggregation failed for %s (%s)', res.inFile, ME.message);
            end
    end
end
end
fprintf('[meteorproc_ml_batch] Completed. Files processed: %d\n', totalFiles);
if ~isempty(supportConst)
    delete(supportConst);
end
% Final flush to ensure any remaining years are written and rebuild annuals per radar/year.
if makeAnnual
    try
        keys = annualMap.keys;
        for ki = 1:numel(keys)
            grp = annualMap(keys{ki});
            root = annualRoot;
            if strlength(root) == 0
                root = fileparts(outFile);
            end
            flushAnnual(annualMap, grp.year, root);
        end
    catch ME
        warning('meteorproc_ml_batch:FinalAnnualFlush', 'Final annual flush failed (%s)', ME.message);
    end
    try
        ryUnique = unique(radarYearsSeen);
        if ~isempty(ryUnique)
            annualInputPattern = char(opts.OutputPattern);
            annualInputPattern = regexprep(annualInputPattern, '\\*', '{NAME}*');
            for ri = 1:numel(ryUnique)
                parts = split(ryUnique(ri), "_");
                if numel(parts) ~= 2
                    continue;
                end
                rcode = char(parts(1));
                yrval = str2double(parts(2));
                if isnan(yrval)
                    continue;
                end
                try
                    aggregate_winds_annual(yrval, rcode, annualInputPattern, annualRoot);
                catch ME
                    warning('meteorproc_ml_batch:RebuildAnnual', 'Rebuild annual failed for %s_%04d (%s)', rcode, yrval, ME.message);
                end
            end
        end
    catch ME
        warning('meteorproc_ml_batch:RebuildAnnual', 'Rebuild annual pass failed (%s)', ME.message);
    end
end
end

%%
function result = process_single_file(inFile, outFile, t, support, filterGroundScatter, passArgs)
result = struct('success', false, 'results', [], 'site', [], 'inFile', inFile, 'outFile', outFile, 't', t, 'message', '');
if exist(inFile, 'file') ~= 2
    result.message = sprintf('Skipping %s (file not found).', inFile);
    return;
end
fprintf('Processing %s -> %s\n', inFile, outFile);

[results, site, freqByHour] = deal([]);
try
    [results, site, freqByHour] = run_meteorproc_with_site(inFile, filterGroundScatter, passArgs{:});
catch ME
    result.message = sprintf('Failed %s (%s)', inFile, ME.message);
    return;
end
% Keep only rows from the target calendar day to avoid spillover records
% that sometimes appear at hour 00 of the following day.
dayMask = results.year == year(t) & results.month == month(t) & results.day == day(t);
results = results(dayMask, :);
if isempty(results)
    result.message = sprintf('No valid winds for %s after day filter.', inFile);
    return;
end
results = apply_zonal_sign_fix(results, site);
if isempty(results)
    result.message = sprintf('No valid winds for %s.', inFile);
    return;
end

[peakVals, fwhmVals] = deal([]);
try
    [peakVals, fwhmVals] = compute_ml_profile(results, site, t, support, freqByHour);
catch ME
    result.message = sprintf('ML model failed for %s (%s)', inFile, ME.message);
    return;
end
results.Peak = map_hour_values(results.hour, peakVals);
results.FWHM = map_hour_values(results.hour, fwhmVals);
results.tfreq = map_hour_values(results.hour, freqByHour);

% Drop fields not desired in daily/annual outputs.
dropVars = intersect(results.Properties.VariableNames, ...
    {'vm', 'vm_lat', 'vm_lon', 'frang', 'rsep'});
if ~isempty(dropVars)
    results = removevars(results, dropVars);
end

result.success = true;
result.results = results;
result.site = site;
end

%%
function [results, site, freqByHour] = run_meteorproc_with_site(ncfile, filterGroundScatter, varargin)
% Wrap meteorproc_from_netcdf to also return the site metadata and tfreq-derived frequency.
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

records = buildMeteorRecords(fileData, site, filterGroundScatter);
meteorArgs = structToNameValue(parser.Unmatched);
meteorArgs = [meteorArgs, {'SourceName', char(ncfile)}];
results = meteorproc(records, site, meteorArgs{:});
freqByHour = derive_freq_by_hour(fileData, ncfile);
end

%%
function [peakVals, fwhmVals] = compute_ml_profile(results, site, datenumDay, support, freqByHourMHz)
% Build a full-day time grid, interpolate MEM, and run the ML model.
hrs = (0:23).';
Times = datenum(datetime(datevec(datenumDay)) + hours(hrs));
Times = reshape(Times, [], 1);
persistent memCache presCache speedCache
if isempty(memCache)
    memCache = containers.Map('KeyType', 'char', 'ValueType', 'any');
    presCache = containers.Map('KeyType', 'char', 'ValueType', 'any');
    speedCache = containers.Map('KeyType', 'char', 'ValueType', 'any');
end
dayKey = sprintf('%s_%.6f_%.6f_%0.0f_%s', string(site.code), site.geolat, site.geolon, floor(datenumDay), support.mem_source);
if memCache.isKey(dayKey)
    mem_int = memCache(dayKey);
else
    mem_int = interp_mem(support.mem, support.mem_fields, Times, site.geolat, site.geolon);
    memCache(dayKey) = mem_int;
end

presKey = sprintf('%s_%s_%0.0f', string(site.code), support.sw_source, floor(datenumDay));
if presCache.isKey(presKey)
    pres = presCache(presKey);
else
    pres = calc_msis_pressure(Times, 90E3, site.geolat, site.geolon, support.sw);
    presCache(presKey) = pres;
end

speedKey = sprintf('%s_%s_%0.0f_%.6f_%.6f', string(site.code), support.angles_source, floor(datenumDay), site.geolat, site.geolon);
if speedCache.isKey(speedKey)
    speed = speedCache(speedKey);
else
    speed = meteor_speed_density_model(Times, site.geolat, site.geolon, support.meteor_angles);
    speedCache(speedKey) = speed;
end

freqGrid = freqByHourMHz(:);
[peakGrid, fwhmGrid] = run_ml_model(support.Mdl, Times, site.geolat, site.geolon, ...
    mem_int, support.sw, support.meteor_angles, freqGrid, speed, pres);
peakVals = peakGrid(:);
fwhmVals = fwhmGrid(:);
end

%%
function vals = map_hour_values(hours, dailyVector)
vals = nan(numel(hours), 1);
for i = 1:numel(hours)
    h = hours(i);
    if h >= 0 && h <= 23 && h == floor(h)
        vals(i) = dailyVector(h + 1);
    end
end
end

function results = apply_zonal_sign_fix(results, site) %#ok<INUSD>
% Unconditionally flip zonal component sign (vy/u) to match desired convention.
if isempty(results) || ~istable(results)
    return;
end
fieldsToFlip = intersect(results.Properties.VariableNames, {'vy', 'u'});
for fi = 1:numel(fieldsToFlip)
    fld = fieldsToFlip{fi};
    results.(fld) = -results.(fld);
end
end

%%
function preferred = select_preferred_matches(matches)
% For each radar/day, prefer the base file (e.g., fir) over qualifiers (fir.a, fir.b, ...).
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

%%
function [radar, qual] = parse_radar_and_quality(path)
[~, base, ~] = fileparts(path);
m = regexp(base, '(?<radar>[A-Za-z]{3})(?:\.(?<qual>[A-Za-z0-9]+))?$', 'names');
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

%%
function rnk = quality_rank(qual)
if strlength(qual) == 0
    rnk = 0;
    return;
end
q = char(qual);
rnk = 1 + double(lower(q(1)));
end

%%
function support = load_ml_support(opts)
support.sw = readtable(expandPath(opts.SWFile));
support.meteor_angles = load_nc(expandPath(opts.AnglesFile));
support.mem = load_mem(expandPath(opts.MemFile));
support.mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};
support.sw_source = expandPath(opts.SWFile);
support.mem_source = expandPath(opts.MemFile);
support.angles_source = expandPath(opts.AnglesFile);
mdlStruct = load(expandPath(opts.MLModelFile));
flds = fieldnames(mdlStruct);
support.Mdl = struct();
if ismember('Peak', flds)
    support.Mdl.Peak = mdlStruct.Peak;
end
if ismember('FWHM', flds)
    support.Mdl.FWHM = mdlStruct.FWHM;
end
if isempty(fieldnames(support.Mdl)) && ismember('Mdl', flds)
    support.Mdl = mdlStruct.Mdl;
end
support.ml_source = expandPath(opts.MLModelFile);
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

%%
function flushAnnual(annualMap, yearToFlush, annualRoot)
keys = annualMap.keys;
for i = 1:numel(keys)
    key = keys{i};
    group = annualMap(key);
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
    write_group_file(group, dstFile);
    remove(annualMap, key);
end
end

%%
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

%%
function args = structToNameValue(s)
if isempty(fieldnames(s))
    args = {};
    return;
end
names = fieldnames(s);
values = struct2cell(s);
args = reshape([names.'; values.'], 1, []);
end

%%
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

%%
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

%%
function writeResultsNetCDF(outFile, results, sourceFile, site)
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
latAttr = NaN; lonAttr = NaN;
if nargin >= 4 && ~isempty(site) && isfield(site, 'geolat') && isfield(site, 'geolon')
    latAttr = site.geolat;
    lonAttr = site.geolon;
end
if isnan(latAttr) && isfield(results, 'lat') && ~isempty(results.lat)
    latAttr = results.lat(1);
end
if isnan(lonAttr) && isfield(results, 'lon') && ~isempty(results.lon)
    lonAttr = results.lon(1);
end
if ~isnan(latAttr)
    ncwriteatt(outFile, '/', 'radar_latitude', latAttr);
end
if ~isnan(lonAttr)
    ncwriteatt(outFile, '/', 'radar_longitude', lonAttr);
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
    case 'tfreq'
        attrs.long_name = 'Transmit frequency (median, per hour)';
        attrs.units = 'MHz';
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
    case 'tfreq'
        newName = 'tfreq';
    otherwise
        newName = name;
end
end

function values = transform_variable_data(name, values)
switch name
    otherwise
        % no-op
end
end

%%
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

%%
function delete_if_exists(filename)
if exist(filename, 'file')
    delete(filename);
end
end

%%
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

%%
function freqByHour = derive_freq_by_hour(data, ncfile)
% derive per-hour median transmit frequency in MHz using tfreq variable
epoch = data.epoch(:);
if ~isfield(data, 'tfreq') || isempty(data.tfreq)
    error('meteorproc_ml_batch:MissingTFreq', ...
        'tfreq variable not found in %s; cannot derive radar frequency.', ncfile);
end
tfreqVals = double(data.tfreq(:));
if numel(tfreqVals) ~= numel(epoch)
    % Fallback: broadcast available values to match epochs
    reps = ceil(numel(epoch) / numel(tfreqVals));
    tfreqVals = repmat(tfreqVals(:), reps, 1);
    tfreqVals = tfreqVals(1:numel(epoch));
end
vec = datetime(epoch, 'ConvertFrom', 'posixtime', 'TimeZone', 'UTC');
hrs = hour(vec);
freqByHour = nan(24, 1);
for h = 0:23
    mask = hrs == h & ~isnan(tfreqVals);
    if any(mask)
        freqByHour(h + 1) = median(tfreqVals(mask), 'omitnan');
    end
end
if all(isnan(freqByHour))
    error('meteorproc_ml_batch:MissingTFreq', ...
        'No usable tfreq values found in %s; cannot derive radar frequency.', ncfile);
end
units = '';
if isfield(data, 'tfreq_units') && ~isempty(data.tfreq_units)
    units = lower(strtrim(string(data.tfreq_units)));
end
if contains(units, 'hz')
    if contains(units, 'khz')
        freqByHour = freqByHour / 1e3;
    elseif contains(units, 'mhz')
        % leave as-is
    else
        freqByHour = freqByHour / 1e6; % Hz -> MHz
    end
else
    % heuristic by magnitude
    medVal = median(freqByHour(~isnan(freqByHour)));
    if medVal > 1e5
        freqByHour = freqByHour / 1e6; % assume Hz
    elseif medVal > 1e3
        freqByHour = freqByHour / 1e3; % assume kHz
    end
end
overall = median(freqByHour(~isnan(freqByHour)), 'omitnan');
freqByHour(isnan(freqByHour)) = overall;
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

%% ---- Minimal copies from meteorproc_from_netcdf to access site/records ----
function data = readMeteorNetCDF(ncfile)
ncfile = char(ncfile);
try
    data.mjd = double(ncread(ncfile, 'mjd'));
    data.beam = double(ncread(ncfile, 'beam'));
    data.range = double(ncread(ncfile, 'range'));
    data.v = double(ncread(ncfile, 'v'));
    data.p_l = double(ncread(ncfile, 'p_l'));
    data.v_e = double(ncread(ncfile, 'v_e'));
catch ME
    error('meteorproc_ml_batch:ReadNetCDF', 'Failed to read %s (%s)', ncfile, ME.message);
end
% Optional transmit frequency (may be kHz or MHz; handled later)
try
    data.tfreq = double(ncread(ncfile, 'tfreq'));
    try
        data.tfreq_units = ncreadatt(ncfile, 'tfreq', 'units');
    catch
        data.tfreq_units = '';
    end
catch
    data.tfreq = [];
    data.tfreq_units = '';
end
% Optional ground scatter flag
try
    data.gflg = int32(ncread(ncfile, 'gflg'));
catch
    data.gflg = [];
end
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

function records = buildMeteorRecords(data, site, filterGroundScatter)
mask = true(data.numPoints, 1);
if filterGroundScatter && isfield(data, 'gflg') && ~isempty(data.gflg) && numel(data.gflg) == data.numPoints
    mask = mask & (data.gflg(:) ~= 1); % reject ground scatter
end
if ~any(mask)
    records = struct([]);
    return;
end
timeKey = data.timeKey(mask);
beamVals = data.beam(mask);
gateVals = data.gate(mask);
velVals = data.v(mask);
snrVals = data.p_l(mask);
verrVals = data.v_e(mask);
epochVals = data.epoch(mask);
if isfield(data, 'gflg') && ~isempty(data.gflg) && numel(data.gflg) == data.numPoints
    gflgVals = data.gflg(mask);
else
    gflgVals = zeros(nnz(mask), 1, 'like', velVals);
end

combo = [timeKey(:), beamVals(:)];
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

    ranges = gateVals(grpIndices);
    vel = velVals(grpIndices);
    snr = snrVals(grpIndices);
    verr = verrVals(grpIndices);
    beam = beamVals(grpIndices(1));
    gflg = gflgVals(grpIndices);

    rec = template;
    rec.time = epochVals(grpIndices(1));
    rec.bmnum = beam;
    rec.num = len;
    rec.rng = ranges(:);
    rec.data = struct( ...
        'v', num2cell(vel(:)), ...
        'p_l', num2cell(snr(:)), ...
        'v_e', num2cell(verr(:)), ...
        'w_l', num2cell(zeros(len, 1)), ...
        'gflg', num2cell(gflg(:)));

    records(g) = rec;
end
records = reshape(records, 1, []);
end

%%
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
site.bmsep_raw = double(bmsep);
site.bmsep = abs(double(bmsep));
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

function yrs = yearSafe(val)
% Extract year(s) from datenum or datetime without relying on year().
if isnumeric(val)
    dv = datevec(val);
    yrs = dv(:, 1);
elseif isdatetime(val)
    yrs = datevec(datenum(val));
    yrs = yrs(:, 1);
else
    yrs = [];
end
end
