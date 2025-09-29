lla = [69.2, 16.1, 90];
ecef = lla2ecef(lla);
[eci, eci_dv] = ecef2eci(datetime(2008, 1, 1, 0, 0, 0), ecef, [0, 0, 0]);

eci_km = eci/1E3;
eci_dv_km = eci_dv / 1E3;

fprintf('%1.4f %1.4f %1.4f %1.4f %1.4f %1.4f %1.4f\n', eci_km, eci_dv_km)