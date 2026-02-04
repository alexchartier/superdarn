#!/usr/bin/env bash
set -euo pipefail

src="/project/superdarn/al_fitacf_3"
dest="/project/superdarn/fitacf"

echo "Moving .fit files from $src to $dest ..."
count=0

find "$src" -type f -name '*.fit' -print0 |
while IFS= read -r -d '' f; do
  rel=${f#"$src"/}
  mkdir -p "$dest/$(dirname "$rel")"
  mv "$f" "$dest/$rel"
  count=$((count + 1))
  echo "[$count] moved $rel"
done

echo "Done. Moved $count files."

