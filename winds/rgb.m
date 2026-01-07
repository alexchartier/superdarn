function cmap = rgb()
%RGB Return a finely sampled SuperDARN colormap (10x the base resolution).
base = [ ...
    94    79   162
    50   136   189
   102   194   165
   171   221   164
   230   245   152
   255   255   191
   254   224   139
   253   174    97
   244   109    67
   213    62    79
   158     1    66  ] / 255;
nBase = size(base, 1);
xi = linspace(1, nBase, nBase * 10);
cmap = interp1(1:nBase, base, xi, 'linear');
end
