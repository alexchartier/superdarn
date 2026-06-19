function refresh_annual_peak_fwhm(annualRoot, mlModelFn, swFnCsv, memFn, anglesFn, mwrFreqFn)
% refresh_annual_peak_fwhm Recompute Peak/FWHM in annual SuperDARN NetCDFs.
%
% This updates only the meteor-model-derived variables in-place. The wind
% fields and the rest of the annual file content are preserved.
%
% Example:
%   refresh_annual_peak_fwhm( ...
%       '/Users/chartat1/data/superdarn/fit_nc_3_winds/annual', ...
%       '/Users/chartat1/data/meteor_winds/ml_model.mat', ...
%       '/Users/chartat1/data/indices/SW-All.csv', ...
%       '/Users/chartat1/data/meteor_winds/mem_3_output_v1.nc', ...
%       '/Users/chartat1/data/meteor_winds/angles_2008.nc', ...
%       '/Users/chartat1/data/meteor_winds/mwr_freqs.mat');

if nargin < 1 || isempty(annualRoot)
    annualRoot = '/Users/chartat1/data/superdarn/fit_nc_3_winds/annual';
end
if nargin < 2 || isempty(mlModelFn)
    mlModelFn = '/Users/chartat1/data/meteor_winds/ml_model.mat';
end
if nargin < 3 || isempty(swFnCsv)
    swFnCsv = '/Users/chartat1/data/indices/SW-All.csv';
end
if nargin < 4 || isempty(memFn)
    memFn = '/Users/chartat1/data/meteor_winds/mem_3_output_v1.nc';
end
if nargin < 5 || isempty(anglesFn)
    anglesFn = '/Users/chartat1/data/meteor_winds/angles_2008.nc';
end
if nargin < 6 || isempty(mwrFreqFn)
    mwrFreqFn = '/Users/chartat1/data/meteor_winds/mwr_freqs.mat';
end

annualRoot = char(annualRoot);
mlModelFn = char(mlModelFn);
swFnCsv = char(swFnCsv);
memFn = char(memFn);
anglesFn = char(anglesFn);
mwrFreqFn = char(mwrFreqFn);

files = dir(fullfile(annualRoot, '*', '*.nc'));
files = files(~[files.isdir]);
if isempty(files)
    error('refresh_annual_peak_fwhm:NoFiles', 'No annual NetCDF files found under %s', annualRoot);
end

fprintf('[refresh_annual_peak_fwhm] Annual root: %s\n', annualRoot);
fprintf('[refresh_annual_peak_fwhm] Files found : %d\n', numel(files));

Mdl = loadstruct(mlModelFn);
sw = readtable(swFnCsv);
mem = load_mem(memFn);
meteorAngles = load_nc(anglesFn);
mem_fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};

