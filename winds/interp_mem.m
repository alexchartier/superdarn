function out = interp_mem(mem, fields, Times, lat, lon)
%%
dv_mem = datevec(mem.times(:));
mem_yr = median(dv_mem(:, 1));
tv = Times(:);
dv = datevec(tv);
times_yr = median(dv(:, 1));
yrs_to_add = times_yr - mem_yr;
mem_dt = datetime(mem.times, 'ConvertFrom', 'datenum');
mem_times = datenum(mem_dt + calyears(yrs_to_add));

lon(lon < 0) = lon(lon < 0) + 360;
for fi = 1:length(fields)
    out.(fields{fi}) = zeros(size(Times)) * NaN;
    for hri = 1:size(Times, 1)
        try
            V = squeeze(mem.(fields{fi})(hri, :, :, :));
        catch
            disp(1)
        end
        out.(fields{fi})(hri, :) = interp3(...
            squeeze(mem_times(hri, :))', mem.lon,  mem.lat, ...
            permute(V, [2, 1, 3]), ...
            Times(hri, :), lon, lat);

        if sum(isnan(out.(fields{fi})(hri, :))) > 0
            disp(1)
        end
    end
end
