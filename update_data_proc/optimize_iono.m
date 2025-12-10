%% optimize_iono.m
% Optimize Croft's quasi-parabolic ionosphere based on SuperDARN data
%
% Croft's raytracer produces [Pgc,Pgroup,Pphase] based on (f0,beta0,fm,hm,ym)
% Observables are Pgroup, Pphase
% Known variables are f0, beta0
% Unknowns are fm, hm and ym
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
%
% Define the problem as follows:
%           x = [fm, hm, ym]
%        AFun = croft_raytrace(f0, beta0, x)
%           B = [Pgroup, Pphase]


%% TODO: Check the accuracy of ground scatter range predictions

%% Switches
iono_type = 'iri'; % 'iri' % 'real'

if strcmp(iono_type, 'croft')  
    %% Internal simulation (homogeneous)
    f0 = 20;
    beta0 = [2:2:20];
    nm_T = 1E12;
    fm_T = elec2freq(nm_T) / 1E6;
    hm_T = 300;
    ym_T = 100;
    [Pground, Pgroup, Pphase] = raytrace_croft(f0, deg2rad(beta0), fm_T, hm_T, ym_T);
    B = raytrace_croft_optim(f0, beta0, fm_T, hm_T, ym_T);
    
%%
elseif strcmp(iono_type, 'iri')  
    %% External simulation (heterogeneous)
    % Load stuff
    D = loadstruct('ne_polar.mat');
    ray_data = loadstruct('ray_data.mat');
    
    % Specify input variables
    f0 = nan(size(ray_data));
    beta0 = nan(size(ray_data));
    Pground = nan(size(ray_data));
    Pgroup = nan(size(ray_data));
    Pphase = nan(size(ray_data));
    
    for i = 1:length(ray_data)
        f0(i) = ray_data(i).frequency;
        beta0(i) = ray_data(i).initial_elev(1);
        Pground(i) = ray_data(i).group_range(1);
        Pgroup(i) = ray_data(i).group_range(1);
        Pphase(i) = ray_data(i).phase_path(1);
    end
    % Just use scatter within 1000 - 5000 km
    %ind = Pgroup < 1E5 & Pphase < 1E5 & Pgroup > 5 & Pphase > 5;  
    
    ind = beta0 > 0;
    f0 = f0(ind);
    beta0 = beta0(ind);
	Pground = Pground(ind);
    Pgroup = Pgroup(ind);
    Pphase = Pphase(ind);

    B = [Pgroup, Pphase];
    
    % Calculate what the 'truth' ionosphere is
    mean_dens = mean(D.F, 2);
    nm_T = max(mean_dens) * 1E6;
    fm_T = elec2freq(nm_T) / 1E6;
    hm_T = D.Alt(mean_dens == (nm_T / 1E6));
    
    bottomside = mean_dens(D.Alt <= hm_T);
    half_rb = D.Alt(mean_dens == closest(bottomside, (nm_T / 1E6) / 2));
    rb_T = hm_T - (hm_T - half_rb) * 2;  % Not perfect, but it's only for comparison
    ym_T = hm_T - rb_T;
        
else  % Use real observations from SuperDARN
    fprintf('%s simulation not implemented yet', iono_type)
end


%% Define initial guess X0
fm0 = max(f0);
hm0 = 220;
ym0 = 50;
X0 = [fm0, hm0, ym0];


%% Define cost function A
A = @(x) sum((raytrace_croft_optim(f0, beta0, x(1), x(2), x(3)) - B) .^ 2);

% NOTE: Lb should not be set too high - can screw things up
lb = [1, 200, 50];  
ub = [10, 500, 300];

X = fmincon(A, X0, [], [], [], [], lb, ub);

%% Display output
fprintf('     ************************\n')
fprintf('     ** Experiment Summary **\n')
fprintf('     ************************\n\n')
fprintf('Ionosphere type: %s\n\n',  iono_type)
fprintf('    truth      initial    final\n')
fprintf('fm: %2.2f       %2.2f       %2.2f\n', [fm_T, unique(fm0), X(1)])
fprintf('hm: %2.2f     %2.2f      %2.2f\n', [hm_T, hm0, X(2)])
fprintf('ym: %2.2f     %2.2f      %2.2f\n', [ym_T, ym0, X(3)])


%% Compare estimated against truth ground, group and phase paths
[PgroundI, PgroupI, PphaseI] = raytrace_croft(f0, deg2rad(beta0), fm0, hm0, ym0);
[PgroundO, PgroupO, PphaseO] = raytrace_croft(f0, deg2rad(beta0), X(1), X(2), X(3));

fprintf('RMS first guess ground path error: %3.3f km\n', ...
    sqrt(mean(Pground - PgroundI) .^2))
fprintf('RMS final guess ground path error: %3.3f km\n', ...
    sqrt(mean(Pground - PgroundO) .^2))

subplot(3, 1, 1)
hold on 
plot(beta0, Pground, 'k', 'LineWidth', 4)
plot(beta0, PgroundI, 'r', 'LineWidth', 2)
plot(beta0, PgroundO, 'b', 'LineWidth', 2)
hold off
grid on
grid minor
ylabel('Ground Path')

subplot(3, 1, 2)
hold on 
plot(beta0, Pgroup, 'k', 'LineWidth', 4)
plot(beta0, PgroupI, 'r', 'LineWidth', 2)
plot(beta0, PgroupO, 'b', 'LineWidth', 2)
hold off
grid on
grid minor
ylabel('Group Path')

subplot(3, 1, 3)
hold on 
plot(beta0, Pphase, 'k', 'LineWidth', 4)
plot(beta0, PphaseI, 'r', 'LineWidth', 2)
plot(beta0, PphaseO, 'b', 'LineWidth', 2)
hold off
grid on
grid minor
ylabel('Phase Path')
xlabel('elevation angle beta')


%% Plot
figure
re = 6371;
clf
hold on

% Truth
if strcmp(iono_type, 'iri')
    plot(mean_dens * 1E6, D.Alt, 'k', 'LineWidth', 4)
elseif strcmp(iono_type, 'croft')
    [neT, altT] = calc_iono(nm_T, hm_T, ym_T, re);
    plot(neT, altT, 'k', 'LineWidth', 4)
end

% Start guess
[ne0, alt0] = calc_iono(freq2elec(X0(1) * 1E6), X0(2), X0(3), re);
plot(ne0, alt0, '--Xr', 'LineWidth', 2)

% Final guess
[ne, alt] = calc_iono(freq2elec(X(1) * 1E6), X(2), X(3), re);
plot(ne, alt, '--Xb', 'LineWidth', 2)

legend({'Truth', 'Start guess', 'Final guess'})
xlabel('Electron Density [m^-^3]')
ylabel('Altitude [km]')

legend(sprintf('%s Truth', upper(iono_type)), 'Starting guess', 'Final guess')
grid minor 
grid on
hold off


























