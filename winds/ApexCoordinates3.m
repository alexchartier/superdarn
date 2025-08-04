function [ZenApex, AzApex] = ApexCoordinates3(Time, LatG, LonG)
%% ApexCoordinates3.m
% % From Diego Janches' IDL script
% % Calculate the Azimuth and Zenith of the Apex direction for a given night 
% % and place on Earth with minute precision
% 
% % Coordinate notes as follows:
% % Apex is in Earth's direction of travel
% % Helion is towards the Sun
% % Toroidal is perpendicular to the ecliptic?
% 
% Times = datetime(2022, 1, 1, 0:23, 0, 0);
% LatG = 0;
% LonG = 0;
% ZenApex = zeros(size(Times));
% AzApex = zeros(size(Times));
% for t = 1:length(Times)
%   [ZenApex(t), AzApex(t)] = ApexCoordinates3(Times(t), LatG, LonG);
% end
% plot(Times, ZenApex); datetick

%% Define constants
a = 1.00001161;

% define conversions, radian to degrees
rad2deg = 180 / pi;
deg2rad = pi / 180;
 
%% Finding the Sun Parameters
[OmegaS, MeanAnomalyAngle, ~, TrueEccSun, Eccentricity, lst, ~, jc] = ...
    sunparameters(Time, LonG);

% Calculating the Earth - Sun distance in astronomical units
SunEarthDist = (1 - Eccentricity * cos(MeanAnomalyAngle) - ...
    Eccentricity^2 / 2 .* (cos(2 * MeanAnomalyAngle) - 1) - ...
    Eccentricity^3 / 8 .* (cos(3 * MeanAnomalyAngle) - ...
    3 * cos(MeanAnomalyAngle))) * a;
 
% Calculate the apex of the earth motion
Xp = (-29.765206 * sin(TrueEccSun) / SunEarthDist);
 
% The ecliptic coordinates of the apex
LambdaApex = within2pi((atan(-Xp) + OmegaS));
BetaApex = 0;
 
% calculating the obliquity for ea hr of the day- angle between the planes of the equator and ecliptic
epsilonD = 23.452294 + (-46.845 * jc - 59 * jc^2 + 181 * jc^3) / 3600;    %degrees
epsilonR = epsilonD * deg2rad;             %radians
 
%% Convert the ecliptic coordinates of the Apex to equatorial coordinates
% The ecliplic coordinate system used so far refers to the ecliptic plane, 
% and must converted to the equatorial coordinates system.
% This is a projection of the Earth coordinates to the celestial sphere, 
% and is synchronized with the rotation of the Earth. 
% The declination (delta) may be considered as the latitude (the angular 
% distance of a  celestial body from the celestial equator), while the 
% right ascension (alpha) is the longitude (the angular distance from the 
% vernal equinox, expressed either in hours or degrees). 

Temp1 = (sin(LambdaApex) * cos(epsilonR) - tan(BetaApex) * sin(epsilonR));
Temp2 = cos(LambdaApex);
AlphaApex = atan(Temp2);
Quadrant1 = Temp1 >= 0 & Temp2 >= 0;
Quadrant2 = Temp1 < 0 & Temp2 >= 0;
Quadrant3 = Temp1 < 0 & Temp2 < 0;
Quadrant4 = Temp1 >= 0 & Temp2 < 0;
if sum(Quadrant3) ~= 0
    AlphaApex(Quadrant3) = AlphaApex(Quadrant3) + 2 * pi;
end
if sum(Quadrant4) ~= 0
    AlphaApex(Quadrant4) = 2. * pi + AlphaApex(Quadrant4);
end
 
DeltaApex = asin(sin(BetaApex) * cos(epsilonR) + cos(BetaApex) * sin(epsilonR) * sin(LambdaApex));
 
% Convert from equatorial to horizon coordinates
% Calculate the hour angle: The angular distance in longitude from a celestial body to the local meridian line. 
% May be expressed in degrees (0? to 360?) or hours (0 to 24 hours).  Here we are considering in radians. 
% The meridian is the line crossing the celestial sphere above an observer's location, from the North celestial pole and 
% passing through the  zenith (the highest point in the sky) and falling to the South point of the  horizon, in the northern 
% hemisphere; from the South celestial pole,  passing through the zenith and falling to the North point of the horizon,  
% in the southern hemisphere. 
HAApex = lst - AlphaApex * rad2deg/15.;
Temp3 = HAApex < 0;
if sum(Temp3) ~= 0 
    HAApex(Temp3) = 24 + HAApex(Temp3);
end
HAApex = HAApex * 15. * deg2rad; %in radians
 
ZenApex = asin(sin(DeltaApex) * sin(LatG) + cos(DeltaApex) * cos(LatG) * cos(HAApex));
AzApex = (acos((sin(DeltaApex) * cos(LatG) - sin(LatG) * sin(ZenApex))/(cos(ZenApex) * cos(LatG)))) * rad2deg;
ZenApex = ZenApex * rad2deg;
Temp4 = sin(HAApex);
Temp5 = Temp4 >= 0;
if sum(Temp5) ~= 0 
    AzApex(Temp5) = 360. - AzApex(Temp5);
end
 