updated = 0;
for i = 1:numel(files)
    fn = fullfile(files(i).folder, files(i).name);
    try
        info = ncinfo(fn);
        varNames = string({info.Variables.Name});
        loadVars = {'year', 'month', 'day', 'hour'};
        if any(varNames == "tfreq")
            loadVars{end + 1} = 'tfreq';
        end
        if any(varNames == "u")
            loadVars{end + 1} = 'u';
        end
        if any(varNames == "v")
            loadVars{end + 1} = 'v';
        end
        data = load_nc(string(fn), loadVars);
        radar = string(get_nc_attr(info, 'radar', infer_radar_from_filename(fn)));
        lat = double(get_nc_attr(info, 'radar_latitude', NaN));
        lon = double(get_nc_attr(info, 'radar_longitude', NaN));

        if ~isfield(data, 'year') || ~isfield(data, 'month') || ~isfield(data, 'day') || ~isfield(data, 'hour')
            warning('refresh_annual_peak_fwhm:MissingTimeFields', 'Skipping %s (missing time fields)', fn);
            continue;
        end
        if ~isfinite(lat) || ~isfinite(lon)
            warning('refresh_annual_peak_fwhm:MissingLatLon', 'Skipping %s (missing radar lat/lon)', fn);
            continue;
        end

        yearMat = double(data.year);
        monthMat = double(data.month);
        dayMat = double(data.day);
        hourVec = double(data.hour(:));
        nHours = numel(hourVec);
        if ~isfield(data, 'u') || ~isfield(data, 'v')
            error('refresh_annual_peak_fwhm:MissingWindFields', ...
                'File %s does not contain both u and v wind fields.', fn);
        end
        uMat = double(data.u);
        vMat = double(data.v);

        if size(yearMat, 2) == nHours
            % already canonical: day x hour
        elseif size(yearMat, 1) == nHours
            yearMat = yearMat.';
            monthMat = monthMat.';
            dayMat = dayMat.';
            uMat = uMat.';
            vMat = vMat.';
        else
            warning('refresh_annual_peak_fwhm:UnexpectedShape', 'Skipping %s (unexpected time grid shape %s)', fn, mat2str(size(yearMat)));
            continue;
        end
        hourGrid = repmat(reshape(hourVec, 1, []), size(yearMat, 1), 1);
        validMask = isfinite(yearMat) & isfinite(monthMat) & isfinite(dayMat) & isfinite(hourGrid);
        if ~any(validMask(:))
            warning('refresh_annual_peak_fwhm:NoValidCells', 'Skipping %s (no finite time cells)', fn);
            continue;
        end

        Peak = nan(size(yearMat));
        FWHM = nan(size(yearMat));
        if ~isfield(data, 'tfreq')
            error('refresh_annual_peak_fwhm:MissingFrequency', ...
                'File %s does not contain tfreq; cannot recompute Peak/FWHM without a frequency grid.', fn);
        end
        freqMat = double(data.tfreq);
        if size(freqMat, 2) == nHours
            % already canonical: day x hour
        elseif size(freqMat, 1) == nHours
            freqMat = freqMat.';
        else
            warning('refresh_annual_peak_fwhm:UnexpectedFreqShape', 'Skipping %s (unexpected tfreq grid shape %s)', fn, mat2str(size(freqMat)));
            continue;
        end

        for dayIdx = 1:size(yearMat, 1)
            timeValid = reshape(isfinite(yearMat(dayIdx, :)) & isfinite(monthMat(dayIdx, :)) & ...
                isfinite(dayMat(dayIdx, :)) & isfinite(hourGrid(dayIdx, :)), 1, []);
            windValid = reshape(isfinite(uMat(dayIdx, :)) | isfinite(vMat(dayIdx, :)), 1, []);
            freqRow = reshape(double(freqMat(dayIdx, :)), 1, []);
            rowValid = timeValid & windValid;
            if ~any(rowValid)
                continue;
            end

            firstValid = find(rowValid, 1, 'first');
            yearVal = yearMat(dayIdx, firstValid);
            monthVal = monthMat(dayIdx, firstValid);
            dayVal = dayMat(dayIdx, firstValid);
            freqValid = reshape(isfinite(freqRow), 1, []);
            if any(rowValid & ~freqValid)
                error('refresh_annual_peak_fwhm:MissingFrequencyCell', ...
                    'File %s has missing tfreq values for a wind-bearing cell at day index %d.', fn, dayIdx);
            end
            cellIdx = find(rowValid & freqValid);
            if isempty(cellIdx)
                continue;
            end

            hourCells = hourVec(cellIdx);
            tCells = datenum(yearVal .* ones(size(hourCells)), monthVal .* ones(size(hourCells)), ...
                dayVal .* ones(size(hourCells)), hourCells, 0, 0);
            tCells = reshape(tCells, [], 1);
            freqCells = reshape(freqRow(cellIdx), [], 1);

            mem_int = interp_mem(mem, mem_fields, tCells, lat, lon);
            speed = meteor_speed_density_model(tCells, lat, lon, meteorAngles);
            pres = calc_msis_pressure(tCells, 90E3, lat, lon, sw);
            [peakRow, fwhmRow] = run_ml_model(Mdl, tCells, lat, lon, mem_int, sw, meteorAngles, freqCells, speed, pres);
            Peak(dayIdx, cellIdx) = peakRow(:).';
            FWHM(dayIdx, cellIdx) = fwhmRow(:).';
        end

        if exist(fn, 'file') ~= 2
            warning('refresh_annual_peak_fwhm:MissingFile', 'Skipping missing file %s', fn);
            continue;
        end

        % The annual NetCDF variables are defined as hour x day_of_year.
        ncwrite(fn, 'Peak', Peak.');
        ncwrite(fn, 'FWHM', FWHM.');

        try
            oldHistory = string(get_nc_attr(info, 'history', ''));
        catch
            oldHistory = "";
        end
        stamp = string(datestr(now, 'yyyy-mm-ddTHH:MM:SS'));
        if strlength(oldHistory) > 0
            newHistory = oldHistory + newline + stamp + ': Peak/FWHM recomputed by refresh_annual_peak_fwhm';
        else
            newHistory = stamp + ': Peak/FWHM recomputed by refresh_annual_peak_fwhm';
        end
        ncwriteatt(fn, '/', 'history', char(newHistory));
        updated = updated + 1;
        fprintf('[%d/%d] Updated %s\n', i, numel(files), fn);
    catch ME
        if ~isempty(ME.stack)
            where = sprintf('%s:%d', ME.stack(1).name, ME.stack(1).line);
        else
            where = 'unknown';
        end
        warning('refresh_annual_peak_fwhm:FileFailed', 'Failed to update %s at %s (%s)', fn, where, ME.message);
    end
end

fprintf('[refresh_annual_peak_fwhm] Updated %d file(s)\n', updated);
end

function val = get_nc_attr(info, name, default)
idx = find(strcmpi({info.Attributes.Name}, name), 1);
if isempty(idx)
    val = default;
else
    val = info.Attributes(idx).Value;
end
end

function radar = infer_radar_from_filename(fn)
[~, base, ~] = fileparts(fn);
parts = split(string(base), '_');
if isempty(parts)
    radar = "fir";
else
    radar = lower(parts(1));
end
end
