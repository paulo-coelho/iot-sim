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
  DEVICE_ID=$(printf "%04d" "$i")
  CONFIG_FILE="$FOLDER/device-$REGION_ID-$DEVICE_ID.json"
  ./generate-config.sh "${@:5}" -p $(($PORT+$i)) > $CONFIG_FILE

  # Extract server_host and server_port using jq
  SERVER_HOST=$(jq -r '.server_host' "$CONFIG_FILE")
  SERVER_PORT=$(jq -r '.server_port' "$CONFIG_FILE")
  DEVICE_URI="coap://$SERVER_HOST:$SERVER_PORT/device/data"
  DEVICE_URIS+=("$DEVICE_URI")
done

# Write devices-$REGION_ID.json
DEVICES_JSON="$FOLDER/devices-$REGION_ID.json"
{
  echo '{'
  echo '  "devices": ['
  for idx in "${!DEVICE_URIS[@]}"; do
    URI=${DEVICE_URIS[$idx]}
    if [ "$idx" -lt $((${#DEVICE_URIS[@]}-1)) ]; then
      echo "    \"$URI\","
    else
      echo "    \"$URI\""
    fi
  done
  echo '  ]'
  echo '}'
} > "$DEVICES_JSON"




