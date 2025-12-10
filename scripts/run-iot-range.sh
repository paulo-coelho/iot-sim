#!/bin/bash
# Usage: ./run-iot.sh <folder> <region> <device_id_start> <device_id_end>
# Example: ./run-iot.sh scenarios/2x50 1 30 35

if [ "$#" -ne 4 ]; then
  echo "Usage: $0 <folder> <region> <device_id_start> <device_id_end>"
  exit 1
fi

FOLDER="$1"
REGION="$2"
START="$3"
END="$4"

# Check if region, start, and end are integers
if ! [[ "$REGION" =~ ^[0-9]+$ ]] || ! [[ "$START" =~ ^[0-9]+$ ]] || ! [[ "$END" =~ ^[0-9]+$ ]]; then
  echo "Error: <region>, <device_id_start>, and <device_id_end> must be integers."
  exit 1
fi

if [ "$START" -gt "$END" ]; then
  echo "Error: <device_id_start> must be less than or equal to <device_id_end>."
  exit 1
fi

REGION_ID=$(printf "%02d" "$REGION")

PIDS=()

trap 'echo "Killing child processes..."; kill "${PIDS[@]}" 2>/dev/null; exit 130' SIGINT

for (( i=START; i<=END; i++ )); do
  DEVICE_ID=$(printf "%03d" "$i")
  CONFIG_FILE="$FOLDER/device-$REGION_ID-$DEVICE_ID.json"
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "Warning: Config file '$CONFIG_FILE' does not exist. Skipping."
    continue
  fi
  uv run sim.py "$CONFIG_FILE" &
  PIDS+=($!)
done
wait
