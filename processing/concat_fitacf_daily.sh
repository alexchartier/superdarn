#!/usr/bin/env bash
# Concatenate hourly fitacf .bz2 files into daily per-radar files.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./concat_fitacf_daily.sh [-i INPUT_DIR] [-o OUTPUT_DIR] [-r radar1,radar2] [-p JOBS] [-f]
  -i  Root directory containing the year/month subfolders with *.fitacf.bz2 files (default: fitacf_bzip)
  -o  Output directory for concatenated daily files (default: fitacf_daily)
  -r  Comma-separated radar codes to include; if omitted, process all radars
  -p  Number of radar/day concatenations to run in parallel (default: 1)
  -f  Overwrite existing daily outputs instead of skipping them
  -h  Show this help
EOF
}

input_dir="fitacf_bzip"
output_dir="fitacf_daily"
radar_filter=""
force=0
parallel_jobs=1

while getopts "i:o:r:p:fh" opt; do
  case "${opt}" in
    i) input_dir="${OPTARG}" ;;
    o) output_dir="${OPTARG}" ;;
    r) radar_filter="${OPTARG}" ;;
    p) parallel_jobs="${OPTARG}" ;;
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
echo "  Parallel jobs: ${parallel_jobs}"

input_dir="${input_dir%/}"
output_dir="${output_dir%/}"

if [[ ! -d "${input_dir}" ]]; then
  echo "Input directory not found: ${input_dir}" >&2
  exit 1
fi

if ! [[ "${parallel_jobs}" =~ ^[0-9]+$ ]] || [[ "${parallel_jobs}" -lt 1 ]]; then
  echo "Parallel jobs must be a positive integer: ${parallel_jobs}" >&2
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
index_count=0
processed_count=0
skipped_existing=0
declare -a job_pids=()
tmp_root="$(mktemp -d)"
find_error_log=""
entries_file=""
group_counts_file=""

