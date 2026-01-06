function savestruct( File, Struct )
% Function to save a structures to a MAT file
%    savestruct( File, Struct )
% Input Arguments:
%    File   = File name and path for output mat file
%    Struct = Structure to save
% Notes:
%    This is a wrapper for matlab's save function which creates the
% directory structure for the file if it dosen't exist.
%
% Example:
%    savestruct('data.mat',x);
%    x = load('data.mat');
%
% See Also: SAVE LOAD
% -------------------------------------------------------------------------
warning off MATLAB:MKDIR:DirectoryExists;

try
   [Path]=fileparts(File); 
   mkdir(Path);
   if length(Struct) == 1 
       try
           save(File,'-struct','Struct');
       catch
           save(File,'Struct');
       end
   else 
       save(File,'Struct'); 
   end
catch
   fprintf('Trapped error in savestructure.m:  ');
   Err = lasterror; 
   fprintf('%s\n',Err.message);
end