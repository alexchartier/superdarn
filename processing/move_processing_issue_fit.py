"""
Move .fit files from processing issues into the fitacf_3 hierarchy.

By default it looks under /project/superdarn/processing_issues/<YYYY>/<MM>
and moves files to /project/superdarn/data/fitacf_3/<YYYY>/<MM>.
"""

import argparse
import shutil
import sys
from pathlib import Path


def iter_issue_files(root: Path):
    """Yield (src_path, year, month) for .fit files under the issue root."""
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            for src in sorted(month_dir.glob("*.fit")):
                yield src, year_dir.name, month_dir.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move .fit files out of processing_issues into fitacf_3.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--issue-dir",
        default="/project/superdarn/processing_issues",
        help="Root of processing issues directories (without /YYYY/MM).",
    )
    parser.add_argument(
        "--dest-dir",
        default="/project/superdarn/data/fitacf_3",
        help="Destination base directory (without /YYYY/MM).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite destination files if they already exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be moved without making changes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    issue_root = Path(args.issue_dir)
    dest_root = Path(args.dest_dir)

    moved = 0
    skipped = 0

    for src, year, month in iter_issue_files(issue_root):
        dest_dir = dest_root / year / month
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        if dest.exists():
            if args.overwrite:
                try:
                    dest.unlink()
                except OSError as exc:  # noqa: BLE001
                    print(f"Could not remove existing {dest}: {exc}", file=sys.stderr)
                    skipped += 1
                    continue
            else:
                print(f"Skipping {src} -> {dest} (destination exists)", file=sys.stderr)
                skipped += 1
                continue

        if args.dry_run:
            print(f"[DRY RUN] {src} -> {dest}")
            moved += 1
            continue

        try:
            shutil.move(str(src), str(dest))
            print(f"Moved {src} -> {dest}")
            moved += 1
        except OSError as exc:  # noqa: BLE001
            print(f"Failed to move {src} -> {dest}: {exc}", file=sys.stderr)
            skipped += 1

    print(f"Done. Moved: {moved}, skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
