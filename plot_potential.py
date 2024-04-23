import matplotlib.pyplot as plt
import numpy as np
from nc_utils import ncread_vars
import datetime as dt
import pdb


def main():
    starttime = dt.datetime(2014, 5, 21, 3, 0)
    endtime = dt.datetime(2014, 5, 28)
    timestep = dt.timedelta(hours=3)
    in_fname_fmt = 'data/pot_sami_cond/may14/ampere_mix_%Y-%m-%dT%H-%M-00Z.nc'
    out_fname_fmt = 'data/plots/sami_cond/may14/sami_%Y%b%d_%H%M.png'
    titlestr_fmt = '%Y%b%d %H:%M'
    time = starttime

    while time < endtime:
        in_fname = time.strftime(in_fname_fmt)
        out_fname = time.strftime(out_fname_fmt)
        titlestr = time.strftime(titlestr_fmt)
        plot_pot_etc(in_fname, titlestr, out_fname)
        time += timestep


def plot_pot_etc(
        in_fname, title,
        out_fname=None,
        facmax=1.5,
        potmax=50,
        condmax=20,
):
    vars = ncread_vars(in_fname)
    fig, ax = plt.subplots(2, 2, subplot_kw=dict(
        projection='polar'), figsize=(12, 8))
    th = np.rad2deg(np.unique(vars['Colatitude']))
    ph = np.unique(vars['Longitude'])
    plt.suptitle(title)
    for a in range(2):
        for b in range(2):
            ax[a, b].set_theta_zero_location("N")

    # FACs
    im = ax[0, 0].pcolor(ph, th, vars['FAC'], cmap='bwr',
                         vmin=-facmax, vmax=facmax)
    cs = ax[0, 0].contour(ph, th, vars['Potential'], 8, colors='k')
    cbar = fig.colorbar(im, ax=ax[0, 0])
    cbar.set_label(r'Radial current density ($\mu A/m^2$)')
    plt.clabel(cs, inline=1, fmt='%1.0f', fontsize=10)

    # Potential
    im = ax[0, 1].pcolor(ph, th, vars['Potential'],
                         cmap='jet', vmin=-potmax, vmax=potmax)
    exb = np.gradient(np.array(vars['Potential']))
    cs = ax[0, 1].contour(ph, th, vars['Potential'], 8, colors='k')
    cbar = fig.colorbar(im, ax=ax[0, 1])
    cbar.set_label('Electric Potential (kV)')
    # plt.clabel(cs, inline=1, fmt='%1.0f', fontsize=10)

    # Conductances
    conds = 'Pedersen conductance', 'Hall conductance'
    for ind, cond in enumerate(conds):
        im = ax[1, ind].pcolor(ph, th, vars[cond], vmin=0, vmax=condmax)
        cbar = fig.colorbar(im, ax=ax[1, ind])
        cbar.set_label(cond + ' (S)')

    # Reset yticks to lat from colat
    for axis in ax.flatten():
        new_yticks = 90 - np.array(axis.get_yticks())
        axis.set_yticklabels(new_yticks)
        axis.grid(True)
    plt.tight_layout()

    if out_fname:
        plt.savefig(out_fname)
        print('Saved to %s' % out_fname)
    else:
        plt.show()
    plt.close()


if __name__ == '__main__':
    main()
