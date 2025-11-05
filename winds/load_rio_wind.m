%% Load a wind file
function wind = load_rio_wind(fn)
tbl = readtable(fn);

Time = datenum(tbl.Var1, tbl.Var2, tbl.Var3, tbl.Var4, 0, 0);
alt = tbl.Var5;
wind_u = tbl.Var6;  % zonal 
wind_v = tbl.Var8;  % meridional 
wind_u(wind_u == 9999) = NaN;
wind_v(wind_v == 9999) = NaN;

wind.Time = unique(Time);
wind.alt = unique(alt);
wind.u = reshape(wind_u, length(wind.alt), length(wind.Time))';
wind.v = reshape(wind_v, length(wind.alt), length(wind.Time))';
wind.lat = -53.8;
wind.lon = -67.8;
wind.hour = [0:23]';

end

