#!/bin/bash
# Usage: ./run-iot.sh <folder> <region> <device_id>
# Example: ./run-iot.sh scenarios/2x50 1 30

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <folder> <region> <device_id>"
  exit 1
fi

FOLDER="$1"
REGION="$2"
DEVICE="$3"

# Check if region and device are integers
if ! [[ "$REGION" =~ ^[0-9]+$ ]] || ! [[ "$DEVICE" =~ ^[0-9]+$ ]]; then
  echo "Error: <region> and <device_id> must be integers."
  exit 1
fi

REGION_ID=$(printf "%02d" "$REGION")
DEVICE_ID=$(printf "%03d" "$DEVICE")

CONFIG_FILE="$FOLDER/device-$REGION_ID-$DEVICE_ID.json"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Error: Config file '$CONFIG_FILE' does not exist."
  exit 1
fi

uv run iot-sim.py "$CONFIG_FILE"
