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
hrs = hrs(:)';                     % force row vector
[n_hr, n_col] = size(winds);
if n_hr ~= numel(hrs)
    error('UT_to_LT:DimMismatch', 'winds first dimension (%d) must match hrs length (%d)', n_hr, numel(hrs));
end

% local time hours, wrapped to [0,24)
lthrs = hrs + lon/360 * 24;
lthrs(lthrs >= 24) = lthrs(lthrs >= 24) - 24;
lthrs(lthrs < 0) = lthrs(lthrs < 0) + 24;

% sort for monotonic interpolation
[lthrs_sort, si] = sort(lthrs);
winds_sort = winds(si, :);

L = numel(lthri);
LTwinds = nan(L, n_col);

for cc = 1:n_col
    ws = winds_sort(:, cc);
    % periodic extension to cover wrap-around
    lt_ext = [lthrs_sort(:); lthrs_sort(1) + 24];
    ws_ext = [ws(:); ws(1)];
    LTwinds(:, cc) = interp1(lt_ext, ws_ext, lthri, 'linear', 'extrap');
end
