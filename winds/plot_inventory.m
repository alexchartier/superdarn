%% 

datadir = '~/data/superdarn/meteorwindnc/';
%% Create inventory
sitenames = [];
times = [];
yrlist = dir(datadir);
for yi = 3:length(yrlist)
    monthlist = dir([datadir, '/', yrlist(yi).name]);
    for mi = 3:length(monthlist)
        flist = dir([monthlist(mi).folder, '/', monthlist(mi).name]);

        for fi = 3:length(flist)
            filename = flist(fi).name;
            parts = strsplit(filename, '.');
            time = datetime(parts{1}, "InputFormat", 'yyyyMMMdd');
            sitename = parts{2};
            sitenames = [sitenames, {sitename}];
            times = [times, time];

        end

    end
end


%% 
close all
sitelist = unique(sitenames);
timelist = min(times):max(times);
arr = nan([length(timelist), length(sitelist)]);
for si = 1:length(sitelist)
    ti = ismember(timelist, times(ismember(sitenames, {sitelist{si}})));
    arr(ti, si) = 1;
end

hC = pcolor(timelist, 0:37, arr');
xlabel('Year')
ylabel('Site Name')
yticks([0.5:37.5]);
yticklabels(upper(sitelist));
set(hC, 'LineStyle', 'None')
grid on
grid minor