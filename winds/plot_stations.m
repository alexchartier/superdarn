
%% 
% python3 get_radar_coords.py
code_fn = '~/data/meteor_winds/madrigal/mwr_madrigal_codes.xlsx';
mwr_dir = '~/data/meteor_winds/mat';

%% 

flist = dir(mwr_dir);
mwr_coords = [];
mwr_sites = {};
for i = 3:length(flist)
    D = loadstruct([mwr_dir, '/', flist(i).name]);
    mwr_coords = [mwr_coords; [D.lat, D.lon]];
end



%% Load 

mwr_coords = [
   69.2691   16.0396
  -30.3000  -70.0000
   54.6305   13.3741
  -77.8297  166.6625
  -53.7000  -67.7000
  ];
Sites = {'AND', 'CON', 'JUL', 'MCM' 'RIO'};


sdr_coords = [
    -69.01 39.61
    68.413 -133.769
    56.43568 58.57142
    53.31753 -60.46424
    -43.40012 147.21627
    41.83265 111.93369
    49.3926 -82.32184
    41.83272 111.93093
    -46.5133 168.37569
    43.27101 -120.35856
    -75.08952 123.35125
    43.5319 143.6146
    43.27053 -120.35642
    37.8573 -75.51019
    -51.8314 -58.9793
    46.76656 130.48594
    63.77258 -20.54476
    43.5374 143.6073
    38.85877 -99.38843
    -75.62 -26.219
    54.8 -66.8
    38.85909 -99.39061
    62.828 -92.113
    63.77443 -20.54167
    57.61215 -152.19116
    -77.83777 166.657
    -34.6271 138.466
    53.98 -122.59
    63.77396 -20.54578
    -69.0 39.58
    51.89337 -176.63121
    -89.995 118.291
    51.89309 -176.62827
    42.885 83.709
    -71.67714 -2.82816
    42.885 83.709
    58.69206 -156.65922
    42.82406 129.42244
    52.16 -106.53
    42.8267 129.41775
    -75.08629 123.3599
    62.31357 26.60562
    37.10211 -77.95033
    53.32 -60.46
    63.86045 -21.0315
    78.15338 16.07342
    -69.37669 76.36646
    70.487 -68.504
    -49.35073 70.26652];
SD_sites = {'sye', 'inv', 'ekb', 'gbr', 'tig', 'sze', 'kap', 'szw', 'unw', ...
    'cvw', 'dce', 'hok', 'cve', 'wal', 'fir', 'jme', 'pyk', 'hkw', 'fhe', ...
    'hal', 'sch', 'fhw', 'rkn', 'ice', 'kod', 'mcm', 'bpk', 'pgr', 'icw', ...
    'sys', 'adw', 'sps', 'ade', 'hjw', 'san', 'hje', 'ksr', 'lje', 'sas', ...
    'ljw', 'dcn', 'han', 'bks', 'tst', 'sto', 'lyr', 'zho', 'cly', 'ker'};

load coastlines
land = readgeotable("landareas.shp");

close all
figure
newmap
geoplot(land)
hold on

ms = 30;

% mwr_coords(mwr_coords(:, 2) > 180, 2) = mwr_coords(mwr_coords(:, 2) > 180, 2) - 360;
plot(mwr_coords(:, 1), mwr_coords(:, 2), '.g', 'MarkerSize', ms)
for i = 1:length(mwr_coords(:, 1))
    text(mwr_coords(i, 1), mwr_coords(i, 2), Sites{i}, ...
        'VerticalAlignment', 'top', 'HorizontalAlignment', 'right', 'color', 'g');
end
plot(sdr_coords(:, 1), sdr_coords(:, 2), '.r', 'MarkerSize', ms)

left_list = {'SCH', 'ICE', 'HJE', 'SZE', 'FHE', 'ADE', 'CVE', 'DCE', 'SYE', 'BKS'};
south_list = {'HOK', 'KSR', 'GBR', 'LJE', 'PYK'};
leftsouth_list = {'ICW'};
for i = 1:length(sdr_coords(:, 1))
    if ismember(upper(SD_sites{i}), left_list)
        text(sdr_coords(i, 1), sdr_coords(i, 2), upper(SD_sites{i}), ...
        'VerticalAlignment', 'bottom', 'HorizontalAlignment', 'right', 'color', 'r');
    elseif ismember(upper(SD_sites{i}), south_list)
        text(sdr_coords(i, 1), sdr_coords(i, 2), upper(SD_sites{i}), ...
        'VerticalAlignment', 'top', 'HorizontalAlignment', 'left', 'color', 'r');
    elseif ismember(upper(SD_sites{i}), leftsouth_list)
        text(sdr_coords(i, 1), sdr_coords(i, 2), upper(SD_sites{i}), ...
        'VerticalAlignment', 'top', 'HorizontalAlignment', 'right', 'color', 'r');
    else
    text(sdr_coords(i, 1), sdr_coords(i, 2), upper(SD_sites{i}), ...
        'VerticalAlignment', 'bottom', 'HorizontalAlignment', 'left', 'color', 'r');
    end
end

set(gca, 'FontSize', 24)
legend({'', 'MWR', 'SDR'})
% hold off