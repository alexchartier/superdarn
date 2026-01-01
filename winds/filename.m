function out = filename(pattern, t, ~, sep)
%FILENAME Simple token expander for {yyyy}/{mm}/{dd}/{yyyymmdd} patterns.
%   out = filename(pattern, datenum, [], filesep_char)

if nargin < 4 || isempty(sep)
    sep = filesep;
end
if isempty(pattern)
    out = '';
    return;
end

name = char(pattern);
name = strrep(name, '\', '/'); % normalize
dt = datetime(t, 'ConvertFrom', 'datenum');

rep = @(token, fmt) strrep(name, token, datestr(dt, fmt));
name = rep('{yyyy}', 'yyyy');
name = rep('{YYYY}', 'yyyy');
name = rep('{yy}', 'yy');
name = rep('{YY}', 'yy');
name = rep('{mm}', 'mm');
name = rep('{dd}', 'dd');
name = rep('{yyyymmdd}', 'yyyymmdd');
name = rep('{yyyymm}', 'yyyymm');

% Optional {NAME} placeholder is removed.
name = strrep(name, '{NAME}', '');
name = strrep(name, '{name}', '');

name = strrep(name, '//', '/');
name = strrep(name, '/', sep);
out = name;
