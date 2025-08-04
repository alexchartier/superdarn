function [OmegaS, MeanAnomalyAngle, LongitudeOfSun, TrueEccSun, Eccentricity, Alfa1, TT, T0] = ...
    sunparameters(time, lon);
    %sunparameters(Year, Month, Day, Hour, Minutes, Second, AOLong)

%%
time = datetime(2022, 1, 1);

% Get the Julian Date
JulianDates = juliandate(time); % JulianDate(Year,Month,Day,Hour,Minutes,Second);
T0 = (JulianDates - 2415020) / 36525.;   %Time in centuries measured from January 1st 1900 AD
TT = (JulianDates - 2451545.0) / 36525.; %Time in centuries measured from 2000 AD

% Calculate the Sidereal time in hr units
Alfa1 = siderealTime(JulianDates) + lon / 360 * 24;
Alfa1(Alfa1 >= 24) = Alfa1(Alfa1 >= 24) - 24;
Alfa1(Alfa1 < 0) = Alfa1(Alfa1 < 0) + 24;

%Calculate the Longitude of Perihelion of the Sun referred to the ecliptic, measured from the vernal equinox 
OmegaS = deg2rad((281.220833 + 1.719175 * T0 + 4.5277778 - 4 * T0^2 + 3.333334 - 6*T0^3)); %  * pi / 180;

%Calculate the mean anomaly angle from the times
%The anomaly is the angular difference between a mean circular orbit and the true elliptic orbit 
MeanAnomalyAngle = within2pi(deg2rad(358.475845 + 35999.047 * T0 - 1.5 - 4 * T0^2 + 3.3 - 6 * T0^3));

Epsilon = (23.439 - 0.013 * TT) * pi / 180;

%Calculating the Eccentricity
Eccentricity = (0.01675104 - 0.00004180 * T0 - 0.0000000126 * T0^2);

%Calculating the true Longitude of the Sun
LongitudeOfSun = (OmegaS + MeanAnomalyAngle + ...
    2 * Eccentricity * sin(MeanAnomalyAngle) + ...
    5 ./ 4. * Eccentricity^2 * sin(2 * MeanAnomalyAngle));
LongitudeOfSun = within2pi(LongitudeOfSun);

%Calculate the True eccentricity of the Sun
TrueEccSun = (MeanAnomalyAngle + ...
    Eccentricity * (1 - Eccentricity^2 / 8.) * sin(MeanAnomalyAngle) + ...
    Eccentricity^2 / 2. * sin(2 * MeanAnomalyAngle) + ...
    3 * Eccentricity^3 / 8 .* sin(3 * MeanAnomalyAngle));

TrueEccSun = within2pi(TrueEccSun); 

