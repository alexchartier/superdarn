function LTwinds = UT_to_LT(winds, hrs, lthri, lon)
%%
% 
% winds = mwr.Vx_med_avg;
% lon = mwr.lon;
% hrs = mwr.Jul.hour';
% LTwinds = UT_to_LT(winds, hrs, lon)
% tiledlayout(1, 2, 'TileSpacing','compact')
% nexttile
% contourf(winds(1:24, :))
% nexttile
% contourf(LTwinds')

%%
lthrs = hrs + lon/360 * 24;
lthrs(lthrs >= 24) = lthrs(lthrs >= 24) - 24;
lthrs(lthrs < 0) = lthrs(lthrs < 0) + 24;

[lthrs, si] = sort(lthrs);
winds_s = winds(si, :);
winds_s = cat(1,  winds_s(end, :), winds_s, winds_s(1, :));
lthrs = [min(lthrs) - 1, lthrs, max(lthrs) + 1];

LTwinds = interp2(lthrs, 1:size(winds_s, 2), winds_s', ...
    lthri', 1:size(winds, 2))';

