#!/usr/bin/env python3
"""
Compatibility helpers for standard DigitalRF and flat `channel/Data/rf@*.h5`
recordings.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import digital_rf as drf
import h5py
import numpy as np


def _decode_attr(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.generic):
        return value.item()
    return value


@dataclass(frozen=True)
class _Block:
    path: Path
    start_sample: int
    stop_sample: int
    data_start: int
    data_stop: int


class FlatDataDigitalRFReader:
    def __init__(self, dataset_root: Path, channel: str | None = None) -> None:
        self.dataset_root = Path(dataset_root).expanduser()
        self.channel_name, self.channel_dir = self._resolve_channel_dir(self.dataset_root, channel)
        self.data_dir = self.channel_dir / "Data"
        props_path = self.channel_dir / "drf_properties.h5"
        if not props_path.exists():
            raise FileNotFoundError(f"Missing {props_path}")
        if not self.data_dir.is_dir():
            raise FileNotFoundError(f"Missing {self.data_dir}")

        with h5py.File(props_path, "r") as f:
            self.properties = {k: _decode_attr(v) for k, v in f.attrs.items()}

        if "samples_per_second" not in self.properties:
            num = float(self.properties["sample_rate_numerator"])
            den = float(self.properties["sample_rate_denominator"])
            self.properties["samples_per_second"] = num / den
        if "sample_rate_hz" not in self.properties:
            self.properties["sample_rate_hz"] = float(self.properties["samples_per_second"])

        self._blocks = self._scan_blocks()
        if not self._blocks:
            raise RuntimeError(f"No rf@*.h5 blocks found in {self.data_dir}")

    @staticmethod
    def _resolve_channel_dir(dataset_root: Path, channel: str | None) -> tuple[str, Path]:
        if (dataset_root / "drf_properties.h5").exists():
            channel_name = dataset_root.name
            return channel_name, dataset_root

        if channel is None:
            channel_dirs = sorted(
                p for p in dataset_root.iterdir() if p.is_dir() and (p / "drf_properties.h5").exists()
            )
            if not channel_dirs:
                raise RuntimeError(f"No channel directory with drf_properties.h5 found in {dataset_root}")
            channel_dir = channel_dirs[0]
            return channel_dir.name, channel_dir

        channel_dir = dataset_root / channel
        if not channel_dir.exists() and channel == "cha":
            channel_dirs = sorted(
                p for p in dataset_root.iterdir() if p.is_dir() and (p / "drf_properties.h5").exists()
            )
            if channel_dirs:
                channel_dir = channel_dirs[0]
                return channel_dir.name, channel_dir
        if not (channel_dir / "drf_properties.h5").exists():
            raise RuntimeError(f"Channel directory {channel_dir} does not contain drf_properties.h5")
        return channel, channel_dir

    def _scan_blocks(self) -> list[_Block]:
        blocks: list[_Block] = []
        for path in sorted(self.data_dir.glob("rf@*.h5")):
            with h5py.File(path, "r") as f:
                rf_data = f["rf_data"]
                total_samples = int(rf_data.shape[0])
                rf_index = np.asarray(f["rf_data_index"])
                if rf_index.size == 0:
                    continue
                for i in range(rf_index.shape[0]):
                    start_sample = int(rf_index[i][0])
                    data_start = int(rf_index[i][1])
                    next_data_start = int(rf_index[i + 1][1]) if i + 1 < rf_index.shape[0] else total_samples
                    data_stop = next_data_start - 1
                    if data_stop < data_start:
                        continue
                    stop_sample = start_sample + (data_stop - data_start)
                    blocks.append(
                        _Block(
                            path=path,
                            start_sample=start_sample,
                            stop_sample=stop_sample,
                            data_start=data_start,
                            data_stop=data_stop,
                        )
                    )
        blocks.sort(key=lambda b: (b.start_sample, b.path.name, b.data_start))
        return blocks

    def get_channels(self) -> list[str]:
        return [self.channel_name]

    def get_properties(self, channel_name: str, sample: int | None = None) -> dict[str, Any]:
        self._check_channel(channel_name)
        _ = sample
        return self.properties.copy()

    def get_bounds(self, channel_name: str) -> tuple[int | None, int | None]:
        self._check_channel(channel_name)
        if not self._blocks:
            return (None, None)
        return (self._blocks[0].start_sample, self._blocks[-1].stop_sample)

    def get_continuous_blocks(self, start: int, stop: int, channel_name: str) -> OrderedDict[int, int]:
        self._check_channel(channel_name)
        merged: list[list[int]] = []
        for block in self._blocks:
            lo = max(start, block.start_sample)
            hi = min(stop, block.stop_sample)
            if hi < lo:
                continue
            if not merged or lo > merged[-1][1] + 1:
                merged.append([lo, hi])
            else:
                merged[-1][1] = max(merged[-1][1], hi)
        out: OrderedDict[int, int] = OrderedDict()
        for lo, hi in merged:
            out[int(lo)] = int(hi - lo + 1)
        return out

    def read_vector_1d(self, start: int, count: int, channel_name: str) -> np.ndarray:
        self._check_channel(channel_name)
        if count <= 0:
            return np.array([], dtype=np.complex64)

        stop = start + count - 1
        pieces: list[np.ndarray] = []
        cursor = start

        for block in self._blocks:
            if block.stop_sample < cursor:
                continue
            if block.start_sample > stop:
                break
            if block.start_sample > cursor:
                raise OSError(f"Gap in requested span at sample {cursor}")

            lo = max(cursor, block.start_sample)
            hi = min(stop, block.stop_sample)
            if hi < lo:
                continue

            file_lo = block.data_start + (lo - block.start_sample)
            file_hi = block.data_start + (hi - block.start_sample) + 1
            with h5py.File(block.path, "r") as f:
                raw = f["rf_data"][file_lo:file_hi]
            real = raw["r"].astype(np.float32, copy=False).reshape(-1)
            imag = raw["i"].astype(np.float32, copy=False).reshape(-1)
            pieces.append(real + 1j * imag)
            cursor = hi + 1
            if cursor > stop:
                break

        if cursor <= stop:
            raise OSError(f"Requested span [{start}, {stop}] is not fully covered by contiguous data")

        if len(pieces) == 1:
            return pieces[0].astype(np.complex64, copy=False)
        return np.concatenate(pieces).astype(np.complex64, copy=False)

    def _check_channel(self, channel_name: str) -> None:
        if channel_name != self.channel_name:
            raise RuntimeError(f"Channel {channel_name!r} not available; expected {self.channel_name!r}")


def open_drf_like_reader(dataset_root: Path, channel: str | None = None) -> tuple[Any, str, str]:
    dataset_root = Path(dataset_root).expanduser()

    try:
        reader = drf.DigitalRFReader(str(dataset_root))
        channels = reader.get_channels()
        if channels:
            resolved_channel = channel or channels[0]
            if resolved_channel in channels:
                start, stop = reader.get_bounds(resolved_channel)
                if start is not None and stop is not None:
                    return reader, resolved_channel, "digital_rf"
    except Exception:
        pass

    flat_reader = FlatDataDigitalRFReader(dataset_root, channel=channel)
    return flat_reader, flat_reader.get_channels()[0], "flat_data"
