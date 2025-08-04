function weighted_angular_mean_deg = meanangle(angles_deg, weights);

% Convert angles to radians
angles_rad = deg2rad(angles_deg);

% Convert angles to unit vectors
x_components = cos(angles_rad);
y_components = sin(angles_rad);

% Apply weights
weighted_x = x_components .* weights;
weighted_y = y_components .* weights;

% Sum the weighted components
sum_weighted_x = sum(weighted_x);
sum_weighted_y = sum(weighted_y);

% Convert back to an angle (in radians)
weighted_angular_mean_rad = atan2(sum_weighted_y, sum_weighted_x);

% Convert back to degrees (if needed)
weighted_angular_mean_deg = rad2deg(weighted_angular_mean_rad);

% 0-360 limit
weighted_angular_mean_deg(weighted_angular_mean_deg < 0) = ...
    weighted_angular_mean_deg(weighted_angular_mean_deg < 0) + 360;