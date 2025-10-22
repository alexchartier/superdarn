%% inputs
radar_names = {'McMurdo', 'CONDOR'};
yrs = {[2018, 2019], 2020:2023};
fn_fmt = {['~/data/meteor_winds/madrigal/McMurdo_Meteor_Radar/',...
    'mcr{yyyy}*_001.hdf5.nc'], ...
    ['~/data/meteor_winds/madrigal/',...
    'CONDOR_multi-static_meteor_radar_system/alo{yyyy}*_001.hdf5.nc']};

out_fn_fmt = '~/data/meteor_winds/mat/{NAME}_{yyyy}.mat';

%% Loop through and store
for ri = 1:length(radar_names)
    for yi = 1:length(yrs{ri})
        clear data_full out
        time = datenum(yrs{ri}(yi), 1, 1);
        flist = dir(filename(fn_fmt{ri}, time));
        for fi = 1:length(flist)
            data = load_nc([flist(fi).folder, '/', flist(fi).name]);
            if fi == 1
                data_full = data;
                vn = fieldnames(data);
                lat = str2double(ncreadatt([flist(fi).folder, '/', ...
                    flist(fi).name] , '/', 'instrument_latitude'));
                lon = str2double(ncreadatt([flist(fi).folder, '/', ...
                    flist(fi).name] , '/', 'instrument_longitude'));
            else
                try
                    for vni = 1:length(vn)

                        data_full.(vn{vni}) = cat(3, data_full.(vn{vni}), data.(vn{vni}));
                    end
                catch
                    continue
                end
            end
        end

        out.Time = datenum(datetime(squeeze(data_full.timestamps), ...
            'ConvertFrom', 'posixtime'));
        out.counts = data_full.met_count;
        out.alt = squeeze(data_full.gdalt(:, 1, 1));
        out.lat = lat;
        out.lon = lon;

        out_fn = filename(out_fn_fmt, time, radar_names{ri});
        savestruct(out_fn, out)
        fprintf('Saved to %s\n', out_fn)
    end
end