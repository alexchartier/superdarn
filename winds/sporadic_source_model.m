function model = sporadic_source_model()
%% sporadic_source_model.m
% 
% model = sporadic_source_model();
%%%  plot
% Names = {'north_apex', 'south_apex', 'helion', 'antihelion', 'north_toroidal', 'south_toroidal'};
%
% hold on
% for i = 1:length(Names)
%    plot(model.(Names{i}), 'LineWidth', 3); 
% end
% legend(Names, 'Interpreter', 'none')
% xlim([1, 366]); 
% ylim([0, 0.5])
% grid on
% grid minor
% xlabel('Day of Year')
% ylabel('Scaled Flux (arbitrary units)')

% What about the meteor angle in relation to the radar boresight?


%% north apex
model.north_apex = zeros([366, 1]);
model.north_apex(1:130) = cosd(([1:130]+60)*1.5)/12 + 0.3;
model.north_apex(131:170) = linspace(model.north_apex(130), 0.2, 40);
model.north_apex(171:200) = linspace(0.2, 0.36, 30);
model.north_apex(201:230) = linspace(0.36, 0.22, 30);
model.north_apex(231:250) = linspace(0.22, 0.28, 20);
model.north_apex(251:300) = linspace(0.28, 0.18, 50);
model.north_apex(301:366) = linspace(0.18, 0.21, 66);


%% south apex
model.south_apex = zeros([366, 1]);
model.south_apex(1:230) = linspace(0.38, 0.28, 230);
model.south_apex(231:366) = linspace(0.28, 0.32, 136);


%% Helion
model.helion = zeros([366, 1]);
model.helion(1:40)  = linspace(0.175, 0.15, 40);
model.helion(41:120)  = linspace(0.15, 0.19, 80);
model.helion(121:145)  = linspace(0.19, 0.15, 25);
model.helion(146:165)  = linspace(0.15, 0.24, 20);
model.helion(166:190)  = linspace(0.24, 0.08, 25);
model.helion(191:230)  = 0.08;
model.helion(231:270)  = linspace(0.08, 0.13, 40);
model.helion(271:300)  = linspace(0.13, 0.10, 30);
model.helion(301:366)  = linspace(0.1, 0.17, 66);


%% Antihelion
model.antihelion = zeros([366, 1]);
model.antihelion(1:130)  = linspace(0.07, 0.22, 130);
model.antihelion(131:175)  = linspace(0.22, 0.18, 45);
model.antihelion(176:200)  = linspace(0.18, 0.23, 25);
model.antihelion(201:260)  = linspace(0.23, 0.13, 60);
model.antihelion(260:340) = 0.13;
model.antihelion(341:366)  = linspace(0.13, 0.07, 26);


%% North toroidal
model.north_toroidal = zeros([366, 1]);
model.north_toroidal(1:40)  = linspace(0.12, 0.06, 40);
model.north_toroidal(41:100)  = linspace(0.06, 0.13, 60);
model.north_toroidal(101:170)  = linspace(0.13, 0.1, 70);
model.north_toroidal(171:200)  = linspace(0.1, 0.12, 30);
model.north_toroidal(201:210)  = linspace(0.12, 0.06, 10);
model.north_toroidal(211:240)  = linspace(0.06, 0.08, 30);
model.north_toroidal(241:366)  = linspace(0.08, 0.06, 126);


%% South toroidal
model.south_toroidal = ones([366, 1]) * 0.1;


