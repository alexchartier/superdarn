#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import requests
from urllib3.exceptions import InsecureRequestWarning


LOGIN_URL = "https://jawara.nipr.ac.jp/login"
LOGIN_ACTION_URL = (
    "https://jawara.nipr.ac.jp/_server"
    "?id=src_lib_common_lib_actions_ts--login_action"
    "&name=%2Fhome%2Fjawara%2Fsrc%2Flib%2Fcommon_lib_actions.ts%3Ftsr-directive-use-server%3D"
)
USER_URL = "https://jawara.nipr.ac.jp/user"
MONTH_URL = "https://jawara.nipr.ac.jp/download/{year}/{month}/"

TARGET_LABELS = {
    "temperature": "Temperature",
    "geopotential_height": "Geopotential height",
}


def log(msg: str) -> None:
    print(msg, flush=True)


def parse_date(text: str) -> tuple[int, int, int]:
    year_s, month_s, day_s = text.split("-", 2)
    year = int(year_s)
    month = int(month_s)
    day = int(day_s)
    if month < 1 or month > 12:
        raise argparse.ArgumentTypeError(f"Invalid month in {text!r}")
    if day < 1 or day > 31:
        raise argparse.ArgumentTypeError(f"Invalid day in {text!r}")
    return year, month, day


def login(session: requests.Session, user: str, password: str) -> None:
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    session.get(LOGIN_URL, timeout=60)
    resp = session.post(
        LOGIN_ACTION_URL,
        data={"userid": user, "password": password},
        headers={"Referer": LOGIN_URL},
        allow_redirects=True,
        timeout=60,
    )
    resp.raise_for_status()

    user_page = session.get(USER_URL, timeout=60)
    user_page.raise_for_status()
    if "approved" not in user_page.text.lower():
        raise RuntimeError("JAWARA login did not reach an approved user session.")


def fetch_month_links(session: requests.Session, year: int, month: int) -> dict[str, str]:
    resp = session.get(MONTH_URL.format(year=year, month=month), timeout=60)
    resp.raise_for_status()
    html = resp.text

    links: dict[str, str] = {}
    for key, label in TARGET_LABELS.items():
        pattern = re.compile(rf'>{re.escape(label)}</td>.*?href="(?P<href>/api/jawara/[^"]+)"', re.S)
        match = pattern.search(html)
        if match is None:
            raise RuntimeError(f"Unable to find JAWARA link for {label!r} in {year}-{month:02d}")
        links[key] = match.group("href")

    return links


def download_file(session: requests.Session, url: str, out_path: Path, *, overwrite: bool = False) -> None:
    if out_path.exists() and not overwrite:
        log(f"Skipping existing {out_path}")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")
    if tmp_path.exists():
        tmp_path.unlink()

    log(f"Downloading {url}")
    with session.get(url, stream=True, timeout=(30, 300)) as resp:
        resp.raise_for_status()
        with tmp_path.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)

    tmp_path.rename(out_path)
    log(f"Wrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the JAWARA monthly assimilation temperature and geopotential-height files.")
    parser.add_argument("--date", required=True, help="Target date in YYYY-MM-DD.")
    parser.add_argument(
        "--out-dir",
        default=str(Path.home() / "data" / "ampere" / "jawara"),
        help="Directory to write the JAWARA NetCDF files.",
    )
    parser.add_argument(
        "--ca-bundle",
        default=os.environ.get("JAWARA_CA_BUNDLE", "/etc/ssl/cert.pem"),
        help="CA bundle to use for HTTPS requests.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=os.environ.get("JAWARA_INSECURE", "").lower() in {"1", "true", "yes"},
        help="Disable TLS certificate verification for this session.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files.")
    parser.add_argument("--dry-run", action="store_true", help="Print the selected download URLs and exit.")
    args = parser.parse_args()

    year, month, _day = parse_date(args.date)
    user = os.environ.get("JAWARA_USER") or "alexchartier"
    password = os.environ.get("JAWARA_PASS") or "hj5kW}kQgPAx69F"

    out_dir = Path(args.out_dir).expanduser()

    session = requests.Session()
    if args.insecure:
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
        session.verify = False
    elif args.ca_bundle:
        session.verify = args.ca_bundle

    try:
        login(session, user, password)
        log("Logged into JAWARA with approved access.")
        links = fetch_month_links(session, year, month)
        for key, href in links.items():
            out_name = Path(href).name
            out_path = out_dir / out_name
            log(f"{key}: {href}")
            if not args.dry_run:
                download_file(session, f"https://jawara.nipr.ac.jp{href}", out_path, overwrite=args.overwrite)
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
