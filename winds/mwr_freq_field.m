function field = mwr_freq_field(siteCode)
%MWR_FREQ_FIELD Map a site/radar code to the field name in mwr_freqs.mat.

code = lower(string(strtrim(siteCode)));
switch code
    case {"and", "andenes"}
        field = 'And';
    case {"jul", "juliusruh"}
        field = 'Jul';
    case {"rio", "riogrande"}
        field = 'riogrande';
    case {"condor"}
        field = 'CONDOR';
    case {"mcm", "mcmurdo"}
        field = 'McMurdo';
    otherwise
        field = char(siteCode);
end
end
