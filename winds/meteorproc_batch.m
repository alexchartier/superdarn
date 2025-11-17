function meteorproc_batch(inputPattern, startDate, endDate, varargin)
%METEORPROC_BATCH Run meteorproc over a date range of NetCDF files.
%
%   METEORPROC_BATCH(INPUTPATTERN, STARTDATE, ENDDATE) uses the existing
%   filename.m helper to expand INPUTPATTERN for each day between STARTDATE
%   and ENDDATE (inclusive), runs METEORPROC_FROM_NETCDF on each file, and
%   writes the hourly results to a daily NetCDF. The directory syntax in
%   INPUTPATTERN should follow the filename.m convention, e.g.
%       '~/data/superdarn/netcdf/{yyyy}/{mm}/{yyyymmdd}.fir.v2.5.nc'
%
%   Name/Value options:
%       'OutputPattern' - Pattern for the output NetCDF path. Defaults to
%                         appending '.winds.nc' to the input pattern.
%       Any other Name/Value arguments are forwarded directly to
%       METEORPROC_FROM_NETCDF (e.g., 'MaxVelocity', 'RequestedHour', etc.).
%
%   Example:
%       meteorproc_batch('~/data/netcdf/{yyyy}/{mm}/{yyyymmdd}.fir.v2.5.nc', ...
%                        datenum(2019,1,1), datenum(2019,1,31), ...
%                        'OutputPattern', '~/data/winds/{yyyy}/{mm}/{yyyymmdd}.fir.nc');

if exist('filename', 'file') ~= 2
    error('meteorproc_batch:FilenameFunc', ...
        'filename.m must be on the MATLAB path (e.g., addpath to utils/filename.m).');
end

if nargin < 3
    error('meteorproc_batch:Inputs', ...
        'Usage: meteorproc_batch(inputPattern, startDate, endDate, ...)');
end

if ~isstring(inputPattern)
    inputPattern = string(inputPattern);
end

parser = inputParser;
parser.FunctionName = 'meteorproc_batch';
parser.KeepUnmatched = true;
parser.addParameter('OutputPattern', inputPattern + ".winds.nc", @(s) ischar(s) || isstring(s));
parser.parse(varargin{:});
args = parser.Results;
inputPattern = string(inputPattern);
outputPattern = string(args.OutputPattern);
passArgs = structToNameValue(parser.Unmatched);

timeVec = expandDatenum(startDate, endDate);
if isempty(timeVec)
    warning('meteorproc_batch:EmptyRange', 'No days found within the requested span.');
    return;
end

for idx = 1:numel(timeVec)
    t = timeVec(idx);
    inFile = expandPath(filename(char(inputPattern), t, [], filesep));
    if isempty(inFile)
        continue;
    end
    if exist(inFile, 'file') ~= 2
        warning('meteorproc_batch:MissingInput', 'Skipping %s (file not found).', inFile);
        continue;
    end
    outFile = expandPath(filename(char(outputPattern), t, [], filesep));
    fprintf('Processing %s -> %s\n', inFile, outFile);
    try
        results = meteorproc_from_netcdf(inFile, passArgs{:});
    catch ME
        warning('meteorproc_batch:ProcessingError', ...
            'meteorproc failed for %s (%s).', inFile, ME.message);
        continue;
    end
    if isempty(results)
        warning('meteorproc_batch:EmptyResult', 'No valid winds for %s.', inFile);
        continue;
    end
    writeResultsNetCDF(outFile, results, inFile);
end
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
        error('meteorproc_batch:UnsupportedType', ...
            'Variable %s is not numeric; cannot write to NetCDF.', varNames{i});
    end
    nccreate(outFile, varNames{i}, 'Dimensions', recordDim, ...
        'Datatype', class(data));
    ncwrite(outFile, varNames{i}, data);
    meta = variableMetadata();
    if isfield(meta, varNames{i})
        attrs = meta.(varNames{i});
        attrNames = fieldnames(attrs);
        for a = 1:numel(attrNames)
            ncwriteatt(outFile, varNames{i}, attrNames{a}, attrs.(attrNames{a}));
        end
    end
end
ncwriteatt(outFile, '/', 'description', 'Hourly meteor winds from meteorproc');
ncwriteatt(outFile, '/', 'generated', datestr(now, 'yyyy-mm-ddTHH:MM:SS'));
if nargin >= 3 && ~isempty(sourceFile)
    ncwriteatt(outFile, '/', 'source', sourceFile);
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

function meta = variableMetadata()
meta.year.long_name = 'Calendar year';
meta.year.units = 'year';

meta.month.long_name = 'Month of year';
meta.month.units = 'month';

meta.day.long_name = 'Day of month';
meta.day.units = 'day';

meta.hour.long_name = 'Hour (UT)';
meta.hour.units = 'hour';

meta.num_avgs.long_name = 'Number of vlos samples included in averages';
meta.num_avgs.units = 'count';

meta.frang.long_name = 'First range gate';
meta.frang.units = 'km';

meta.rsep.long_name = 'Range separation';
meta.rsep.units = 'km';

meta.vx.long_name = 'Meridional wind component (positive southward)';
meta.vx.units = 'm/s';

meta.vy.long_name = 'Zonal wind component (positive eastward)';
meta.vy.units = 'm/s';

meta.lat.long_name = 'Geographic latitude of fit';
meta.lat.units = 'deg';

meta.lon.long_name = 'Geographic longitude of fit';
meta.lon.units = 'deg';

meta.vm.long_name = 'Line-of-sight velocity on vm beam';
meta.vm.units = 'm/s';

meta.vm_lat.long_name = 'Latitude of vm beam intersection';
meta.vm_lat.units = 'deg';

meta.vm_lon.long_name = 'Longitude of vm beam intersection';
meta.vm_lon.units = 'deg';

meta.sdev_vx.long_name = 'Uncertainty of Vx';
meta.sdev_vx.units = 'm/s';

meta.sdev_vy.long_name = 'Uncertainty of Vy';
meta.sdev_vy.units = 'm/s';
end
