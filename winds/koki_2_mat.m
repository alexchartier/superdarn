%% inputs

yrs = [2008, 2020];

koki_radars = {'And', 'Jul'};
koki_fn_fmt = {'~/data/meteor_winds/SMR_{NAME}_{NAME}_32_{yyyymmdd}', ...
    '_{yyyymmdd}.h5'};
koki_mat_fn_fmt = '~/data/meteor_winds/mat/{NAME}_{yyyy}.mat';


%% convert
for i = 1:length(yrs)
    mwr_times = datenum(yrs(i), 1, 1):datenum(yrs(i), 12, 31);
    for j = 1:length(koki_radars)
        koki_fn = [filename(koki_fn_fmt{1}, min(mwr_times), koki_radars{j}), ...
            filename(koki_fn_fmt{2}, max(mwr_times), koki_radars{j})];
        mwr = load_mwr_simple(koki_fn);

        savestruct(filename(koki_mat_fn_fmt, min(mwr_times), ...
            koki_radars{j}), mwr)

    end
end


