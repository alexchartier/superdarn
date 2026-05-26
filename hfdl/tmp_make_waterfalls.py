import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA_ROOT = "/project/superdarn/data/rawrf/rawrf_14600_2p5m_aa"
OUT_DIR = os.path.join(DATA_ROOT, "waterfalls")

FS = 2.5e6
CENTER_HZ = 14.6e6
NFFT = 4096
HOP = 4096
SKIP = 200  # take every Nth hop to keep plots small


def make_waterfall(channel: str, path: str) -> str | None:
    data = np.memmap(path, dtype=np.complex64, mode="r")
    total = data.size
    step = HOP * SKIP
    n_frames = int((total - NFFT) // step)
    if n_frames <= 0:
        return None

    window = np.hanning(NFFT).astype(np.float32)
    specs = []
    for i in range(n_frames):
        start = i * step
        seg = data[start : start + NFFT]
        if seg.size < NFFT:
            break
        seg = seg * window
        spec = np.fft.fftshift(np.fft.fft(seg))
        power = 20.0 * np.log10(np.abs(spec) + 1e-12)
        specs.append(power)

    if not specs:
        return None

    spec_arr = np.stack(specs, axis=1)  # freq x time
    spec_arr = spec_arr - np.median(spec_arr)

    time_axis = np.arange(spec_arr.shape[1]) * step / FS
    freq_axis = np.linspace(-FS / 2, FS / 2, NFFT, endpoint=False) / 1e6

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"waterfall_{channel}.png")

    plt.figure(figsize=(10, 6), dpi=150)
    plt.imshow(
        spec_arr,
        aspect="auto",
        origin="lower",
        extent=[time_axis[0], time_axis[-1], freq_axis[0], freq_axis[-1]],
        cmap="viridis",
    )
    plt.xlabel("Time (s)")
    plt.ylabel("Frequency offset (MHz)")
    plt.title(f"{channel} @ {CENTER_HZ/1e6:.3f} MHz")
    plt.colorbar(label="dB (median-normalized)")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()

    return out_path


def main() -> None:
    channels = []
    for name in sorted(os.listdir(DATA_ROOT)):
        ch_dir = os.path.join(DATA_ROOT, name)
        if not os.path.isdir(ch_dir):
            continue
        cf32 = os.path.join(ch_dir, "rawrf_continuous.cf32")
        if os.path.isfile(cf32):
            channels.append((name, cf32))

    if not channels:
        raise SystemExit("no channels found")

    for channel, path in channels:
        out_path = make_waterfall(channel, path)
        if out_path:
            print(out_path)


if __name__ == "__main__":
    main()
