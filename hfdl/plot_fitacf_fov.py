#!/usr/bin/env python3

"""Plot Borealis fitacf power and Doppler on a polar FOV grid."""

from __future__ import annotations

import argparse
import bz2
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors
from matplotlib.cm import ScalarMappable
import numpy as np
import pydarnio

try:
    from backscatter import fitacf as backscatter_fitacf
except ImportError:  # pragma: no cover - optional for rawacf replay
    backscatter_fitacf = None

try:
    import zmq
except ImportError:  # pragma: no cover - only exercised for live capture
    zmq = None


DEFAULT_SOCKET = "tcp://192.168.112.127:9696"
DEFAULT_WAL_BEAM_AZ_DEG = [
    -37.26,
    -34.02,
    -30.78,
    -27.54,
    -24.30,
    -21.06,
    -17.82,
    -14.58,
    -11.34,
    -8.10,
    -4.86,
    -1.62,
    1.62,
    4.86,
    8.10,
    11.34,
    14.58,
    17.82,
    21.06,
    24.30,
    27.54,
    30.78,
    34.02,
    37.26,
]


def _parse_int_list(spec: str | None) -> list[int] | None:
    if spec is None:
        return None
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out


def _parse_float_list(spec: str | None) -> list[float] | None:
    if spec is None:
        return None
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    return out


def _record_time_utc(rec: dict) -> datetime:
    return datetime(
        int(rec["time.yr"]),
        int(rec["time.mo"]),
        int(rec["time.dy"]),
        int(rec["time.hr"]),
        int(rec["time.mt"]),
        int(rec["time.sc"]),
        int(rec["time.us"]),
        tzinfo=timezone.utc,
    )


def _load_fitacf_records(path: Path) -> tuple[list[dict], int]:
    if path.suffix == ".bz2":
        payload = bz2.decompress(path.read_bytes())
        return pydarnio.read_fitacf(payload, mode="strict"), 0
    return pydarnio.read_fitacf(str(path), mode="strict"), 0


def _load_rawacf_records(path: Path) -> tuple[list[dict], int]:
    if path.suffix == ".bz2":
        payload = bz2.decompress(path.read_bytes())
        return pydarnio.read_rawacf(payload, mode="strict"), 0
    return pydarnio.read_rawacf(str(path), mode="strict"), 0


def _capture_fitacf_records(
    socket_addr: str,
    duration_s: float,
    max_messages: int | None,
    decompress_bz2: bool,
) -> tuple[list[dict], int]:
    if zmq is None:
        raise RuntimeError("pyzmq is required for --socket capture mode")

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.LINGER, 0)
    sub.connect(socket_addr)

    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    records: list[dict] = []
    messages_received = 0
    deadline = time.monotonic() + duration_s
    try:
        while time.monotonic() < deadline:
            remaining_ms = max(1, int(1000 * (deadline - time.monotonic())))
            events = dict(poller.poll(remaining_ms))
            if sub not in events:
                continue
            payload = sub.recv()
            if decompress_bz2:
                payload = bz2.decompress(payload)
            records.extend(pydarnio.read_fitacf(payload, mode="strict"))
            messages_received += 1
            if max_messages is not None and messages_received >= max_messages:
                break
    finally:
        sub.close()

    return records, messages_received


def _most_common_value(records: list[dict], key: str, cast=int) -> int | None:
    vals = [cast(rec[key]) for rec in records if key in rec]
    if not vals:
        return None
    return Counter(vals).most_common(1)[0][0]


def _detect_input_format(path: Path, input_format: str) -> str:
    if input_format != "auto":
        return input_format

    lower_name = path.name.lower()
    if ".fitacf" in lower_name:
        return "fitacf"
    if ".rawacf" in lower_name:
        return "rawacf"
    raise ValueError("Could not infer input format from path; use --input-format fitacf|rawacf")


def _select_last_scans(records: list[dict], scans: int | None, beams_per_scan: int) -> list[dict]:
    if scans is None:
        return records
    keep = max(int(scans), 1) * max(int(beams_per_scan), 1)
    if len(records) <= keep:
        return records
    return records[-keep:]


