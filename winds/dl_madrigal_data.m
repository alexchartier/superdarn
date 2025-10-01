%% download the meteor wind data from madrigal

%% Set inputs

code_fn = '~/data/meteor_winds/madrigal/mwr_madrigal_codes.xlsx';
outdir = '~/data/meteor_winds/madrigal/%s/';

%% Download
names = readtable(code_fn);
codes = names.Var1;
sitenames = names.Var2;
lats = names.Var4;
lons = names.Var5;

for i = 1:length(codes)
    try
    globalDownload('https://cedar.openmadrigal.org/', ...
        sprintf(outdir, strrep(sitenames{i}, ' ', '_')), ...
        'Alex+Chartier', ...
        'alex.chartier@jhuapl.edu', ...
        'APL', ...
        'netCDF4', ...
        datenum('01-Jan-1950 00:00:00'), ...
        datenum('31-Dec-2025 00:00:00'), ...
        codes(i), ...
        [], ...
        '', ...
        '')
    catch
        fprintf('Failed to get some of %s/n', sitenames{i})
    end
end

%% codes

%%  Check for meteor counts in
maddirn = '~/data/meteor_winds/madrigal/';
dirs = dir(maddirn);
for i = 3:length(dirs)
    fprintf('%i %s\n', i, dirs(i).name)
    flist = dir([maddirn, '/', dirs(i).name]);
    if length(flist) > 2
        try
            vn = ncinfo([flist(3).folder, '/', flist(3).name]);
            for ij = 1:length(vn.Variables)
                fprintf('%s\n', vn.Variables(ij).Name)
            end
        catch
            fprintf('Failed on %s\n', dirs(i).name)
        end
    end
end
good = {'South_Pole_meteor_radar', 'McMurdo_Meteor_Radar', ...
    'CONDOR_multi-static_meteor_radar_system'};
