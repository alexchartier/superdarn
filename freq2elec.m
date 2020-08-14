function elec = freq2elec(freq)
%% Convert critical frequency to electron density
elec = freq .^ 2 / 80.6;