def _fit_rawacf_records(records: list[dict]) -> list[dict]:
    if backscatter_fitacf is None:
        raise RuntimeError("rawacf replay requires the backscatter package")

    fitted: list[dict] = []
    for rec in records:
        try:
            fit = backscatter_fitacf._fit(rec)
        except Exception:
            continue
        if not fit:
            continue
        if "pwr0" in fit:
            fit["pwr0"] = np.asarray(fit["pwr0"], dtype=np.float32)
        fitted.append(fit)
    return fitted


def _beam_azimuth_map(
    records: list[dict],
    beam_ids: list[int],
    beam_az_override: list[float] | None,
) -> dict[int, float]:
    if beam_az_override is not None:
        if len(beam_az_override) != len(beam_ids):
            raise ValueError("--beam-az-deg length must match --beam-ids length")
        return {beam: az for beam, az in zip(beam_ids, beam_az_override)}

    out: dict[int, float] = {}
    for rec in records:
        if "bmnum" in rec and "bmazm" in rec:
            out[int(rec["bmnum"])] = float(rec["bmazm"])

    if beam_ids == list(range(len(DEFAULT_WAL_BEAM_AZ_DEG))):
        for beam, az in zip(beam_ids, DEFAULT_WAL_BEAM_AZ_DEG):
            out.setdefault(beam, az)

    missing = [beam for beam in beam_ids if beam not in out]
    if missing:
        raise ValueError(f"Missing azimuths for beams: {missing}")
    return out


def _beam_edges_deg(beam_az_deg: dict[int, float]) -> dict[int, tuple[float, float]]:
    ordered = sorted(beam_az_deg.items(), key=lambda item: item[1])
    centers = np.array([az for _, az in ordered], dtype=float)
    beams = [beam for beam, _ in ordered]
    if centers.size < 2:
        width = 3.24
        return {beams[0]: (centers[0] - 0.5 * width, centers[0] + 0.5 * width)}

    edges = np.empty(centers.size + 1, dtype=float)
    edges[1:-1] = 0.5 * (centers[:-1] + centers[1:])
    edges[0] = centers[0] - 0.5 * (centers[1] - centers[0])
    edges[-1] = centers[-1] + 0.5 * (centers[-1] - centers[-2])
    return {beam: (float(edges[i]), float(edges[i + 1])) for i, beam in enumerate(beams)}


def _aggregate_cells(
    records: list[dict],
    plot_beams: list[int],
    nrang: int,
) -> tuple[np.ndarray, np.ndarray]:
    power = np.full((len(plot_beams), nrang), np.nan, dtype=np.float32)
    doppler = np.full((len(plot_beams), nrang), np.nan, dtype=np.float32)
    beam_to_index = {beam: i for i, beam in enumerate(plot_beams)}

    for rec in records:
        beam = int(rec.get("bmnum", -1))
        if beam not in beam_to_index:
            continue

        slist = np.asarray(rec.get("slist", []), dtype=np.int32).ravel()
        p_l = np.asarray(rec.get("p_l", []), dtype=np.float32).ravel()
        v = np.asarray(rec.get("v", []), dtype=np.float32).ravel()
        qflg = np.asarray(rec.get("qflg", np.ones_like(slist)), dtype=np.int8).ravel()
        n = min(slist.size, p_l.size, v.size)
        if n == 0:
            continue

        bi = beam_to_index[beam]
        for i in range(n):
            if i < qflg.size and int(qflg[i]) == 0:
                continue
            gate = int(slist[i])
            if gate < 0 or gate >= nrang:
                continue
            pwr = float(p_l[i])
            vel = float(v[i])
            if not np.isfinite(pwr) or not np.isfinite(vel):
                continue
            current = power[bi, gate]
            if not np.isfinite(current) or pwr > current:
                power[bi, gate] = pwr
                doppler[bi, gate] = vel

    return power, doppler


