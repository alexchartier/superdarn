%% Calculate frequency-height model from Steel & Elford (1991)

freq = [6, 24.5, 54.1];
ht = [106, 98, 94];

p = polyfit(log10(freq), ht, 1);
m = p(1);
c = p(2);


ht_est = m .* log10(freq) + c;

h1 = 30;
h2 = 12;
hshift = m .* log10(h1/h2);



%% Plotting
semilogx(freq, ht, '-kx', 'MarkerSize', 15)

