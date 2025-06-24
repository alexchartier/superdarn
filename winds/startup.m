%% pharlap stuff
pl_path = '/Users/chartat1/pharlap/';
path(pl_path,path);
path([pl_path, 'src/matlab/'],path);
path([pl_path, 'mex/'],path);
setenv('DIR_MODELS_REF_DAT', [pl_path, 'dat/'])

% Set path print
fprintf('_______________________________________________________________________\n\n');
fprintf(' Set path to PHaRLAP: %s\n', pl_path);
fprintf('_______________________________________________________________________\n\n');



%% m_map
path(['/Users/chartat1/midas-3/matlab/m_map'],path);
path(['/Users/chartat1/midas-3/matlab/utils'],path);
path(['/Users/chartat1/midas-3/matlab/maths'],path);

path(['/Users/chartat1/MATLABhaprot'],path);

path(['/Users/chartat1/ampere-python/alex/swarm_val'], path);


%% mice
path(['/Users/chartat1/mice/'],path);

%% Paths to MAGIC sub-directories (please leave)
global MIDASROOT;
MIDASROOT = '~/midas-3/';

path([MIDASROOT,'matlab/export_fig'],path);
path([MIDASROOT,'matlab/gps'],path);
path([MIDASROOT,'matlab/maths'],path);
path([MIDASROOT,'matlab/medical'],path);
path([MIDASROOT,'source/mex'],path);
path([MIDASROOT,'matlab/mindi'],path);
path([MIDASROOT,'matlab/m_map'],path);
path([MIDASROOT,'matlab/utils'],path);
path([MIDASROOT,'matlab/utils/hexdump'],path);
path([MIDASROOT,'matlab/utils/matlab_cdf380_patch-64/'],path);

%% Set plotting defaults (edit as required)
S = get(0,'ScreenSize');
set(0,'DefaultFigurePosition',[8,82,S(3:4)/2]);    % Figure position and size
set(0,'DefaultFigureColor',[1,1,1]);               % Figure background color
set(0,'DefaultTextColor',[0,0,0]);                 % Color for text and titles
set(0,'DefaultAxesColor',[1,1,1]);              % Color fill for plot
set(0,'DefaultAxesYColor',[0,0,0]);                % Color of y axis text and ticks
set(0,'DefaultAxesXColor',[0,0,0]);                % Color of x axis text and ticks
set(0,'DefaultAxesZColor',[0,0,0]);                % Color of z axis text and ticks
set(0,'DefaultTextFontSize',14)                    % Font size of titles
set(0,'DefaultAxesFontSize',14)                    % Font size of axes
set(0,'DefaultAxesFontName','arial');              % Axis Font
set(0,'DefaultTextFontName','arial');              % Axis Font


%%

% Plot
set(groot, ...
    'DefaultAxesFontSize', 20, ...
    'DefaultTextFontSize', 20, ...
    'DefaultTextFontName', 'Futura', ...
    'DefaultAxesFontName', 'Futura', ...
    'defaultfigurecolor', [1, 1, 1])
