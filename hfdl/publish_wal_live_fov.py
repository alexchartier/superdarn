#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys


REMOTE_HOST = "wal"
REMOTE_PYTHON = "~/borealis/borealis_env3.11/bin/python3.11"
REMOTE_RENDERER = "/home/radar/local_scripts/wal_live_fov/render_latest_wal_live_fov.py"
REMOTE_OUTPUT_DIR = "/home/radar/tmp/wal_live_fov"
LOCAL_WEB_DIR = Path("/project/superdarn/www/htdocs/wal-live-fov")
ARCHIVE_DIR = LOCAL_WEB_DIR / "archive"
ARCHIVE_MANIFEST = LOCAL_WEB_DIR / "wal_live_fov_archive.json"
LOCK_PATH = Path("/project/superdarn/www/cron/logs/publish_wal_live_fov.lock")
ARCHIVE_WINDOW = timedelta(hours=24)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def copy_remote_file(remote_path: str, local_path: Path) -> None:
    tmp_path = local_path.with_suffix(local_path.suffix + ".tmp")
    run(["scp", f"{REMOTE_HOST}:{remote_path}", str(tmp_path)])
    tmp_path.replace(local_path)


def parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def archive_current_status() -> None:
    status_path = LOCAL_WEB_DIR / "wal_live_fov_status.json"
    if not status_path.exists():
        return

    status = json.loads(status_path.read_text())
    generated_at = parse_utc(status["generated_at_utc"])
    cutoff = generated_at - ARCHIVE_WINDOW
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    if ARCHIVE_MANIFEST.exists():
        manifest = json.loads(ARCHIVE_MANIFEST.read_text())
    else:
        manifest = {"window_hours": 24, "entries": []}

    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    entry = {
        "generated_at_utc": status["generated_at_utc"],
        "experiment_name": status.get("experiment_name"),
        "scheduling_mode": status.get("scheduling_mode"),
        "channels": [],
        "errors": status.get("errors", []),
    }

    referenced_files: set[str] = set()
    retained_entries: list[dict] = []

    for existing in manifest.get("entries", []):
        try:
            existing_time = parse_utc(existing["generated_at_utc"])
        except Exception:
            continue
        if existing_time < cutoff:
            continue
        if existing["generated_at_utc"] == status["generated_at_utc"]:
            continue
        retained_entries.append(existing)
        for channel in existing.get("channels", []):
            for key in ("output_png", "output_json"):
                rel = channel.get(key)
                if rel:
                    referenced_files.add(Path(rel).name)

    for channel in status.get("channels", []):
        src_png = LOCAL_WEB_DIR / channel["output_png"]
        src_json = LOCAL_WEB_DIR / channel["output_json"]
        archive_png = ARCHIVE_DIR / f"{stamp}_wal_live_fov_{channel['channel']}.png"
        archive_json = ARCHIVE_DIR / f"{stamp}_wal_live_fov_{channel['channel']}.json"
        shutil.copy2(src_png, archive_png)
        shutil.copy2(src_json, archive_json)
        referenced_files.add(archive_png.name)
        referenced_files.add(archive_json.name)
        channel_entry = dict(channel)
        channel_entry["output_png"] = f"archive/{archive_png.name}"
        channel_entry["output_json"] = f"archive/{archive_json.name}"
        entry["channels"].append(channel_entry)

    retained_entries.append(entry)
    retained_entries.sort(key=lambda item: item["generated_at_utc"])
    manifest = {
        "updated_at_utc": status["generated_at_utc"],
        "window_hours": 24,
        "entries": retained_entries,
    }
    ARCHIVE_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    for path in ARCHIVE_DIR.iterdir():
        if path.is_file() and path.name not in referenced_files:
            path.unlink()


def main() -> int:
    LOCAL_WEB_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    with LOCK_PATH.open("w") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("publish_wal_live_fov: another run is active", file=sys.stderr)
            return 0

        run(
            [
                "ssh",
                REMOTE_HOST,
                REMOTE_PYTHON,
                REMOTE_RENDERER,
                "--plot-script",
                f"{Path(REMOTE_RENDERER).parent}/plot_fitacf_fov.py",
                "--output-dir",
                REMOTE_OUTPUT_DIR,
            ]
        )

        for name in [
            "wal_live_fov_a.png",
            "wal_live_fov_a.json",
            "wal_live_fov_b.png",
            "wal_live_fov_b.json",
            "wal_live_fov_status.json",
        ]:
            copy_remote_file(f"{REMOTE_OUTPUT_DIR}/{name}", LOCAL_WEB_DIR / name)

        archive_current_status()

        source_page = Path("/project/superdarn/software/wal_live_fov/index.html")
        target_page = LOCAL_WEB_DIR / "index.html"
        shutil.copy2(source_page, target_page)
        print(f"Published Wallops live FOV page to {target_page}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
