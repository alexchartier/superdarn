function File = filename( Path, Time, Name, Sep )
% Function to generate file names
%    Name = filename( Path, Time, [Name], [Sep] )
% Input Arguments:
%    Path = Path with code strings contained in {} as follows;
%           {NAME} = Replace {NAME} with input string(s) Name, [m,n]
%           {DOY}  = 3 digit day of year
%           {GPSW} = 4 digit GPS week
%           {GPSD} = 1 digit GPS week day
%           {BART} = 4 digit Bartels rotations
%           {HC}   = Letter representing hour of day (A=0, B=2 ... X=23).
%           {hc}   = Letter representing hour of day (a=0, b=2 ... x=23).
%           {...}  = Free-form string used by datestr
%    Time = Time(s), [1,n] datenums
% Optional Input Argument:
%    Name = String(s) to replace {NAME}, [m,n] chars or []
%    Sep  = Force path seperator; '\' or '/', default = '\'
% Output Arguments:
%    File = File name(s) for all combinations of names and times
%
% Notes:
%   Code strings are case sensitive
%
% Example for RINEX file;
%   filename('../{NAME}/{NAME}{DOY}0.{yy}o',datenum(2002,1,1),'colb')
% Example for IGS SP3 file;
%   filename('../{yyyy}/{DOY}/igs{GPSW}{GPSD}.sp3',datenum(2002,1,1))
% Example for multiple names and times;
%   filename('{NAME}{yyyy-mmm-dd}',datenum(2000,1,1)+[0:3],['aa';'bb'])
%
% (Updated 12 May 2011 by Chris Benton.  Fixed bug in {HC} support; Added
% {hc} option for lower case hour-letters.)
%
% See also DATESTR COMB
% ----------------------------------------------------------------------------
if nargin == 1; Time = []; end
if nargin <= 2 || isempty(Name); Name = 'None'; end
if nargin < 4; Sep = '/'; end
if isempty(Time), Time = 0; else Time = reshape(Time,1,length(Time)); end
if isempty(Path), File = ''; return; end

% Check directory seperator for this platform
Path = double(Path);
Path(find((Path==double('/'))+(Path==double('\'))))  = Sep;
Path = char(Path);

File = repmat(Path,size(Name,1)*size(Time,2),1);
Time = repmat(Time,size(Name,1),1);
Name = repmat(Name,size(Time,2),1); Time = Time(:);


i = findstr('{NAME}',File(1,:));
while ~isempty(i)
   File = [File(:,1:i(1)-1),Name,File(:,i(1)+6:end)];
   i = findstr('{NAME}',File(1,:));
end

i = findstr('{DOY}',File(1,:));
while ~isempty(i)
   DOY  = fix(Time-datenum([str2num(datestr(Time,'yyyy')),ones(size(Time,1),2)])+1);
   DOY  = reshape(sprintf('%03d',DOY),3,size(Time,1)).';
   File = [File(:,1:i(1)-1),DOY,File(:,i(1)+5:end)];
   i = findstr('{DOY}',File(1,:));
end

i = findstr('{GPSW}',File(1,:));
while ~isempty(i)
   GPSW = fix((fix(Time)-datenum(repmat([1980,1,6],size(Time,1),1)))/7);
   GPSW = reshape(sprintf('%04d',GPSW),4,size(Time,1)).';
   File = [File(:,1:i(1)-1),GPSW,File(:,i(1)+6:end)];
   i = findstr('{GPSW}',File(1,:));
end

i = findstr('{GPSD}',File(1,:));
while ~isempty(i)
   GD = mod(fix(Time)-datenum(repmat([1980,1,6],size(Time,1),1)),7);
   GD = reshape(sprintf('%1d',GD),1,size(Time,1)).';
   File = [File(:,1:i(1)-1),GD,File(:,i(1)+6:end)];
   i = findstr('{GPSD}',File(1,:));
end

i = findstr('{BART}',File(1,:));
while ~isempty(i)
   Ba = fix((fix(Time)-datenum(repmat([1832,2,8],size(Time,1),1)))/27)+1;
   Ba = reshape(sprintf('%4d',Ba),4,size(Time,1)).';
   File = [File(:,1:i(1)-1),Ba,File(:,i(1)+6:end)];
   i = findstr('{BART}',File(1,:));
end

i = findstr('{HC}',File(1,:));
while ~isempty(i)
   % +1E-6 offset prevents rounding error from shifting hour to previous.
   Hc = 'A' + fix(mod(Time+1E-6,1)*24);
   Hc = reshape(char(Hc),1,size(Time,1)).';
   File = [File(:,1:i(1)-1),Hc,File(:,i(1)+4:end)];
   i = findstr('{HC}',File(1,:));
end

i = findstr('{hc}',File(1,:));
while ~isempty(i)
   % +1E-6 offset prevents rounding error from shifting hour to previous.
   Hc = 'a' + fix(mod(Time+1E-6,1)*24);
   Hc = reshape(char(Hc),1,size(Time,1)).';
   File = [File(:,1:i(1)-1),Hc,File(:,i(1)+4:end)];
   i = findstr('{hc}',File(1,:));
end

% Convert remaining formats according to datestr rules
i = findstr('{',File(1,:));
j = findstr('}',File(1,:));
while ~isempty(i)
   File = [File(:,1:i(1)-1), datestr(Time,File(1,i(1)+1:j(1)-1)),File(:,j(1)+1:end)];
   i = findstr('{',File(1,:));
   j = findstr('}',File(1,:));
end

