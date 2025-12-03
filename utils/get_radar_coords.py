import sd_utils
hdw_dat_dir = '~/rst/tables/superdarn/hdw/'
radar_params = sd_utils.get_radar_params(hdw_dat_dir)
for k, v in radar_params.items():
    f = next(iter(v))
    print('%1.2f %1.2f' % (v[f]['glat'], v[f]['glon']))


for k, v in radar_params.items():
    f = next(iter(v))
    print("'%s', " % k, end="")
    print('\n')

