import numpy as np
import matplotlib.pyplot as plt


lon = np.linspace(0, 360, 36)
amp = 1
phase = 5
s = 1
t = 0

t = 12  # hour (UT)
s = 2  # wavenumber
# phase_at_lon = phase + dirn_multiplier * s * lon / 360 * 24

wind_jens = amp * np.cos(np.pi / 12. * t - s * lon *
                         np.pi / 180. - phase * np.pi / 12)
# wind_alex = amp * np.cos((phase_at_lon - t * ds_multiplier)  / 24 * np.pi * 2)
wind_al_j = amp * np.cos(np.pi / 12 * (t - phase - s * lon / 360 * 24))

plt.plot(lon, wind_jens)
plt.plot(lon, wind_al_j)
plt.show()
