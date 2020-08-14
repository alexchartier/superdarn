function freq = elec2freq(elec)
%% Convert electron density to critical frequency
freq = sqrt(80.6 * elec);