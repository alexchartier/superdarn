#!/usr/bin/env python3
"""
Extract audio snippets around WWV tick detections in a selected range band.

The input CSV is expected to contain the detection rows from detect_wwv_ticks.py.
This script converts the CSV sample indices into positions in the demodulated WAV
and concatenates short windows around each hit that falls inside a range band.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from scipy.io import wavfile


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gate WWV audio by detected range band.")
    p.add_argument("--input-wav", type=Path, required=True, help="Input mono WAV file.")
    p.add_argument("--input-csv", type=Path, required=True, help="Detection CSV from detect_wwv_ticks.py.")
    p.add_argument("--output-wav", type=Path, required=True, help="Output WAV file.")
    p.add_argument("--range-min-km", type=float, required=True, help="Inclusive minimum range (km).")
    p.add_argument("--range-max-km", type=float, required=True, help="Inclusive maximum range (km).")
    p.add_argument(
        "--channel-rate",
        type=float,
        required=True,
        help="Detection channel rate used to generate sample_index in the CSV.",
    )
    p.add_argument("--pre-seconds", type=float, default=0.2, help="Seconds to keep before each hit.")
    p.add_argument("--post-seconds", type=float, default=0.3, help="Seconds to keep after each hit.")
    p.add_argument(
        "--merge-gap-seconds",
        type=float,
        default=0.05,
        help="Merge overlapping windows separated by less than this gap.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    rate, audio = wavfile.read(args.input_wav)
    if audio.ndim != 1:
        raise ValueError("Expected mono WAV input.")
    if audio.dtype != np.int16:
        audio = audio.astype(np.int16, copy=False)

    hits: list[int] = []
    with args.input_csv.open(newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("range_km"):
                continue
            range_km = float(row["range_km"])
            if range_km < args.range_min_km or range_km > args.range_max_km:
                continue
            sample_index = int(row["sample_index"])
            hit_sample = int(round(sample_index * rate / args.channel_rate))
            hits.append(hit_sample)

    if not hits:
        raise RuntimeError("No hits found in the requested range band.")

    hits.sort()
    pre = int(round(args.pre_seconds * rate))
    post = int(round(args.post_seconds * rate))
    merge_gap = int(round(args.merge_gap_seconds * rate))

    windows: list[tuple[int, int]] = []
    for hit in hits:
        start = max(0, hit - pre)
        stop = min(audio.shape[0], hit + post)
        if not windows:
            windows.append((start, stop))
            continue
        prev_start, prev_stop = windows[-1]
        if start <= prev_stop + merge_gap:
            windows[-1] = (prev_start, max(prev_stop, stop))
        else:
            windows.append((start, stop))

    chunks = [audio[start:stop] for start, stop in windows if stop > start]
    if not chunks:
        raise RuntimeError("No audio windows survived gating.")

    out = np.concatenate(chunks)
    peak = int(np.max(np.abs(out)))
    if peak > 0:
        scale = min(1.0, 0.95 * 32767.0 / peak)
        out = np.clip(out.astype(np.float32) * scale, -32768, 32767).astype(np.int16)

    args.output_wav.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(args.output_wav, rate, out)

    total_seconds = out.shape[0] / rate
    print(f"Wrote {args.output_wav} ({total_seconds:.1f} s, {len(hits)} hits, {len(windows)} windows)")


if __name__ == "__main__":
    main()
