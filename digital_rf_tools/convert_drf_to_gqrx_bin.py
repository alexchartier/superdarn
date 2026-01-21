#!/usr/bin/env python3
"""
Convert a DigitalRF channel into a Gqrx-compatible complex float (.cfile).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import digital_rf as drf
import numpy as np

DEFAULT_SRC = "/Users/chartat1/data/hf_data/b200_test/recorder/2025_12_12_15_03_24/"
DEFAULT_CHANNEL = "cha"
DEFAULT_OUTPUT = "~/Downloads/iq.cfile"
DEFAULT_STEP = 1024 * 1024


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert a DigitalRF channel to a Gqrx .cfile.")
    p.add_argument(
        "--src",
        type=Path,
        default=Path(DEFAULT_SRC).expanduser(),
        help="DigitalRF dataset root containing HDF5 chunks. Default: /Users/chartat1/data/hf_data/b200_test/recorder/2025_12_12_15_03_24/.",
    )
    p.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: cha.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT).expanduser(),
        help="Output .cfile path. Default: ~/Downloads/iq.cfile.",
    )
    p.add_argument(
        "--step",
        type=int,
        default=DEFAULT_STEP,
        help=f"Read block size in samples. Default: {DEFAULT_STEP}.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    src = args.src.expanduser()
    out = args.output.expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    reader = drf.DigitalRFReader(str(src))
    props = reader.get_properties(args.channel)
    sr = props["samples_per_second"]
    start, stop = reader.get_bounds(args.channel)

    with open(out, "wb") as f:
        for i in range(start, stop, args.step):
            n = min(args.step, stop - i)
            data = reader.read_vector(i, n, args.channel)
            if data is None:
                data = np.zeros(n, np.complex64)
            data.astype(np.complex64).tofile(f)

    print(f"Sample rate: {sr} Hz")


if __name__ == "__main__":
    main()
