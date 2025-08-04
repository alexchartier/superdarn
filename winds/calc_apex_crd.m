lat = 0;
lon = 0;
height = 0;
apex_ecliptic_lon = 270;  % Only at the Vernal Equinox!
apex_ecliptic_lat = 0;
time = datenum(2022, 3, 20, 6, 0, 0);
t_DOY_lambda0 = 79;

%% Add the DOY adjustment to Earth's Apex longitude
dt = datetime(time, 'ConvertFrom', 'datenum');
DOY = day(dt, 'DayOfYear');
DOY_lambda = (DOY - t_DOY_lambda0) * 360/365;

apex_ecliptic_lon = rad2deg(within2pi(deg2rad(apex_ecliptic_lon + DOY_lambda)));

%%

[alpha, delta] = eclip2equat(apex_ecliptic_lon, apex_ecliptic_lat);


% alpha: right-ascension, delta: declination
R = 6371E3 + height;


X = R * cosd(delta) * cosd(alpha);
Y = R * cosd(delta) * sind(alpha);
Z = R * sind(delta);


[xEast, yNorth, zUp] = ecef2enu(X, Y, Z, lat, lon, height, wgs84Ellipsoid);

RAE = xyz2rae([xEast, yNorth, zUp]); %???
RAE(:, 2:3) = rad2deg(RAE(:, 2:3));

[Az, El] = RaDec2AzEl(RAE(2), RAE(3), lat, lon, time);