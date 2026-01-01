function D = load_nc(fname, variables)
%% Load a netCDF into a struct. Optionally specify fields
arguments
    fname string
    variables cell = {}
end

vn = ncinfo(fname).Variables;

if ~isempty(variables)
    ct = 0;
    for vi = 1:length(vn)
        if ismember(vn(vi).Name, variables)
            ct = ct +1;
            vn2(ct) = vn(vi);
        end
    end
    vn = vn2;
end


D = [];

for v = vn
    
    vnew = strrep(v.Name, '.', '_');
    D.(vnew) = ncread(fname, v.Name);

end

