function D = within2pi(D)


while sum(D > 2*pi) > 0
    D(D >= 2 * pi) = D(D >= 2 * pi) - 2 * pi;
end
while sum(D < 0) > 0
    D(D < 0) = D(D < 0) + 2 * pi;
end