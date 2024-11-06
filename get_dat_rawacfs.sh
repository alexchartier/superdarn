#!/bin/bash

# Check if the correct number of arguments is provided
if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <start_yyyymm> <end_yyyymm>"
  exit 1
fi

# Parse input arguments
start_date=$1
end_date=$2

# Extract start year and month
start_year=${start_date:0:4}
start_month=${start_date:4:2}

# Extract end year and month
end_year=${end_date:0:4}
end_month=${end_date:4:2}

# Base directory
base_dir="/project/superdarn/data/rawacf"

# Path to Python
python3_path="/software/python-3.11.4/bin/python3"

# Loop over years
for year in $(seq $start_year $end_year); do
  # Determine the starting month for the current year
  if [ $year -eq $start_year ]; then
    month_start=$start_month
  else
    month_start=1
  fi

  # Determine the ending month for the current year
  if [ $year -eq $end_year ]; then
    month_end=$end_month
  else
    month_end=12
  fi

  # Loop over months
  for month in $(seq -f "%02g" $month_start $month_end); do
    # Directory for the year/month
    target_dir="$base_dir/$year/$month"

    # Check if the directory exists; if not, create it
    if [ ! -d "$target_dir" ]; then
      echo "Creating directory $target_dir"
      mkdir -p "$target_dir"
    fi

    # Run the sync script with the specified Python interpreter
    echo "$(date +'%Y-%m-%d %H:%M:%S') - Running sync for year $year, month $month"
    $python3_path /homes/superdarn/superdarn/globus/sync_radar_data_globus.py -y $year -m $month -t dattorawacf "$target_dir"
  done
done
