# HFDL Detection (rawrf)

This folder contains a thin wrapper around `dumphfdl` that streams IQ samples from an HDF5 raw RF file into the decoder.

## Usage

```bash
./detect_hfdl.py \
  --input /project/superdarn/data/rawrf/20260212.2005.21.wal.rawrf.h5 \
  --dataset /path/to/iq_dataset \
  --sample-rate-hz 48000 \
  --center-freq-khz 8906.0 \
  --systable /path/to/dumphfdl/etc/systable.conf
```

Notes:
- If `--dataset` is omitted, the script picks the largest numeric dataset.
- If `--sample-rate-hz` and `--center-freq-khz` are omitted, the script tries to infer them from HDF5 attributes.
- Provide `--freqs-khz` to pass explicit channel frequencies instead of a systable.

## Requirements
- `python3` with `h5py` and `numpy`
- `dumphfdl` installed and in `PATH` (or use `--dumphfdl /path/to/dumphfdl`)

## Polar FOV Plotter

`plot_fitacf_fov.py` rebuilds the Wallops-style polar power and Doppler plots from either a Borealis realtime fitacf PUB socket, an offline `.fitacf[.bz2]` file, or an offline `.rawacf[.bz2]` file that it fits on the fly.

Example live capture:

```bash
./plot_fitacf_fov.py \
  --socket tcp://192.168.112.127:9696 \
  --cp 151 \
  --duration-s 60 \
  --radar wal \
  --mode-label normalscan \
  --output plots/wal_normalscan_polar_power_doppler.png
```

Example offline replay:

```bash
./plot_fitacf_fov.py \
  --input /path/to/file.fitacf.bz2 \
  --cp 151 \
  --radar wal \
  --mode-label normalscan
```

Example offline rawacf replay with 12-scan accumulation:

```bash
./plot_fitacf_fov.py \
  --input /data/borealis_data_dev_wal/20260310/20260310.2019.47.wal.a.rawacf \
  --cp 3801 \
  --radar wal \
  --mode-label fullfov \
  --accumulate-scans 12
```

Plotter requirements:
- `python3` with `matplotlib`, `numpy`, and `pydarnio`
- `backscatter` when using offline `rawacf`
- `pyzmq` only when using `--socket`

## Antennas IQ Polar Plotter

`plot_antennas_iq_fov.py` renders the same polar power/Doppler format directly from Borealis `antennas_iq` files using the scheduled receive weights for standard beamforming. It supports optional rectangular or Barker-13 matched filtering before beamforming.

Example offline Barker replay:

```bash
./plot_antennas_iq_fov.py \
  --input /data/borealis_data_dev_wal/20260311/20260311.1832.22.wal.0.antennas_iq.h5 \
  --matched-filter barker13 \
  --output plots/wal_fullfov_barker13_sched_bf_polar.png
```

Requirements:
- `python3` with `h5py`, `matplotlib`, and `numpy`

## Limitations
- The script expects IQ samples as one of:
  - complex64 (CF32)
  - float32 I/Q interleaved (CF32)
  - int16 I/Q interleaved (CS16)
  - uint8 I/Q interleaved (U8)
- Other formats will require an explicit conversion step.
