#!/usr/bin/env python3

import argparse
import datetime as dt
import glob
import os
import re
import statistics
import subprocess
import sys
import tempfile

TIME_RE = re.compile(r"(\d{8})-(\d{4})")


def parse_timestamp(path):
    matches = TIME_RE.findall(path)
    if not matches:
        return None
    date_str, hm_str = matches[-1]
    try:
        return dt.datetime.strptime(date_str + hm_str, "%Y%m%d%H%M")
    except ValueError:
        return None


def parse_user_datetime(value, is_end=False):
    if value is None:
        return None
    value = value.strip()
    for fmt in ("%Y%m%d-%H%M", "%Y%m%d"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            if fmt == "%Y%m%d" and is_end:
                return parsed + dt.timedelta(days=1) - dt.timedelta(seconds=1)
            return parsed
        except ValueError:
            continue
    raise ValueError(
        "Invalid datetime format. Use YYYYMMDD or YYYYMMDD-HHMM."
    )


def collect_images(input_path, recursive=True, ext=".png"):
    if any(ch in input_path for ch in "*?[]"):
        paths = glob.glob(input_path, recursive=True)
    elif os.path.isdir(input_path):
        paths = []
        if recursive:
            for root, _, files in os.walk(input_path):
                for name in files:
                    if name.lower().endswith(ext):
                        paths.append(os.path.join(root, name))
        else:
            for name in os.listdir(input_path):
                if name.lower().endswith(ext):
                    paths.append(os.path.join(input_path, name))
    else:
        paths = [input_path]

    paths = [p for p in paths if os.path.isfile(p)]
    return paths


def sorted_with_timestamps(paths):
    stamped = []
    unstamped = []
    for path in paths:
        ts = parse_timestamp(path)
        if ts is None:
            unstamped.append(path)
        else:
            stamped.append((ts, path))

    stamped.sort(key=lambda x: x[0])
    ordered = [p for _, p in stamped] + sorted(unstamped)
    times = [t for t, _ in stamped]
    return ordered, times


def infer_minutes_per_frame(times):
    if len(times) < 2:
        return None
    deltas = []
    for a, b in zip(times, times[1:]):
        delta = (b - a).total_seconds() / 60.0
        if delta > 0:
            deltas.append(delta)
    if not deltas:
        return None
    return statistics.median(deltas)


def compute_fps(minutes_per_frame, seconds_per_hour):
    if minutes_per_frame <= 0:
        raise ValueError("Minutes per frame must be positive.")
    frames_per_hour = 60.0 / minutes_per_frame
    return frames_per_hour / seconds_per_hour


def guess_output_path(input_path, ordered_paths, times):
    if os.path.isdir(input_path):
        base_dir = input_path
    else:
        base_dir = os.path.commonpath(ordered_paths) if ordered_paths else os.getcwd()
        if os.path.isfile(base_dir):
            base_dir = os.path.dirname(base_dir)

    date_str = times[0].strftime("%Y%m%d") if times else None
    if date_str:
        return os.path.join(base_dir, f"maps_{date_str}.mp4")
    return os.path.join(base_dir, "maps_movie.mp4")


def guess_output_path_range(input_path, ordered_paths, start_time, end_time):
    if os.path.isdir(input_path):
        base_dir = input_path
    else:
        base_dir = os.path.commonpath(ordered_paths) if ordered_paths else os.getcwd()
        if os.path.isfile(base_dir):
            base_dir = os.path.dirname(base_dir)

    if start_time and end_time:
        tag = f"{start_time:%Y%m%d}_{end_time:%Y%m%d}"
    elif start_time:
        tag = f"{start_time:%Y%m%d}"
    elif end_time:
        tag = f"{end_time:%Y%m%d}"
    else:
        tag = "movie"
    return os.path.join(base_dir, f"maps_{tag}.mp4")


def write_concat_file(paths, duration_sec=None):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    for path in paths:
        abs_path = os.path.abspath(path)
        escaped = abs_path.replace("'", "'\\''")
        tmp.write(f"file '{escaped}'\n")
        if duration_sec is not None:
            tmp.write(f"duration {duration_sec:.6f}\n")
    if paths:
        abs_path = os.path.abspath(paths[-1])
        escaped = abs_path.replace("'", "'\\''")
        tmp.write(f"file '{escaped}'\n")
    tmp.flush()
    tmp.close()
    return tmp.name


def run_ffmpeg(list_path, output_path, fps):
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        list_path,
        "-vf",
        f"fps={fps:.3f},scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-fps_mode",
        "cfr",
        "-pix_fmt",
        "yuv420p",
        output_path,
    ]
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create a movie from map images produced by plot_fitacf_nc.py. "
            "Default speed is 0.5 seconds per hour of data."
        )
    )
    parser.add_argument(
        "input",
        help=(
            "Input directory or glob for map images (e.g. plots/maps/20230728 or "
            "plots/maps/20230728/**/*.png)."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output mp4 path. Defaults to maps_YYYYMMDD.mp4 in the input directory.",
    )
    parser.add_argument(
        "--seconds-per-hour",
        type=float,
        default=0.5,
        help="Video seconds per hour of data (default: 0.5).",
    )
    parser.add_argument(
        "--minutes-per-frame",
        type=float,
        default=None,
        help="Override the time step in minutes if timestamps are missing.",
    )
    parser.add_argument(
        "--start",
        help="Start datetime (YYYYMMDD or YYYYMMDD-HHMM).",
    )
    parser.add_argument(
        "--end",
        help="End datetime (YYYYMMDD or YYYYMMDD-HHMM).",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Explicit frames-per-second override.",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Disable recursive search when input is a directory.",
    )

    args = parser.parse_args()

    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ffmpeg is required but was not found in PATH.", file=sys.stderr)
        return 2

    paths = collect_images(args.input, recursive=not args.no_recursive)
    if not paths:
        print("No image files found.", file=sys.stderr)
        return 2

    ordered_paths, times = sorted_with_timestamps(paths)
    start_time = None
    end_time = None
    if args.start or args.end:
        try:
            start_time = parse_user_datetime(args.start, is_end=False)
            end_time = parse_user_datetime(args.end, is_end=True)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        filtered = []
        filtered_times = []
        for path in ordered_paths:
            ts = parse_timestamp(path)
            if ts is None:
                continue
            if start_time and ts < start_time:
                continue
            if end_time and ts > end_time:
                continue
            filtered.append(path)
            filtered_times.append(ts)
        if not filtered:
            print("No images found in the requested time range.", file=sys.stderr)
            return 2
        ordered_paths = filtered
        times = filtered_times

    if args.fps is not None:
        fps = args.fps
    else:
        minutes_per_frame = args.minutes_per_frame
        if minutes_per_frame is None:
            minutes_per_frame = infer_minutes_per_frame(times)
        if minutes_per_frame is None:
            print("Unable to infer frame interval; provide --minutes-per-frame or --fps.", file=sys.stderr)
            return 2
        fps = compute_fps(minutes_per_frame, args.seconds_per_hour)

    if args.output:
        output_path = args.output
    elif start_time or end_time:
        output_path = guess_output_path_range(args.input, ordered_paths, start_time, end_time)
    else:
        output_path = guess_output_path(args.input, ordered_paths, times)
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    duration_sec = 1.0 / fps
    list_path = write_concat_file(ordered_paths, duration_sec=duration_sec)
    try:
        run_ffmpeg(list_path, output_path, fps)
    finally:
        os.unlink(list_path)

    print(f"Saved movie to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
