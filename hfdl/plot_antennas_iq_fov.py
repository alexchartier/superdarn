#!/usr/bin/env python3
"""Plot scheduled-beam power and Doppler from Borealis antennas_iq files."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


C_MPS = 299792458.0
BARKER13 = np.array([1, 1, 1, 1, 1, -1, -1, 1, 1, -1, 1, -1, 1], dtype=np.float32)


@dataclass(frozen=True)
class MatchedFilterSpec:
    rect_kernel: np.ndarray
    combine_delays: np.ndarray | None = None
    combine_weights: np.ndarray | None = None


def _db(x: np.ndarray) -> np.ndarray:
    return (10.0 * np.log10(np.maximum(np.asarray(x, dtype=np.float32), np.float32(1.0e-12)))).astype(np.float32)


def _parse_records(all_records: list[str], record: str | None, records: int | None) -> list[str]:
    if record is not None:
        if record not in all_records:
            raise ValueError(f"Record {record} not found")
        return [record]
    if records is None or records <= 0 or records >= len(all_records):
        return all_records
    return all_records[-records:]


def _extract_main_array_data(record_group: h5py.Group) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ant_iq = record_group["antennas_iq_data"][...].astype(np.complex64)
    rx_antennas = record_group["rx_antennas"][...].astype(np.int32)
    rx_main_antennas = record_group["rx_main_antennas"][...].astype(np.int32)
    rx_main_excitations = record_group["rx_main_excitations"][...].astype(np.complex64)

    idx_by_ant = {int(ant): i for i, ant in enumerate(rx_antennas.tolist())}

    keep_cols: list[int] = []
    keep_rows: list[int] = []
    keep_ids: list[int] = []
    for col, ant in enumerate(rx_main_antennas.tolist()):
        row = idx_by_ant.get(int(ant))
        if row is None:
            continue
        keep_cols.append(col)
        keep_rows.append(row)
        keep_ids.append(int(ant))

    if not keep_rows:
        raise RuntimeError("No main-array channels found in record")

    main_data = ant_iq[np.asarray(keep_rows, dtype=np.int32), :, :]
    main_weights = rx_main_excitations[:, np.asarray(keep_cols, dtype=np.int32)]
    main_ids = np.asarray(keep_ids, dtype=np.int32)
    return main_data, main_weights, main_ids


def _samples_per_chip(sample_time_us: np.ndarray, chip_us: float) -> int:
    if sample_time_us.size < 2:
        return 1
    dt_us = float(np.median(np.diff(sample_time_us)))
    if dt_us <= 0.0:
        return 1
    return max(1, int(round(chip_us / dt_us)))


def _contiguous_run_lengths(vals: np.ndarray) -> list[int]:
    if vals.size == 0:
        return []
    if vals.size == 1:
        return [1]

    runs: list[int] = []
    run = 1
    for d in np.diff(vals):
        if d == 1:
            run += 1
        else:
            runs.append(run)
            run = 1
    runs.append(run)
    return runs


def _first_contiguous_run_start(vals: np.ndarray, min_len: int) -> int | None:
    if vals.size == 0:
        return None
    start = 0
    run = 1
    for idx, d in enumerate(np.diff(vals), start=1):
        if d == 1:
            run += 1
            if run >= min_len:
                return start
            continue
        start = idx
        run = 1
    if run >= min_len:
        return start
    return None


def _build_kernel_from_weights(chip_samps: int, weights: np.ndarray) -> np.ndarray:
    waveform = np.repeat(np.asarray(weights, dtype=np.complex64), max(1, chip_samps)).astype(np.complex64)
    kernel = np.conj(waveform[::-1])
    norm = np.sqrt(np.sum(np.abs(kernel) ** 2))
    if norm > 0.0:
        kernel = kernel / np.float32(norm)
    return kernel.astype(np.complex64)


def _build_rect_kernel(chip_samps: int) -> np.ndarray:
    kernel = np.ones(max(1, chip_samps), dtype=np.complex64)
    norm = np.sqrt(np.sum(np.abs(kernel) ** 2))
    if norm > 0.0:
        kernel = kernel / np.float32(norm)
    return kernel.astype(np.complex64)


def _pulse_phase_weights(record_group: h5py.Group, pulses: np.ndarray, mf_mode: str) -> np.ndarray:
    if "pulse_phase_offset" in record_group:
        phase_deg = np.asarray(record_group["pulse_phase_offset"][...], dtype=np.float32)
        if phase_deg.ndim == 2:
            if phase_deg.shape[1] != pulses.size:
                raise RuntimeError(
                    f"pulse_phase_offset shape mismatch: phases={phase_deg.shape} pulses={pulses.size}"
                )
            if not np.allclose(phase_deg, phase_deg[:1], atol=1.0e-3):
                raise RuntimeError("Per-sequence pulse_phase_offset varies within a record")
            phase_deg = phase_deg[0]
        elif phase_deg.ndim != 1 or phase_deg.size != pulses.size:
            raise RuntimeError(f"Unsupported pulse_phase_offset shape: {phase_deg.shape}")
        return np.exp(1j * np.deg2rad(phase_deg.astype(np.float32))).astype(np.complex64)

    if mf_mode == "barker13":
        reps = max(1, pulses.size // 13)
        return np.tile(BARKER13, reps)[: pulses.size].astype(np.complex64)

    return np.ones(pulses.size, dtype=np.complex64)


def _build_mf_kernel(
    record_group: h5py.Group, sample_time_us: np.ndarray, mf_mode: str
) -> tuple[MatchedFilterSpec | None, str]:
    if mf_mode == "off":
        return None, "off"

    pulses = record_group["pulses"][...].astype(np.int32) if "pulses" in record_group else np.array([], dtype=np.int32)
    tx_pulse_len_us = float(record_group["tx_pulse_len"][()]) if "tx_pulse_len" in record_group else 0.0
    chip_samps = _samples_per_chip(sample_time_us, max(tx_pulse_len_us, 1.0))

    use_mode = mf_mode
    if mf_mode == "auto":
        runs = _contiguous_run_lengths(pulses)
        if pulses.size >= 13 and (pulses.size % 13 == 0) and runs and all(r == 13 for r in runs):
            use_mode = "barker13"
        else:
            use_mode = "rect"

    rect_kernel = _build_rect_kernel(chip_samps)
    if use_mode == "rect":
        return MatchedFilterSpec(rect_kernel=rect_kernel), use_mode
    elif use_mode == "barker13":
        weights = _pulse_phase_weights(record_group, pulses, use_mode)
        run_start = _first_contiguous_run_start(pulses, 13)
        if run_start is None:
            raise RuntimeError("Could not locate contiguous Barker-13 pulse group")
        code_kernel = _build_kernel_from_weights(chip_samps, weights[run_start : run_start + 13])
        return MatchedFilterSpec(rect_kernel=code_kernel), use_mode
    else:
        raise ValueError(f"Unsupported matched-filter mode: {mf_mode}")


def _apply_matched_filter(data: np.ndarray, mf_spec: MatchedFilterSpec | None) -> np.ndarray:
    if mf_spec is None:
        return data

    rect_filtered = np.empty_like(data)
    for ai in range(data.shape[0]):
        for si in range(data.shape[1]):
            rect_filtered[ai, si, :] = np.convolve(data[ai, si, :], mf_spec.rect_kernel, mode="same")

    if mf_spec.combine_delays is None or mf_spec.combine_weights is None:
        return rect_filtered

    nsamp = rect_filtered.shape[-1]
    valid_delay = mf_spec.combine_delays < nsamp
    delays = mf_spec.combine_delays[valid_delay].astype(np.int32, copy=False)
    weights = mf_spec.combine_weights[valid_delay].astype(np.complex64, copy=False)
    if delays.size == 0:
        return np.zeros_like(rect_filtered)

    out = np.zeros_like(rect_filtered)
    for delay, weight in zip(delays.tolist(), weights.tolist()):
        if delay == 0:
            out += np.conj(np.complex64(weight)) * rect_filtered
        else:
            out[..., :-delay] += np.conj(np.complex64(weight)) * rect_filtered[..., delay:]

    norm = np.sqrt(np.sum(np.abs(weights) ** 2))
    if norm > 0.0:
        out /= np.float32(norm)
    return out.astype(np.complex64)


def _rtt_us_to_range_km(rtt_us: np.ndarray) -> np.ndarray:
    return (np.asarray(rtt_us, dtype=np.float64) * C_MPS / (2.0 * 1.0e9)).astype(np.float32)


def _gate_sample_indices(
    sample_time_us: np.ndarray,
    gate_numbers: np.ndarray,
    range_sep_km: float,
    first_range_rtt_us: float,
) -> np.ndarray:
    gate_rtt_us = first_range_rtt_us + (2.0 * gate_numbers.astype(np.float64) * range_sep_km * 1.0e3 / C_MPS) * 1.0e6
    target_us = gate_rtt_us - first_range_rtt_us
    return np.asarray([int(np.argmin(np.abs(sample_time_us - t))) for t in target_us], dtype=np.int32)


def _estimate_velocity(
    beam_samples: np.ndarray,
    timestamps_s: np.ndarray,
    wavelength_m: float,
    gap_factor: float,
) -> np.ndarray:
    out = np.full((beam_samples.shape[0], beam_samples.shape[2]), np.nan, dtype=np.float32)
    if beam_samples.shape[1] < 2:
        return out

    dt = np.diff(timestamps_s.astype(np.float64))
    dt = dt[np.isfinite(dt) & (dt > 0.0)]
    if dt.size == 0:
        return out

    dt_ref = float(np.median(dt))
    keep = (np.diff(timestamps_s.astype(np.float64)) > 0.0) & (np.diff(timestamps_s.astype(np.float64)) <= gap_factor * dt_ref)
    if not np.any(keep):
        return out

    centered = beam_samples - np.mean(beam_samples, axis=1, keepdims=True)
    pair_prod = centered[:, 1:, :] * np.conj(centered[:, :-1, :])
    pair_prod[:, ~keep, :] = 0.0
    acc = np.sum(pair_prod, axis=1)
    dphi = np.angle(acc)
    vel = -(wavelength_m * dphi) / (4.0 * np.pi * dt_ref)

    weak = np.abs(acc) <= 1.0e-9
    vel[weak] = np.nan
    return vel.astype(np.float32)


def _valid_selected_samples(
    rec: h5py.Group,
    sample_idx: np.ndarray,
    mf_spec: MatchedFilterSpec | None,
    sample_count: int,
) -> np.ndarray:
    valid = np.ones(sample_idx.size, dtype=bool)
    if sample_idx.size == 0:
        return valid

    blanked = np.zeros(sample_count, dtype=bool)
    if "blanked_samples" in rec:
        blank_idx = rec["blanked_samples"][...].astype(np.int64)
        blank_idx = blank_idx[(blank_idx >= 0) & (blank_idx < sample_count)]
        blanked[blank_idx.astype(np.int32)] = True

    valid &= ~blanked[sample_idx]
    if mf_spec is None or mf_spec.combine_delays is None:
        return valid

    max_delay = int(np.max(mf_spec.combine_delays.astype(np.int64)))
    valid &= (sample_idx.astype(np.int64) + np.int64(max_delay)) < np.int64(sample_count)
    return valid


def _spatial_support(mask: np.ndarray, min_neighbors: int) -> np.ndarray:
    if min_neighbors <= 0:
        return mask

    support = np.zeros(mask.shape, dtype=np.int16)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            rs = slice(max(0, dr), mask.shape[0] + min(0, dr))
            cs = slice(max(0, dc), mask.shape[1] + min(0, dc))
            rd = slice(max(0, -dr), mask.shape[0] - max(0, dr))
            cd = slice(max(0, -dc), mask.shape[1] - max(0, dc))
            support[rd, cd] += mask[rs, cs]
    return mask & (support >= min_neighbors)


def _beam_edges(beam_az_deg: np.ndarray) -> np.ndarray:
    az = np.deg2rad(np.asarray(beam_az_deg, dtype=np.float32))
    if az.size == 1:
        spacing = np.deg2rad(3.24)
        return np.asarray([az[0] - 0.5 * spacing, az[0] + 0.5 * spacing], dtype=np.float32)
    mids = 0.5 * (az[1:] + az[:-1])
    left = az[0] - (mids[0] - az[0])
    right = az[-1] + (az[-1] - mids[-1])
    return np.concatenate([[left], mids, [right]]).astype(np.float32)


def _range_edges(range_km: np.ndarray) -> np.ndarray:
    if range_km.size == 1:
        step = max(1.0, float(range_km[0]) * 0.1)
        return np.asarray([max(0.0, range_km[0] - 0.5 * step), range_km[0] + 0.5 * step], dtype=np.float32)
    step = np.median(np.diff(range_km))
    return np.concatenate(
        [[max(0.0, range_km[0] - 0.5 * step)], range_km[:-1] + 0.5 * step, [range_km[-1] + 0.5 * step]]
    ).astype(np.float32)


def _range_grid_for_record(
    rec: h5py.Group,
    sample_time_us: np.ndarray,
    matched_filter_mode: str,
    range_mode: str,
) -> tuple[np.ndarray, np.ndarray]:
    first_range_km = float(rec["first_range"][()])
    first_range_rtt_us = float(rec["first_range_rtt"][()])
    gate_numbers = rec["range_gates"][...].astype(np.int32)
    range_sep_km = float(rec["range_sep"][()])

    use_samples = range_mode == "samples"
    if use_samples:
        range_km = _rtt_us_to_range_km(first_range_rtt_us + sample_time_us)
        max_range_km = first_range_km + gate_numbers.size * range_sep_km
        keep = (range_km >= first_range_km - 1.0e-3) & (range_km <= max_range_km + 1.0e-3)
        sample_idx = np.nonzero(keep)[0].astype(np.int32)
        range_km = range_km[keep]
        return sample_idx, range_km

    sample_idx = _gate_sample_indices(sample_time_us, gate_numbers, range_sep_km, first_range_rtt_us)
    range_km = (first_range_km + gate_numbers.astype(np.float32) * np.float32(range_sep_km)).astype(np.float32)
    return sample_idx, range_km


def run(args: argparse.Namespace) -> tuple[Path, Path]:
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    record_results: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    mf_modes: list[str] = []

    beam_az_by_num: dict[int, float] = {}
    range_km: np.ndarray | None = None
    main_ids: np.ndarray | None = None
    freq_khz = np.nan

    with h5py.File(input_path, "r") as src:
        all_records = sorted([k for k in src.keys() if k != "metadata"])
        use_records = _parse_records(all_records, args.record, args.records)

        for rec_name in use_records:
            rec = src[rec_name]
            if "rx_main_excitations" not in rec or "beam_azms" not in rec or "beam_nums" not in rec:
                continue

            sample_time_us = rec["sample_time"][...].astype(np.float32)
            main_data, main_weights, record_main_ids = _extract_main_array_data(rec)
            mf_spec, mf_applied_mode = _build_mf_kernel(rec, sample_time_us, args.matched_filter)
            mf_modes.append(mf_applied_mode)
            sample_idx, record_range_km = _range_grid_for_record(rec, sample_time_us, mf_applied_mode, args.range_mode)
            main_data = _apply_matched_filter(main_data, mf_spec)

            beamformed = np.einsum("ba,ast->bst", main_weights, main_data, optimize=True)
            beam_samples = np.take(beamformed, sample_idx, axis=2)

            centered = beam_samples - np.mean(beam_samples, axis=1, keepdims=True)
            power_lin = np.mean(np.abs(centered) ** 2, axis=1)
            power_db = _db(power_lin)

            freq_khz = float(rec["freq"][()])
            wavelength_m = C_MPS / (freq_khz * 1.0e3)
            timestamps_s = rec["sqn_timestamps"][...].astype(np.float64)
            vel = _estimate_velocity(beam_samples, timestamps_s, wavelength_m, args.max_gap_factor)
            valid_ranges = _valid_selected_samples(rec, sample_idx, mf_spec, main_data.shape[-1])
            power_db[:, ~valid_ranges] = np.nan
            vel[:, ~valid_ranges] = np.nan

            record_beam_nums = rec["beam_nums"][...].astype(np.int32).reshape(-1)
            record_beam_azms = rec["beam_azms"][...].astype(np.float32).reshape(-1)
            if record_beam_nums.size != power_db.shape[0] or record_beam_azms.size != power_db.shape[0]:
                raise RuntimeError(
                    f"Beam metadata mismatch in {rec_name}: "
                    f"power_beams={power_db.shape[0]} beam_nums={record_beam_nums.size} beam_azms={record_beam_azms.size}"
                )

            for beam_num, beam_az in zip(record_beam_nums.tolist(), record_beam_azms.tolist()):
                prev = beam_az_by_num.get(int(beam_num))
                if prev is None:
                    beam_az_by_num[int(beam_num)] = float(beam_az)
                elif not np.isclose(prev, float(beam_az), atol=1.0e-3):
                    raise RuntimeError(f"Inconsistent azimuth for beam {beam_num}: {prev} vs {beam_az}")

            if range_km is None:
                range_km = record_range_km.astype(np.float32, copy=True)
            elif range_km.shape != record_range_km.shape or not np.allclose(range_km, record_range_km, atol=1.0e-3):
                raise RuntimeError(f"Range grid mismatch in {rec_name}")

            if main_ids is None:
                main_ids = record_main_ids
            elif main_ids.shape != record_main_ids.shape or not np.array_equal(main_ids, record_main_ids):
                raise RuntimeError(f"Main-array antenna mismatch in {rec_name}")

            record_results.append(
                (
                    record_beam_nums,
                    record_beam_azms,
                    power_db.T.astype(np.float32),
                    vel.T.astype(np.float32),
                )
            )

    if not record_results or range_km is None or not beam_az_by_num:
        raise RuntimeError("No usable records found in antennas_iq file")

    beam_meta = sorted(beam_az_by_num.items(), key=lambda item: item[1])
    beam_nums = np.asarray([beam_num for beam_num, _ in beam_meta], dtype=np.int32)
    beam_azms = np.asarray([beam_az for _, beam_az in beam_meta], dtype=np.float32)
    beam_to_col = {int(beam_num): col for col, beam_num in enumerate(beam_nums.tolist())}

    power_records: list[np.ndarray] = []
    vel_records: list[np.ndarray] = []
    for record_beam_nums, _record_beam_azms, record_power, record_vel in record_results:
        power_aligned = np.full((range_km.size, beam_nums.size), np.nan, dtype=np.float32)
        vel_aligned = np.full((range_km.size, beam_nums.size), np.nan, dtype=np.float32)
        for src_col, beam_num in enumerate(record_beam_nums.tolist()):
            dst_col = beam_to_col.get(int(beam_num))
            if dst_col is None:
                continue
            power_aligned[:, dst_col] = record_power[:, src_col]
            vel_aligned[:, dst_col] = record_vel[:, src_col]
        power_records.append(power_aligned)
        vel_records.append(vel_aligned)

    power_stack = np.stack(power_records, axis=0)
    vel_stack = np.stack(vel_records, axis=0)

    power = np.nanmedian(power_stack, axis=0)
    vel = np.nanmedian(vel_stack, axis=0)

    noise_floor = np.full(power.shape[1], np.nan, dtype=np.float32)
    snr = np.full_like(power, np.nan, dtype=np.float32)
    for col in range(power.shape[1]):
        vals = power[:, col]
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            continue
        floor = float(np.percentile(vals, args.noise_percentile))
        noise_floor[col] = floor
        snr[:, col] = power[:, col] - floor

    mask = np.isfinite(power) & np.isfinite(vel) & np.isfinite(snr) & (snr >= args.min_snr_db)
    mask = _spatial_support(mask, args.min_neighbors)

    power_plot = np.where(mask, power, np.nan)
    vel_plot = np.where(mask, vel, np.nan)

    az_edges = _beam_edges(beam_azms)
    range_edges = _range_edges(range_km)
    th2d, r2d = np.meshgrid(az_edges, range_edges)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), subplot_kw={"projection": "polar"}, constrained_layout=True)
    for ax in axes:
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_thetamin(float(np.rad2deg(az_edges.min())))
        ax.set_thetamax(float(np.rad2deg(az_edges.max())))
        ax.set_rmax(float(range_edges[-1]))
        ax.grid(True, alpha=0.3)

    pvals = power_plot[np.isfinite(power_plot)]
    if pvals.size:
        pvmin = float(np.percentile(pvals, 5))
        pvmax = float(np.percentile(pvals, 98))
        if pvmax <= pvmin:
            pvmin = float(np.min(pvals))
            pvmax = float(np.max(pvals))
    else:
        pvmin, pvmax = 0.0, 20.0

    im0 = axes[0].pcolormesh(th2d, r2d, power_plot, cmap="turbo", vmin=pvmin, vmax=pvmax, shading="auto")
    axes[0].set_title("Power")
    cb0 = fig.colorbar(im0, ax=axes[0], pad=0.08)
    cb0.set_label("Power (dB)")

    vvals = vel_plot[np.isfinite(vel_plot)]
    if vvals.size:
        vlim = float(np.percentile(np.abs(vvals), 98))
        vlim = max(args.min_velocity_limit, min(vlim, args.max_velocity_limit))
    else:
        vlim = args.default_velocity_limit

    im1 = axes[1].pcolormesh(th2d, r2d, vel_plot, cmap="RdBu_r", vmin=-vlim, vmax=vlim, shading="auto")
    axes[1].set_title("Doppler")
    cb1 = fig.colorbar(im1, ax=axes[1], pad=0.08)
    cb1.set_label("Doppler (m/s)")

    kept = int(np.count_nonzero(np.isfinite(power_plot)))
    total = int(power_plot.size)
    kept_pct = 100.0 * kept / max(total, 1)
    title_mode = args.title_prefix or input_path.stem
    fig.suptitle(
        f"{title_mode} scheduled BF + MF={mf_modes[-1]} ({kept_pct:.2f}% bins kept)\n"
        f"{input_path.name} records={power_stack.shape[0]} freq={int(round(freq_khz))} kHz"
    )

    if args.output:
        output_png = Path(args.output).expanduser().resolve()
    else:
        output_png = input_path.with_suffix("").with_suffix("")
        output_png = output_png.with_name(output_png.name + f".sched_bf_{mf_modes[-1]}_polar.png")
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=args.dpi)
    plt.close(fig)

    meta = {
        "input": str(input_path),
        "records_used": int(power_stack.shape[0]),
        "beam_nums": beam_nums.astype(int).tolist(),
        "beam_az_deg": beam_azms.astype(float).tolist(),
        "range_km_min": float(range_km[0]),
        "range_km_max": float(range_km[-1]),
        "num_ranges": int(range_km.size),
        "freq_khz": float(freq_khz),
        "matched_filter_mode": mf_modes[-1],
        "range_mode": args.range_mode,
        "min_snr_db": float(args.min_snr_db),
        "noise_percentile": float(args.noise_percentile),
        "min_neighbors": int(args.min_neighbors),
        "max_gap_factor": float(args.max_gap_factor),
        "kept_bins": kept,
        "total_bins": total,
        "kept_pct": kept_pct,
        "main_antennas": [] if main_ids is None else main_ids.astype(int).tolist(),
        "output_png": str(output_png),
    }
    output_json = output_png.with_suffix(".json")
    output_json.write_text(json.dumps(meta, indent=2))
    return output_png, output_json


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="Path to Borealis antennas_iq HDF5 file")
    p.add_argument("--output", help="Output PNG path")
    p.add_argument("--record", help="Specific record group to plot")
    p.add_argument("--records", type=int, default=0, help="Latest N records to use; 0 means all records")
    p.add_argument("--matched-filter", choices=["off", "auto", "rect", "barker13"], default="auto")
    p.add_argument("--range-mode", choices=["auto", "gates", "samples"], default="auto")
    p.add_argument("--min-snr-db", type=float, default=6.0, help="Minimum per-beam SNR above noise floor")
    p.add_argument("--noise-percentile", type=float, default=25.0, help="Percentile used to estimate noise floor per beam")
    p.add_argument("--min-neighbors", type=int, default=1, help="Minimum neighboring bins required to keep a cell")
    p.add_argument("--max-gap-factor", type=float, default=1.5, help="Keep slow-time pairs up to this multiple of the median pair spacing")
    p.add_argument("--default-velocity-limit", type=float, default=400.0, help="Fallback Doppler color limit in m/s")
    p.add_argument("--min-velocity-limit", type=float, default=100.0, help="Minimum Doppler color limit in m/s")
    p.add_argument("--max-velocity-limit", type=float, default=1500.0, help="Maximum Doppler color limit in m/s")
    p.add_argument("--title-prefix", default="", help="Optional figure title prefix")
    p.add_argument("--dpi", type=int, default=160)
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    out_png, out_json = run(args)
    print(str(out_png))
    print(str(out_json))


if __name__ == "__main__":
    main()
