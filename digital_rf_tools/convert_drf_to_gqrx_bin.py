import digital_rf as drf, numpy as np
import os

src = "/Users/chartat1/data/hf_data/b200_test/recorder/2025_12_12_15_03_24/"   # folder with the HDF5 chunks
chan = "cha"             # change to your channel name
out = "~/Downloads/iq.cfile"
src = os.path.expanduser(src)
out = os.path.expanduser(out)
os.makedirs(os.path.dirname(out), exist_ok=True)

r = drf.DigitalRFReader(src)
props = r.get_properties(chan)
sr = props["samples_per_second"]
start, stop = r.get_bounds(chan)
step = 1024 * 1024

with open(out, "wb") as f:
    for i in range(start, stop, step):
        n = min(step, stop - i)
        data = r.read_vector(i, n, chan)
        if data is None:
            data = np.zeros(n, np.complex64)
        data.astype(np.complex64).tofile(f)

print(f"Sample rate: {sr} Hz")
