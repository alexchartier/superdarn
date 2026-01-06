function Struct = loadstruct(Filename)
%% LOADSTRUCT.M
% Function to load a structure into a file (the way mathworks should have
% done it.....

S = load(Filename);
Fields = fieldnames(S);

if length(Fields)==1
    Struct = S.(Fields{1});
else
    Struct = S;
end