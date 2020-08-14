function [ne, alt] = calc_iono(nm, hm, ym, re)
%% calc_iono.m
% Plot Croft's ionosphere
% ne - electron density
% alt - altitude
% nm - peak density
% hm - peak height
% ym - layer thickness
% re - earth radius

%% Define basics
r = [0:3:hm] + re;
rm = hm + re;
ne = zeros(size(r));

%% Calculate ne
ind = r >= (rm - ym);
ne(ind) = nm * (1 - ((r(ind) - rm) / ym) .^ 2);
alt = r - re;