%% model weighted elevation angle variation of combined astronomical sources of meteors
Davis_lat = -62.0;
Davis_long = -58.0;
dates = datenum(2022, 1, 1:365, 0, 0, 0);
hours = 0:23;

lat = Davis_lat;
lon = Davis_long;


%% Fentzke and Janches (2006) model
% Meteoroid source right-ascensions and declinations in ecliptic
% coordinates
% Janches' explanation of weighting:
% JFC = Helion/Antihelion (70%). HTC = apex & toroidal (21%), Asteroidal = ignored.

names = {'apex', 'antiapex', 'helion', 'antihelion', 'south_toroidal', 'north_toroidal'};
lambdas = [270, 270, 350, 190, 270, 270]; % Ecliptic longitude
betas = [15, -15, 0, 0, -60, 60];
weights = [0.21, 0.21, 0.7, 0.7, 0.21, 0.21];


%% Calculate DOY lambda
% Coordinate system is referenced to the vernal equinox (20 March)
t_DOY_lambda0 = 80;
DOY_lambda = zeros([length(dates), length(hours)]);
for d = 1:length(dates)
    for h = 1:length(hours)
        time = dates(d) + hours(h) / 24;
        DOY_lambda(d, h) = ((dates(d) - min(dates) + hours(h) / 24 + 1) - t_DOY_lambda0) * 360/365;
    end
end

DOY_lambda(DOY_lambda >= 360) = DOY_lambda(DOY_lambda >= 360) - 360;
DOY_lambda(DOY_lambda < 0) = DOY_lambda(DOY_lambda < 0) + 360;

%     lambdai = lambda_SToroidal + DOY_lambda((DOY-1)*24+HH+1);

%% Calculate local az/els
alpha = nan(size(names));
delta = nan(size(names));
Az = nan(size(names));
El = nan(size(names));

meanAz = nan(length(dates), length(hours));
meanEl = nan(length(dates), length(hours));
for d = 1:length(dates)
    for h = 1:length(hours)
        time = dates(d) + hours(h) / 24;

        Az = nan(size(names));
        El = nan(size(names));

        for i = 1:length(names)
            lambdai = lambdas(i);
            
            % Time shifts for longitude (see calc_astro_angles.m for details)
            lambdai = lambdai + DOY_lambda(d, h); 
            
            % -180 to 180 centering for eclip2equat
            lambdai(lambdai >= 180) = lambdai(lambdai >= 180) - 360;

            % Ecliptic to equatorial coordinates
            [alpha(i), delta(i)] = eclip2equat(lambdai, betas(i));  % checked!

            % Right Ascension and Declination to Az/El
            [Az(i), El(i)] = RaDec2AzEl(alpha(i), delta(i), lat, lon, time);  
            El(El < 0) = 0;
        end

        % calculate weighted mean angles
        meanAz(d, h) = meanangle(Az, weights);
        meanEl(d, h) = meanangle(El, weights);

    end
end

%%
contourf(dates, hours, meanEl')
datetick
ylabel('Hour (UT)')
title('Davis Antarctica')

c = colorbar;
c.Label.String = 'Elevation angle (°)';
