def _auto_power_limits(power: np.ndarray, user_min: float | None, user_max: float | None) -> tuple[float, float]:
    valid = power[np.isfinite(power)]
    if valid.size == 0:
        return 0.0, 1.0
    pmin = float(np.nanmin(valid) if user_min is None else user_min)
    pmax = float(np.nanpercentile(valid, 99.0) if user_max is None else user_max)
    if pmax <= pmin:
        pmax = pmin + 1.0
    return pmin, pmax


def _auto_doppler_limit(doppler: np.ndarray, user_limit: float | None) -> float:
    if user_limit is not None:
        return max(float(user_limit), 1.0)
    valid = np.abs(doppler[np.isfinite(doppler)])
    if valid.size == 0:
        return 1.0
    return max(float(np.nanpercentile(valid, 99.0)), 1.0)


def _draw_panel(
    ax: plt.Axes,
    values: np.ndarray,
    plot_beams: list[int],
    beam_edges_deg: dict[int, tuple[float, float]],
    range_edges_km: np.ndarray,
    cmap: str,
    norm: colors.Normalize,
    title: str,
) -> ScalarMappable:
    for row, beam in enumerate(plot_beams):
        left_deg, right_deg = beam_edges_deg[beam]
        theta = np.column_stack(
            [
                np.full(range_edges_km.size, np.deg2rad(left_deg), dtype=float),
                np.full(range_edges_km.size, np.deg2rad(right_deg), dtype=float),
            ]
        )
        radius = np.column_stack([range_edges_km, range_edges_km])
        cell_values = np.ma.masked_invalid(values[row, :, None])
        ax.pcolormesh(theta, radius, cell_values, cmap=cmap, norm=norm, shading="flat")

    theta_min = min(beam_edges_deg[beam][0] for beam in plot_beams)
    theta_max = max(beam_edges_deg[beam][1] for beam in plot_beams)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetamin(theta_min)
    ax.set_thetamax(theta_max)
    ax.set_title(title, pad=20)
    ax.set_ylim(max(0.0, float(range_edges_km[0])), float(range_edges_km[-1]))
    ax.grid(True, alpha=0.35)

    theta_ticks = np.arange(np.ceil(theta_min / 9.0) * 9.0, theta_max + 0.1, 9.0)
    ax.set_thetagrids(theta_ticks, labels=[f"{int(round(x))}\N{DEGREE SIGN}" for x in theta_ticks])
    max_range = float(range_edges_km[-1])
    range_ticks = np.arange(500.0, max_range + 1.0, 500.0)
    ax.set_rticks(range_ticks)
    ax.set_rlabel_position(float(theta_min) - 6.0)

    return ScalarMappable(norm=norm, cmap=cmap)


