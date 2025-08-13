function model = sporadic_source_model();

% Names = {'north_apex', 'south_apex', 'helion', 'anti_helion', 'north_toroidal', 'south_toroidal'};
%
%%%  plot
%hold on
%for i = 1:length(Names)
%    plot(out.(Names{i}), 'LineWidth', 3); 
%end
%legend(Names)
%xlim([1, 366]); 
%ylim([0, 0.5])
%grid on
%grid minor


%% north apex
out.north_apex = zeros([366, 1]);
out.north_apex(1:130) = cosd(([1:130]+60)*1.5)/12 + 0.3;
out.north_apex(131:170) = linspace(north_apex(130), 0.2, 40);
out.north_apex(171:200) = linspace(north_apex(170), 0.36, 30);
out.north_apex(201:230) = linspace(north_apex(200), 0.22, 30);
out.north_apex(231:250) = linspace(north_apex(230), 0.28, 20);
out.north_apex(251:300) = linspace(north_apex(250), 0.18, 50);
out.north_apex(301:366) = linspace(north_apex(300), 0.21, 66);


%% south apex
out.south_apex = zeros([366, 1]);
out.south_apex(1:230) = linspace(0.38, 0.28, 230);
out.south_apex(231:366) = linspace(0.28, 0.32, 136);


%% Helion
out.helion = zeros([366, 1]);
out.helion(1:40)  = linspace(0.175, 0.15, 40);
out.helion(41:120)  = linspace(0.15, 0.19, 80);
out.helion(121:145)  = linspace(0.19, 0.15, 25);
out.helion(146:165)  = linspace(0.15, 0.24, 20);
out.helion(166:190)  = linspace(0.24, 0.08, 25);
out.helion(191:230)  = 0.08;
out.helion(231:270)  = linspace(0.08, 0.13, 40);
out.helion(271:300)  = linspace(0.13, 0.10, 30);
out.helion(301:366)  = linspace(0.1, 0.17, 66);


%% Antihelion
out.antihelion = zeros([366, 1]);
out.antihelion(1:130)  = linspace(0.07, 0.22, 130);
out.antihelion(131:175)  = linspace(0.22, 0.18, 45);
out.antihelion(176:200)  = linspace(0.18, 0.23, 25);
out.antihelion(201:260)  = linspace(0.23, 0.13, 60);
out.antihelion(260:340) = 0.13;
out.antihelion(341:366)  = linspace(0.13, 0.07, 26);


%% North toroidal
out.north_toroidal = zeros([366, 1]);
out.north_toroidal(1:40)  = linspace(0.12, 0.06, 40);
out.north_toroidal(41:100)  = linspace(0.06, 0.13, 60);
out.north_toroidal(101:170)  = linspace(0.13, 0.1, 70);
out.north_toroidal(171:200)  = linspace(0.1, 0.12, 30);
out.north_toroidal(201:210)  = linspace(0.12, 0.06, 10);
out.north_toroidal(211:240)  = linspace(0.06, 0.08, 30);
out.north_toroidal(241:366)  = linspace(0.08, 0.06, 126);


%% South toroidal
out.south_toroidal = ones([366, 1]) * 0.1;


