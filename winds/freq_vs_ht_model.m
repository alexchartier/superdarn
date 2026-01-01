function ht_mod = freq_vs_ht_model(freq_obs, ht_obs, freq_ref)
%% Calculate meteor peak height shifts to a reference frequency
%
% Example shows calculation of the parameters based on Steel & Elford
% (1991)
% freq = [6, 24.5, 54.1];
% ht = [106, 98, 94];
% semilogx(freq, ht, '-kx', 'MarkerSize', 15)
%
%
% p = polyfit(log10(freq), ht, 1);
% m = p(1);
% c = p(2);
%
% ht_est = m .* log10(freq) + c;  % check the model is getting close
%
%
%

%% calculate peak height shifts based on the simple Steel & Elford-based model 

m = -12.6262;
hshift = m .* log10(freq_ref ./ freq_obs);
ht_mod = ht_obs + hshift;
