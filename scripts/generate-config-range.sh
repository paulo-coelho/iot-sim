#!/bin/bash

if [ "$#" -lt 4 ]; then
  echo "Usage: $0 <folder> <region> <initial_port> <number_of_devs> <ADDITIONAL-ARGUMENTS-T0-GENERATE-CONFIG>"
  exit 1
fi

FOLDER="$1"
REGION="$2"
PORT="$3"
DEVS="$4"

mkdir -p $FOLDER

# Check if region, start, and end are integers
if ! [[ "$REGION" =~ ^[0-9]+$ ]] || ! [[ "$PORT" =~ ^[0-9]+$ ]] || ! [[ "$DEVS" =~ ^[0-9]+$ ]]; then
  echo "Error: <region>, <initial_port>, and <number_of_devs> must be integers."
  exit 1
fi

REGION_ID=$(printf "%02d" "$REGION")

for (( i=1; i<=$DEVS; i++ )); do
  DEVICE_ID=$(printf "%03d" "$i")
  CONFIG_FILE="$FOLDER/device-$REGION_ID-$DEVICE_ID.json"
  ./generate-config.sh -p $(($PORT+$i)) "${@:5}" > $CONFIG_FILE
done
