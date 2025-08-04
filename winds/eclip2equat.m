function [alpha, delta] = eclip2equat(lambda, beta)
% ECLIP2EQUAT - Convert from ecliptic to equatorial celestial coordinates.
%   [alpha,delta] = eclip2equat(lambda,beta) returns the right ascension 
%   and declination in the equatorial coordinate system corresponding
%   to the longitudinal and latitudinal coordinates in the ecliptic
%   coordinate system (lambda and beta)
% 
%   All inputs and outputs are in units of degrees.  alpha will be in the
%   range of [-180, 180] while delta will be in the range [-90, 90]. 
%   Inputs must be vectors of equal size;
% 
%   Example:
%       [alpha, delta] = eclip2equat([ -0.2295;-0.5555],[0.1517;0.2792]);
 
%   Written by Dmitry Savransky, 3 March 2009
%error checking
if nargin ~= 2
    error('You must input both Declination and Right Ascension.');
end
lambda = deg2rad(lambda(:));
beta = deg2rad(beta(:));
if length(lambda) ~= length(beta)
    error('Inputs must be the same length.');
end
%define Earth's axial tilt
epsilon = (23 + 26/60 + 21.448/3600)*pi/180; %radians
%calculate trigonometric combinations of coordinates
sd = sin(epsilon)*sin(lambda).*cos(beta) + cos(epsilon)*sin(beta);
cacd = cos(lambda).*cos(beta);
sacd = cos(epsilon)*sin(lambda).*cos(beta) - sin(epsilon).*sin(beta);
%calculate coordinates
alpha = atan2(sacd,cacd);
r = sqrt(cacd.^2 + sacd.^2);
delta = atan2(sd,r);
r2 = sqrt(sd.^2+r.^2);
%sanity check: r2 should be 1
if sum(abs(r2 - 1)) > 1e-12
    warning('equat2eclip:radiusError',...
        'Latitude conversion radius is not uniformly 1. ');
end

alpha = rad2deg(alpha);
delta = rad2deg(delta);