def _write_sidecar(
    json_path: Path,
    start_utc: datetime,
    stop_utc: datetime,
    duration_s: float,
    args: argparse.Namespace,
    input_format: str,
    messages_received: int,
    cp_records: list[dict],
    all_beams_seen: list[int],
    plot_beams: list[int],
    beam_az_deg: dict[int, float],
    frang: int,
    rsep: int,
    nrang: int,
    tfreq: int | None,
    output_png: Path,
) -> None:
    payload = {
        "start_utc": start_utc.isoformat().replace("+00:00", "Z"),
        "stop_utc": stop_utc.isoformat().replace("+00:00", "Z"),
        "duration_s": duration_s,
        "cp": int(args.cp) if args.cp is not None else None,
        "messages_received": int(messages_received),
        "cp_records": int(len(cp_records)),
        "all_beams_seen": all_beams_seen,
        "plot_beams": plot_beams,
        "beam_az_deg": {str(beam): float(beam_az_deg[beam]) for beam in plot_beams},
        "frang_km": float(frang),
        "rsep_km": float(rsep),
        "nrang": int(nrang),
        "output_png": str(output_png),
    }
    if tfreq is not None:
        payload["tfreq_khz"] = int(tfreq)
    if args.socket:
        payload["socket"] = args.socket
    if args.input:
        payload[f"input_{input_format}"] = str(Path(args.input).expanduser().resolve())
    if args.accumulate_scans is not None:
        payload["accumulate_scans"] = int(args.accumulate_scans)
    json_path.write_text(json.dumps(payload, indent=2) + "\n")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--socket", default=None, help="Realtime fitacf PUB socket, e.g. tcp://192.168.112.127:9696")
    src.add_argument("--input", help="Offline .fitacf[.bz2] or .rawacf[.bz2] file")
    p.add_argument("--input-format", choices=["auto", "fitacf", "rawacf"], default="auto", help="Offline input format")
    p.add_argument("--duration-s", type=float, default=60.0, help="Live capture duration in seconds")
    p.add_argument("--max-messages", type=int, help="Optional live capture cap")
    p.add_argument("--socket-bz2", action="store_true", default=True, help="Live socket payloads are bzip2 compressed")
    p.add_argument("--no-socket-bz2", action="store_false", dest="socket_bz2", help="Treat live socket payloads as raw fitacf bytes")
    p.add_argument("--cp", type=int, required=True, help="Control program ID to keep")
    p.add_argument("--radar", default="wal", help="Radar code for title/output naming")
    p.add_argument("--mode-label", default="fov", help="Mode label for the plot title")
    p.add_argument("--beam-ids", default="0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23")
    p.add_argument("--plot-beams", help="Subset of beam IDs to render")
    p.add_argument("--beam-az-deg", help="Comma-separated beam azimuth centers in degrees")
    p.add_argument("--output", help="Output PNG path")
    p.add_argument("--json-output", help="Optional JSON sidecar path")
    p.add_argument("--accumulate-scans", type=int, help="Keep only the last N scans, where one scan is len(--beam-ids) records")
    p.add_argument("--power-min", type=float, help="Power color scale minimum (dB)")
    p.add_argument("--power-max", type=float, help="Power color scale maximum (dB)")
    p.add_argument("--doppler-max-abs", type=float, help="Symmetric Doppler color scale half-width (m/s)")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    beam_ids = _parse_int_list(args.beam_ids)
    if beam_ids is None or not beam_ids:
        raise ValueError("--beam-ids must not be empty")
    plot_beams = _parse_int_list(args.plot_beams) or beam_ids
    beam_az_override = _parse_float_list(args.beam_az_deg)

    if args.socket:
        socket_addr = args.socket or DEFAULT_SOCKET
        records, messages_received = _capture_fitacf_records(
            socket_addr=socket_addr,
            duration_s=args.duration_s,
            max_messages=args.max_messages,
            decompress_bz2=args.socket_bz2,
        )
        input_format = "fitacf"
        cp_records = [rec for rec in records if int(rec.get("cp", -1)) == int(args.cp)]
    else:
        input_path = Path(args.input).expanduser().resolve()
        input_format = _detect_input_format(input_path, args.input_format)
        if input_format == "fitacf":
            records, messages_received = _load_fitacf_records(input_path)
            cp_records = [rec for rec in records if int(rec.get("cp", -1)) == int(args.cp)]
        else:
            raw_records, messages_received = _load_rawacf_records(input_path)
            cp_raw_records = [rec for rec in raw_records if int(rec.get("cp", -1)) == int(args.cp)]
            cp_raw_records.sort(key=_record_time_utc)
            cp_raw_records = _select_last_scans(cp_raw_records, args.accumulate_scans, len(beam_ids))
            cp_records = _fit_rawacf_records(cp_raw_records)

    if not cp_records:
        raise RuntimeError(f"No {input_format} records found for cp={args.cp}")

    cp_records.sort(key=_record_time_utc)
    cp_records = _select_last_scans(cp_records, args.accumulate_scans, len(beam_ids))
    start_utc = _record_time_utc(cp_records[0])
    stop_utc = _record_time_utc(cp_records[-1])
    duration_s = max((stop_utc - start_utc).total_seconds(), 0.0)

    frang = _most_common_value(cp_records, "frang")
    rsep = _most_common_value(cp_records, "rsep")
    nrang = _most_common_value(cp_records, "nrang")
    tfreq = _most_common_value(cp_records, "tfreq")
    if frang is None or rsep is None or nrang is None:
        raise RuntimeError("Could not infer frang/rsep/nrang from fitacf records")

    beam_az_deg = _beam_azimuth_map(cp_records, beam_ids, beam_az_override)
    all_beams_seen = sorted({int(rec["bmnum"]) for rec in cp_records if "bmnum" in rec})
    beam_edges_deg = _beam_edges_deg(beam_az_deg)
    range_edges_km = (float(frang) - 0.5 * float(rsep)) + np.arange(nrang + 1, dtype=float) * float(rsep)

    power, doppler = _aggregate_cells(cp_records, plot_beams, nrang)
    if not np.isfinite(power).any():
        raise RuntimeError("No valid fitted cells found after filtering")

    power_min, power_max = _auto_power_limits(power, args.power_min, args.power_max)
    doppler_limit = _auto_doppler_limit(doppler, args.doppler_max_abs)

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(14, 6),
        subplot_kw={"projection": "polar"},
        constrained_layout=True,
    )

    power_norm = colors.Normalize(vmin=power_min, vmax=power_max)
    doppler_norm = colors.TwoSlopeNorm(vmin=-doppler_limit, vcenter=0.0, vmax=doppler_limit)

    sm_power = _draw_panel(
        axes[0],
        values=power,
        plot_beams=plot_beams,
        beam_edges_deg=beam_edges_deg,
        range_edges_km=range_edges_km,
        cmap="turbo",
        norm=power_norm,
        title="Power",
    )
    sm_doppler = _draw_panel(
        axes[1],
        values=doppler,
        plot_beams=plot_beams,
        beam_edges_deg=beam_edges_deg,
        range_edges_km=range_edges_km,
        cmap="RdBu_r",
        norm=doppler_norm,
        title="Doppler",
    )

    cbar_power = fig.colorbar(sm_power, ax=axes[0], pad=0.08)
    cbar_power.set_label("Power (dB)")
    cbar_doppler = fig.colorbar(sm_doppler, ax=axes[1], pad=0.08)
    cbar_doppler.set_label("Doppler (m/s)")

    radar = args.radar.upper()
    tfreq_text = f", tfreq={tfreq} kHz" if tfreq is not None else ""
    fig.suptitle(
        f"{radar} {args.mode_label} polar FOV (cp={args.cp}{tfreq_text})\n"
        f"{start_utc.strftime('%Y-%m-%d %H:%M:%S.%f')} to "
        f"{stop_utc.strftime('%Y-%m-%d %H:%M:%S.%f')} UTC"
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.output:
        output_png = Path(args.output).expanduser().resolve()
    elif args.input:
        base = Path(args.input).expanduser().resolve().name
        if base.endswith(".bz2"):
            base = Path(base[:-4]).stem
        else:
            base = Path(base).stem
        output_png = Path.cwd() / f"{base}.{args.mode_label}.polar_power_doppler.png"
    else:
        output_png = Path.cwd() / f"{args.radar}_{args.mode_label}_polar_power_doppler_{stamp}.png"
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=150)
    plt.close(fig)

    json_output = Path(args.json_output).expanduser().resolve() if args.json_output else output_png.with_suffix(".json")
    json_output.parent.mkdir(parents=True, exist_ok=True)
    _write_sidecar(
        json_path=json_output,
        start_utc=start_utc,
        stop_utc=stop_utc,
        duration_s=duration_s,
        args=args,
        input_format=input_format,
        messages_received=messages_received,
        cp_records=cp_records,
        all_beams_seen=all_beams_seen,
        plot_beams=plot_beams,
        beam_az_deg=beam_az_deg,
        frang=frang,
        rsep=rsep,
        nrang=nrang,
        tfreq=tfreq,
        output_png=output_png,
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "input_format": input_format,
                "records": len(cp_records),
                "messages_received": messages_received,
                "output_png": str(output_png),
                "output_json": str(json_output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
