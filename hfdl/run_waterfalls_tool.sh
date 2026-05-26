#!/usr/bin/env bash
set -euo pipefail
DATA=/project/superdarn/data/rawrf/rawrf_14600_2p5m_aa
OUT="$DATA/waterfalls_tool"
mkdir -p "$OUT"
for ch in $(ls -1 "$DATA" | grep -E '^(m|i)[0-9]+$'); do
  /software/python-3.11.4/bin/python3 /tmp/fullband_waterfall.py \
    --dataset-root "$DATA" \
    --channel "$ch" \
    --center-hz 14.6e6 \
    --chunk-seconds 1 \
    --skip-seconds 0 \
    --total-seconds 60 \
    --step-seconds 1 \
    --nfft 8192 \
    --output "$OUT/waterfall_${ch}.png"
  echo "$OUT/waterfall_${ch}.png"
done
