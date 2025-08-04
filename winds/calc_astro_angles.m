%% Orbit_test_ED_use_general_16thJune2022.m
% Based on:Orbit_test_ED_use_18Apr2022.m
%clear all;
%close all;

% what am i trying to produce?
% what does this code do?
% - takes in meteor long/lat, and time and alt/vel, and computes azimuth
% and elevation angle.
% so seeing as this is at the same lat/lon (and height) are we just
% changing the velocities?
% SAAMER
%51.3 deg, 13.0 deg
% ANDES: 30.3S, 70.7W
Davis_lat = -62.0;
Davis_long = -58.0;
meteor.lat=Davis_lat;
meteor.long=Davis_long;

year_index = [2004 2005 2006 2007 2008 2009 2010 2011 2012 2013 2014 2015 2016 2017 2018 2019 2020 2021 2022];
month_index = [0 31 28 31 30 31 30 31 31 30 31 30];
DAYSOFYEAR = [0 31 59 90 120 151 181 212 243 273 304 334];
mm_index = [1 2 3 4 5 6 7 8 9 10 11 12];
HH_index = [0:23];

DOY_incr = 360/(365*24);

DOY_multiplier = NaN(365,1);
count=-1;
for i = 80:365;
    for hh = 1 : 24;
        count = count+1;
        DOY_multiplier((79*24)+count) = count;
    end
end
daycounter = 0;
for i = 1:79
    for hh = 1 : 24;
        daycounter = daycounter+1;
        count = count+1;
        DOY_multiplier(daycounter) = count;
    end
end

DOY_lambda = NaN(length(DOY_multiplier),1);
for i = 1 : length(DOY_lambda);
    DOY_lambda(i) = DOY_incr*DOY_multiplier(i);
end

lambda_apex = 270;
lambda_antiapex = 270;
lambda_helion = 350;
lambda_antihelion = 190;
lambda_SToroidal = 270;
lambda_NToroidal = 270;
beta_apex = 15;
beta_antiapex = -15;
beta_helion = 0;
beta_antihelion = 0;
beta_SToroidal = -60;
beta_NToroidal = 60;