cleanup() {
  rm -rf "${tmp_root}"
  if [[ -n "${entries_file:-}" && -f "${entries_file}" ]]; then
    rm -f "${entries_file}"
  fi
  if [[ -n "${group_counts_file:-}" && -f "${group_counts_file}" ]]; then
    rm -f "${group_counts_file}"
  fi
  # Best-effort kill of any remaining background jobs
  if [[ ${#job_pids[@]} -gt 0 ]]; then
    kill "${job_pids[@]}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

wait_for_slot() {
  # Wait until the number of running jobs is below the limit
  while (( ${#job_pids[@]} >= parallel_jobs )); do
    wait "${job_pids[0]}"
    job_pids=( "${job_pids[@]:1}" )
  done
}

run_group_job() {
  local ymd="${1}"
  local radar="${2}"
  local out_file="${3}"
  local list_file="${4}"

  local count=0
  local total=0
  local -a files=()
  while IFS= read -r f; do
    files+=( "${f}" )
    [[ -n "${f}" ]] && ((total++))
  done < "${list_file}"

  if (( total == 0 )); then
    echo "  [${ymd} ${radar}] no files found in list ${list_file}, skipping" >&2
    rm -f "${list_file}"
    return 0
  fi

  echo "  [${ymd} ${radar}] concatenating ${total} files -> ${out_file}"
  for f in "${files[@]}"; do
    [[ -z "${f}" ]] && continue
    ((count++))
    bzip2 -dc "${f}" >> "${out_file}"
    if (( count % 100 == 0 )); then
      echo "  [${ymd} ${radar}] ${count}/${total} files done" >&2
    fi
  done

  rm -f "${list_file}"
  echo "  [${ymd} ${radar}] completed ${count} files -> ${out_file}"
}

echo "Scanning input directory for .fitacf.bz2 files (progress every 500 files)..."
echo "  This step sorts the full list first, so a large tree can take a while before concatenation starts."

generate_entries() {
  if ! find -L "${input_dir}" -type f -name "*.fitacf.bz2" 2>>"${find_error_log}" \
    | while read -r file; do
        base="$(basename "${file}")"
        IFS='.' read -r ymd hhmm ss radar _rest <<< "${base}"
        if [[ -z "${ymd:-}" || -z "${radar:-}" ]]; then
          continue
        fi
        if ! is_allowed_radar "${radar}"; then
          continue
        fi
        ((index_count++))
        if (( index_count % 500 == 0 )); then
          echo "  Indexed ${index_count} files so far..." >&2
        fi
        printf "%s\t%s\t%s\t%s\t%s\n" "${ymd}" "${radar}" "${hhmm}" "${ss}" "${file}"
      done
  then
    local find_status=${PIPESTATUS[0]:-1}
    echo "find failed while scanning ${input_dir} (exit ${find_status}). See ${find_error_log}." >&2
    return "${find_status}"
  fi
}

current_key=""
group_list_file=""
out_file=""
out_dir=""
ymd=""
radar=""
skip_current_key=0
find_error_log="${tmp_root}/find_errors.log"
entries_file="$(mktemp "${tmp_root}/entries.XXXX")"
: > "${find_error_log}"

echo "Quick visibility check (first match, maxdepth 3)..."
sample_match="$(find -L "${input_dir}" -maxdepth 3 -type f -name "*.fitacf.bz2" -print -quit 2>/dev/null || true)"
if [[ -n "${sample_match}" ]]; then
  echo "  Found: ${sample_match}"
else
  echo "  No files seen in the quick sample; continuing to full scan..." >&2
fi

echo "Building file list (following symlinks)..."
if ! generate_entries > "${entries_file}"; then
  echo "Aborting because find reported an error. See ${find_error_log} for details." >&2
  exit 1
fi

group_counts_file="$(mktemp "${tmp_root}/group_counts.XXXX")"
cut -f1,2 "${entries_file}" | sort | uniq -c | sort -nr > "${group_counts_file}"

entry_count=$(wc -l < "${entries_file}")
group_count=$(wc -l < "${group_counts_file}")
echo "Indexed ${entry_count} files before sorting."
echo "Unique day/radar groups: ${group_count}"
echo "Top groups (count day.radar):"
head -n 10 "${group_counts_file}"

if (( entry_count == 0 )); then
  echo "No .fitacf.bz2 files found under ${input_dir}. Is the path correct/mounted and readable?" >&2
  if [[ -s "${find_error_log}" ]]; then
    echo "find stderr (last 20 lines):" >&2
    tail -n 20 "${find_error_log}" >&2
  fi
  exit 1
fi

while IFS=$'\t' read -r ymd radar hhmm ss file; do
  key="${ymd}.${radar}"

  if [[ "${key}" != "${current_key}" ]]; then
    # Launch previous group if needed
    if [[ -n "${current_key}" && ${skip_current_key} -eq 0 && -n "${group_list_file}" ]]; then
      wait_for_slot
      if (( parallel_jobs == 1 )); then
        run_group_job "${prev_ymd}" "${prev_radar}" "${prev_out_file}" "${group_list_file}"
      else
        run_group_job "${prev_ymd}" "${prev_radar}" "${prev_out_file}" "${group_list_file}" &
        job_pids+=( "$!" )
      fi
    elif [[ -n "${group_list_file}" ]]; then
      rm -f "${group_list_file}"
    fi

    current_key="${key}"
    prev_ymd="${ymd}"
    prev_radar="${radar}"
    out_dir="${output_dir}/${ymd:0:4}/${ymd:4:2}"
    prev_out_file="${out_dir}/${ymd}.${radar}.fitacf"
    skip_current_key=0

    if [[ -f "${prev_out_file}" && ${force} -eq 0 ]]; then
      echo "Skipping existing output: ${prev_out_file}"
      skip_current_key=1
      group_list_file=""
      ((skipped_existing++))
      continue
    fi

    mkdir -p "${out_dir}"
    : > "${prev_out_file}"
    echo "Writing ${ymd} ${radar} -> ${prev_out_file}"
    group_list_file="$(mktemp "${tmp_root}/group.${ymd}.${radar}.XXXX")"
  fi

  if [[ ${skip_current_key} -eq 1 ]]; then
    continue
  fi

  ((processed_count++))
  if (( processed_count % 100 == 0 )); then
    echo "  Queued ${processed_count} files so far..." >&2
  fi

  echo "${file}" >> "${group_list_file}"
done < <(sort -t $'\t' -k1,1 -k2,2 -k3,3 -k4,4 "${entries_file}")

# Final group
if [[ -n "${current_key}" && ${skip_current_key} -eq 0 && -n "${group_list_file}" ]]; then
  wait_for_slot
  if (( parallel_jobs == 1 )); then
    run_group_job "${prev_ymd}" "${prev_radar}" "${prev_out_file}" "${group_list_file}"
  else
    run_group_job "${prev_ymd}" "${prev_radar}" "${prev_out_file}" "${group_list_file}" &
    job_pids+=( "$!" )
  fi
elif [[ -n "${group_list_file}" ]]; then
  rm -f "${group_list_file}"
fi

if (( processed_count == 0 )); then
  if (( skipped_existing > 0 )); then
    echo "All ${skipped_existing} outputs already exist. Use -f to overwrite." >&2
    exit 0
  fi
  echo "No .fitacf.bz2 files queued for processing under ${input_dir}." >&2
  exit 1
fi

# Wait for all jobs to finish
while (( ${#job_pids[@]} > 0 )); do
  wait "${job_pids[0]}"
  job_pids=( "${job_pids[@]:1}" )
done
