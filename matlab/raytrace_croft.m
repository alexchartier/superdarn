function [Pgc,Pgroup,Pphase] = raytrace_croft(f0,beta0,fm,hm,ym)
%% raytrace_croft.m
% Raytracer based on Croft [1968] quasi-parabolic bottomside ionosphere
%
% [Pgc,Pgroup,Pphase] = raytrace_croft(f0,beta0,fm,hm,ym)
%
% f0 = operating frequency
% beta0 = takeoff ray angle
% fm = critical frequency?
% hm = peak height
% ym = layer semithickness
%
% Pgc = Ground path?
% Pgroup = group path
% Pphase = phase path


%% Define basic quantities
F = f0 ./ fm;   % Ratio of operating frequency to critical frequency
r0 = 6371;    % Earth radius (km)
rm = r0 + hm; % Peak radius 
rb = rm - ym; % Radius of base of layer

% Cos(gamma) is the angle of the ray at the bottom of the ionosphere
gamma = acos(r0 ./ rb .* cos(beta0));  


%% Calculations from Croft's paper
A = 1 - 1 ./ (F.^2) + (rb ./ (F .* ym)).^2;
B = - 2 * rm .* rb.^2 ./ (F.^2 .* ym.^2);
C = ((rb .* rm) ./ (F .* ym)).^2 - r0.^2 .* cos(beta0).^2;

Pgc = 2 * r0 * ((gamma - beta0) - (r0 .* cos(beta0) ./ (2 * sqrt(C))) .* ...
    log((B.^2 - 4 * A .* C) ./ (4 * C .* (sin(gamma) + (1 ./ rb) .* sqrt(C) + ...
    B ./ (2 * sqrt(C))).^2)));  % Equation 6a

Pgroup = 2 * (rb .* sin(gamma) - r0 .* sin(beta0) + (1 ./ A) .* ...
    (-rb .* sin(gamma) - (B ./ (4 .* sqrt(A))) .* log((B.^2 - 4 .* A .* C) ./ ...
    (2 * A .* rb + B + 2 * rb .* sqrt(A) .* sin(gamma)).^2)));  % Equation 6b

Pphase = 2 * (-r0 .* sin(beta0) + (B / 4) .* ((1 ./ sqrt(A)) .* ...
    log((B.^2 - 4 * A .* C) ./ ...
    (4 * (A .* rb + (B / 2) + sqrt(A) .* rb .* sin(gamma)).^2)) + ...
    (rm ./ sqrt(C)) .* log((B.^2 - 4 * A .* C) ./ ...
    (4 * C .* (sin(gamma) + sqrt(C) ./ rb + B ./ (2 * sqrt(C))).^2))));  % Eq. 6c


assert(isreal(Pgc), 'Complex array returned - check settings')