YY = year_index(1);
all_data_phi = NaN(365,24);
all_data_theta = NaN(365,24);
all_data_dec = NaN(365,24);
all_data_alpha = NaN(365,24);
all_data_lambda = NaN(365,24);
all_data_beta = NaN(365,24);
for DOY = 1 : 365;
    tx1 = find([DAYSOFYEAR]<=DOY); tx1 = max(tx1);
    MM = mm_index(tx1);
    DD = DOY-DAYSOFYEAR(tx1);
    for HH = HH_index(1):HH_index(end)
        meteor.time=datenum(YY,MM,DD,HH,00,00);
        meteor.alt=90;%110.4;
        meteor.vel=55;%28.54;

        alpha=0;%127.17;
        dec=0;%18.35;

        if DOY==1;
            lambda = lambda_apex + DOY_lambda(1+HH);
        end
        if DOY>1 & DOY<365;
            lambda = lambda_apex + DOY_lambda((DOY-1)*24+HH+1);
        end
        if DOY==365;
            if HH == 23;
                lambda = lambda_apex + DOY_lambda(1);
            end
        end
        beta = beta_apex;
        all_data_lambda(DOY,HH+1) = lambda;
        all_data_beta(DOY,HH+1) = beta;

        [astro]=startimeJ2000(meteor.time,meteor.long);

        % convert from lambda and beta to dec and alpha;
        %Coordinate Transformation from ecliptic to equatorial coordinates
        eps=23.439281;

        cx1=cos(beta*pi/180.0)*cos(lambda*pi/180.0);
        cy1=-sin(eps*pi/180.0)*sin(beta*pi/180.0)...
            +cos(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        cz1=cos(eps*pi/180.0)*sin(beta*pi/180.0)...
            +sin(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        dec=180.0*asin(cz1)/pi;
        alpha=180.0*atan2(cy1,cx1)/pi;
        if(alpha<0.0)
            alpha=alpha+360.0;
        end
        if(alpha>=360.0)
            alpha=alpha-360.0;
        end

        all_data_dec(DOY,HH+1) = dec;
        all_data_alpha(DOY,HH+1) = alpha;

        % convert from dec and alpha to phi and theta;
        phi = 0;
        theta = 0;
        [phi,theta,alpha,dec]= hcec(phi,theta,alpha,dec,astro.startheta,1,-1,meteor.lat);

        meteor.phi=phi;
        meteor.theta=theta;
        all_data_phi(DOY,HH+1) = phi;
        all_data_theta(DOY,HH+1) = theta;

    end
end

%end

all_data_theta_apex = all_data_theta;
all_data_phi_apex = all_data_phi;

YY = year_index(1);
all_data_phi = NaN(365,24);
all_data_theta = NaN(365,24);
all_data_dec = NaN(365,24);
all_data_alpha = NaN(365,24);
all_data_lambda = NaN(365,24);
all_data_beta = NaN(365,24);
for DOY = 1 : 365;
    tx1 = find([DAYSOFYEAR]<=DOY); tx1 = max(tx1);
    MM = mm_index(tx1);
    DD = DOY-DAYSOFYEAR(tx1);
    for HH = HH_index(1):HH_index(end);
        meteor.time=datenum(YY,MM,DD,HH,00,00);
        meteor.alt=90;%110.4;
        meteor.vel=55;%28.54;

        alpha=0;%127.17;
        dec=0;%18.35;

        if DOY==1;
            lambda = lambda_antiapex + DOY_lambda(1+HH);
        end
        if DOY>1 & DOY<365;
            lambda = lambda_antiapex + DOY_lambda((DOY-1)*24+HH+1);
        end
        if DOY==365;
            if HH == 23;
                lambda = lambda_antiapex + DOY_lambda(1);
            end
        end
        beta = beta_antiapex;
        all_data_lambda(DOY,HH+1) = lambda;
        all_data_beta(DOY,HH+1) = beta;

        [astro]=startimeJ2000(meteor.time,meteor.long);

        % convert from lambda and beta to dec and alpha;
        %Coordinate Transformation from ecliptic to equatorial coordinates
        eps=23.439281;

        cx1=cos(beta*pi/180.0)*cos(lambda*pi/180.0);
        cy1=-sin(eps*pi/180.0)*sin(beta*pi/180.0)...
            +cos(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        cz1=cos(eps*pi/180.0)*sin(beta*pi/180.0)...
            +sin(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        dec=180.0*asin(cz1)/pi;
        alpha=180.0*atan2(cy1,cx1)/pi;
        if(alpha<0.0)
            alpha=alpha+360.0;
        end
        if(alpha>=360.0)
            alpha=alpha-360.0;
        end

        all_data_dec(DOY,HH+1) = dec;
        all_data_alpha(DOY,HH+1) = alpha;

        % convert from dec and alpha to phi and theta;
        phi = 0;
        theta = 0;
        [phi,theta,alpha,dec]= hcec(phi,theta,alpha,dec,astro.startheta,1,-1,meteor.lat);

        meteor.phi=phi;
        meteor.theta=theta;
        all_data_phi(DOY,HH+1) = phi;
        all_data_theta(DOY,HH+1) = theta;

    end
end

%end

all_data_theta_antiapex = all_data_theta;
all_data_phi_antiapex = all_data_phi;

YY = year_index(1);
all_data_phi = NaN(365,24);
all_data_theta = NaN(365,24);
all_data_dec = NaN(365,24);
all_data_alpha = NaN(365,24);
all_data_lambda = NaN(365,24);
all_data_beta = NaN(365,24);
for DOY = 1 : 365;
    tx1 = find([DAYSOFYEAR]<=DOY); tx1 = max(tx1);
    MM = mm_index(tx1);
    DD = DOY-DAYSOFYEAR(tx1);
    for HH = HH_index(1):HH_index(end);
        meteor.time=datenum(YY,MM,DD,HH,00,00);
        meteor.alt=90;%110.4;
        meteor.vel=55;%28.54;

        alpha=0;%127.17;
        dec=0;%18.35;

        if DOY==1;
            lambda = lambda_helion + DOY_lambda(1+HH);
        end
        if DOY>1 & DOY<365;
            lambda = lambda_helion + DOY_lambda((DOY-1)*24+HH+1);
        end
        if DOY==365;
            if HH == 23;
                lambda = lambda_helion + DOY_lambda(1);
            end
        end
        beta = beta_helion;
        all_data_lambda(DOY,HH+1) = lambda;
        all_data_beta(DOY,HH+1) = beta;

        [astro]=startimeJ2000(meteor.time,meteor.long);

        % convert from lambda and beta to dec and alpha;
        %Coordinate Transformation from ecliptic to equatorial coordinates
        eps=23.439281;

        cx1=cos(beta*pi/180.0)*cos(lambda*pi/180.0);
        cy1=-sin(eps*pi/180.0)*sin(beta*pi/180.0)...
            +cos(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        cz1=cos(eps*pi/180.0)*sin(beta*pi/180.0)...
            +sin(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        dec=180.0*asin(cz1)/pi;
        alpha=180.0*atan2(cy1,cx1)/pi;
        if(alpha<0.0)
            alpha=alpha+360.0;
        end
        if(alpha>=360.0)
            alpha=alpha-360.0;
        end

        all_data_dec(DOY,HH+1) = dec;
        all_data_alpha(DOY,HH+1) = alpha;

        % convert from dec and alpha to phi and theta;
        phi = 0;
        theta = 0;
        [phi,theta,alpha,dec]= hcec(phi,theta,alpha,dec,astro.startheta,1,-1,meteor.lat);

        meteor.phi=phi;
        meteor.theta=theta;
        all_data_phi(DOY,HH+1) = phi;
        all_data_theta(DOY,HH+1) = theta;

    end
end

%end

all_data_theta_helion = all_data_theta;
all_data_phi_helion = all_data_phi;

YY = year_index(1);
all_data_phi = NaN(365,24);
all_data_theta = NaN(365,24);
all_data_dec = NaN(365,24);
all_data_alpha = NaN(365,24);
all_data_lambda = NaN(365,24);
all_data_beta = NaN(365,24);
for DOY = 1 : 365;
    tx1 = find([DAYSOFYEAR]<=DOY); tx1 = max(tx1);
    MM = mm_index(tx1);
    DD = DOY-DAYSOFYEAR(tx1);
    for HH = HH_index(1):HH_index(end);
        meteor.time=datenum(YY,MM,DD,HH,00,00);
        meteor.alt=90;%110.4;
        meteor.vel=55;%28.54;

        alpha=0;%127.17;
        dec=0;%18.35;

        if DOY==1;
            lambda = lambda_antihelion + DOY_lambda(1+HH);
        end
        if DOY>1 & DOY<365;
            lambda = lambda_antihelion + DOY_lambda((DOY-1)*24+HH+1);
        end
        if DOY==365;
            if HH == 23;
                lambda = lambda_antihelion + DOY_lambda(1);
            end
        end
        beta = beta_antihelion;
        all_data_lambda(DOY,HH+1) = lambda;
        all_data_beta(DOY,HH+1) = beta;

        [astro]=startimeJ2000(meteor.time,meteor.long);

        % convert from lambda and beta to dec and alpha;
        %Coordinate Transformation from ecliptic to equatorial coordinates
        eps=23.439281;

        cx1=cos(beta*pi/180.0)*cos(lambda*pi/180.0);
        cy1=-sin(eps*pi/180.0)*sin(beta*pi/180.0)...
            +cos(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        cz1=cos(eps*pi/180.0)*sin(beta*pi/180.0)...
            +sin(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        dec=180.0*asin(cz1)/pi;
        alpha=180.0*atan2(cy1,cx1)/pi;
        if(alpha<0.0)
            alpha=alpha+360.0;
        end
        if(alpha>=360.0)
            alpha=alpha-360.0;
        end

        all_data_dec(DOY,HH+1) = dec;
        all_data_alpha(DOY,HH+1) = alpha;

        % convert from dec and alpha to phi and theta;
        phi = 0;
        theta = 0;
        [phi,theta,alpha,dec]= hcec(phi,theta,alpha,dec,astro.startheta,1,-1,meteor.lat);

        meteor.phi=phi;
        meteor.theta=theta;
        all_data_phi(DOY,HH+1) = phi;
        all_data_theta(DOY,HH+1) = theta;

    end
end

%end

all_data_theta_antihelion = all_data_theta;
all_data_phi_antihelion = all_data_phi;

YY = year_index(1);
all_data_phi = NaN(365,24);
all_data_theta = NaN(365,24);
all_data_dec = NaN(365,24);
all_data_alpha = NaN(365,24);
all_data_lambda = NaN(365,24);
all_data_beta = NaN(365,24);
for DOY = 1 : 365;
    tx1 = find([DAYSOFYEAR]<=DOY); tx1 = max(tx1);
    MM = mm_index(tx1);
    DD = DOY-DAYSOFYEAR(tx1);
    for HH = HH_index(1):HH_index(end);
        meteor.time=datenum(YY,MM,DD,HH,00,00);
        meteor.alt=90;%110.4;
        meteor.vel=55;%28.54;

        alpha=0;%127.17;
        dec=0;%18.35;

        if DOY==1;
            lambda = lambda_SToroidal + DOY_lambda(1+HH);
        end
        if DOY>1 & DOY<365;
            lambda = lambda_SToroidal + DOY_lambda((DOY-1)*24+HH+1);
        end
        if DOY==365;
            if HH == 23;
                lambda = lambda_SToroidal + DOY_lambda(1);
            end
        end
        beta = beta_SToroidal;
        all_data_lambda(DOY,HH+1) = lambda;
        all_data_beta(DOY,HH+1) = beta;

        [astro]=startimeJ2000(meteor.time,meteor.long);

        % convert from lambda and beta to dec and alpha;
        %Coordinate Transformation from ecliptic to equatorial coordinates
        eps=23.439281;

        cx1=cos(beta*pi/180.0)*cos(lambda*pi/180.0);
        cy1=-sin(eps*pi/180.0)*sin(beta*pi/180.0)...
            +cos(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        cz1=cos(eps*pi/180.0)*sin(beta*pi/180.0)...
            +sin(eps*pi/180.0)*cos(beta*pi/180.0)*sin(lambda*pi/180.0);
        dec=180.0*asin(cz1)/pi;
        alpha=180.0*atan2(cy1,cx1)/pi;
        if(alpha<0.0)
            alpha=alpha+360.0;
        end
        if(alpha>=360.0)
            alpha=alpha-360.0;
        end

        all_data_dec(DOY,HH+1) = dec;
        all_data_alpha(DOY,HH+1) = alpha;

        % convert from dec and alpha to phi and theta;
        phi = 0;
        theta = 0;
        [phi,theta,alpha,dec]= hcec(phi,theta,alpha,dec,astro.startheta,1,-1,meteor.lat);

        meteor.phi=phi;
        meteor.theta=theta;
        all_data_phi(DOY,HH+1) = phi;
        all_data_theta(DOY,HH+1) = theta;

    end
end

%end

all_data_theta_SToroidal = all_data_theta;
all_data_phi_SToroidal = all_data_phi;

%
%
%%
%%%
%%%%
%%%%%
%%%%
%%%
%%
%
%
%% combined and scaled;
ZZ1 = all_data_theta_apex;
ZZ2 = all_data_theta_antiapex;
ZZ3 = all_data_theta_helion;
ZZ4 = all_data_theta_antihelion;
ZZ5 = all_data_theta_SToroidal;

figure
yy = [0:23];%hour_list;
xx = [1:365];%DOY_list;[XX,YY] = meshgrid(xx,yy);
[XX,YY] = meshgrid(xx,yy);
ZZ = NaN(size(ZZ1));
for i = 1 : size(ZZ1,1);
    for j = 1 : size(ZZ1,2);
        ZZ(i,j) = 10/100*ZZ1(i,j) + 10/100*ZZ2(i,j) + 35/100*ZZ3(i,j) + 35/100*ZZ4(i,j) + 10/100*ZZ5(i,j);
    end
end
hold on,pcolor(XX,YY,ZZ');
xlim([0 365])
ylim([0 23])
set(gca,'FontSize',16)
xlabel('DOY')
ylabel('UTC')
title('DAV: combined astro sources')
a=colorbar;ylabel(a,'\theta','FontSize',16,'Rotation',270);
caxis([-90 90])

ZZ_Davis_combined = ZZ;
%save('ZZ_Davis_combined__Jun21st2022.mat','ZZ_Davis_combined','-v7.3','-nocompression')
