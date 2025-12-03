#!/usr/bin/env bash
# Concatenate hourly fitacf .bz2 files into daily per-radar files.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./concat_fitacf_daily.sh [-i INPUT_DIR] [-o OUTPUT_DIR] [-r radar1,radar2] [-f]
  -i  Root directory containing the year/month subfolders with *.fitacf.bz2 files (default: fitacf_bzip)
  -o  Output directory for concatenated daily files (default: fitacf_daily)
  -r  Comma-separated radar codes to include; if omitted, process all radars
  -f  Overwrite existing daily outputs instead of skipping them
  -h  Show this help
EOF
}

input_dir="fitacf_bzip"
output_dir="fitacf_daily"
radar_filter=""
force=0

while getopts "i:o:r:fh" opt; do
  case "${opt}" in
    i) input_dir="${OPTARG}" ;;
    o) output_dir="${OPTARG}" ;;
    r) radar_filter="${OPTARG}" ;;
    f) force=1 ;;
    h) usage; exit 0 ;;
    *) usage >&2; exit 1 ;;
  esac
done

echo "Starting concat_fitacf_daily"
echo "  Input directory: ${input_dir}"
echo "  Output directory: ${output_dir}"
echo "  Radar filter: ${radar_filter:-all}"
echo "  Force overwrite: ${force}"

if [[ ! -d "${input_dir}" ]]; then
  echo "Input directory not found: ${input_dir}" >&2
  exit 1
fi

if ! command -v bzip2 >/dev/null 2>&1; then
  echo "bzip2 is required but not found in PATH" >&2
  exit 1
fi

radar_allow=()
if [[ -n "${radar_filter}" ]]; then
  IFS=',' read -r -a radar_allow <<< "${radar_filter}"
fi

is_allowed_radar() {
  local radar="${1}"
  if [[ ${#radar_allow[@]} -eq 0 ]]; then
    return 0
  fi
  local r
  for r in "${radar_allow[@]}"; do
    if [[ "${radar}" == "${r}" ]]; then
      return 0
    fi
  done
  return 1
}

current_key=""
skip_current_key=0

find "${input_dir}" -type f -name "*.fitacf.bz2" \
  | while read -r file; do
      base="$(basename "${file}")"
      IFS='.' read -r ymd hhmm ss radar _rest <<< "${base}"
      if [[ -z "${ymd:-}" || -z "${radar:-}" ]]; then
        continue
      fi
      if ! is_allowed_radar "${radar}"; then
        continue
      fi
      printf "%s\t%s\t%s\t%s\t%s\n" "${ymd}" "${radar}" "${hhmm}" "${ss}" "${file}"
    done \
  | sort -t $'\t' -k1,1 -k2,2 -k3,3 -k4,4 \
  | while IFS=$'\t' read -r ymd radar hhmm ss file; do
      key="${ymd}.${radar}"
      if [[ "${key}" != "${current_key}" ]]; then
        current_key="${key}"
        skip_current_key=0
        out_dir="${output_dir}/${ymd:0:4}/${ymd:4:2}"
        out_file="${out_dir}/${ymd}.${radar}.fitacf"

        if [[ -f "${out_file}" && ${force} -eq 0 ]]; then
          echo "Skipping existing output: ${out_file}"
          skip_current_key=1
          continue
        fi

        mkdir -p "${out_dir}"
        : > "${out_file}"
        echo "Writing ${ymd} ${radar} -> ${out_file}"
      fi

      if [[ ${skip_current_key} -eq 1 ]]; then
        continue
      fi

      echo "  Appending ${file} to ${out_file}"
      bzip2 -dc "${file}" >> "${out_file}"
    done
