function wind = calc_wind_component(lats, lons, alt, month, model_coeffs, comps, lst, dirn)
%
% compare against https://agupubs.onlinelibrary.wiley.com/doi/epdf/10.1029/2011JA016784
%
% lats: list of latitudes (deg)
% lons: list of longitudes (deg)
% alt: reference altitude (km)
% month: 1-12
% model_coeffs: Jens' netCDFs loaded into a dict
% comps: dict of wave components (diurnal and semidiurnal - see table_of_components())
% lst: local solar time
% dirn: 'u' or 'v' (zonal/meridional)
%

% Calculate the wind

wind = zeros(length(lats), length(lons));
hours = lst - lons / 360 * 24;
ds_list = fieldnames(comps);
for ids = 1:length(ds_list)
    ds = ds_list{ids};
    comp_list = comps.(ds);
    for icomp = 1:length(comp_list)
        comp = comp_list{icomp};
        wind_comp = calc_wind(model_coeffs.(ds), ...
            lats, lons, alt, hours, month, comp, dirn, ds);
        wind = wind + wind_comp;
    end
end
