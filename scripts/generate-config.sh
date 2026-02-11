#!/bin/bash

# Default values
HOST="127.0.0.1"
PORT=5001
LAT=40.7
LON=-74.0
UUID=$(uuidgen 2>/dev/null || echo "56c5b6a5-1bc3-4238-9ff5-2f93d8301fcb")
TEMP_MIN=20.0
TEMP_MAX=30.0
DROP=5
BATT_IDLE=0.1
BATT_TX=1
BATT_CHG=90
PROFILES='[{"probability": 100, "min": 0.1, "max": 0.5}]'

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo "Options:"
  echo "  -h HOST     Server host (default: $HOST)"
  echo "  -p PORT     Server port (default: $PORT)"
  echo "  -a LAT      Latitude (default: $LAT)"
  echo "  -o LON      Longitude (default: $LON)"
  echo "  -u UUID     UUID string (default: generated)"
  echo "  -s MIN      Min temperature (default: $TEMP_MIN)"
  echo "  -e MAX      Max temperature (default: $TEMP_MAX)"
  echo "  -d DROP     Drop percentage (default: $DROP)"
  echo "  -i IDLE     Battery idle discharge (default: $BATT_IDLE)"
  echo "  -t TX       Battery transmit discharge (default: $BATT_TX)"
  echo "  -c CHARGE   Battery charge % (0-100, default: $BATT_CHG)"
  echo "  -f JSON     Delay profiles as JSON array string"
  echo "  --help      Show this help message"
  exit 0
}

# Parse flags
while getopts "h:p:a:o:u:s:e:d:i:t:c:f:-:" opt; do
  case $opt in
    -)
      case "${OPTARG}" in
        help) usage ;;
        *) echo "Unknown option --${OPTARG}"; exit 1 ;;
      esac ;;
    h) HOST=$OPTARG ;;
    p) PORT=$OPTARG ;;
    a) LAT=$OPTARG ;;
    o) LON=$OPTARG ;;
    u) UUID=$OPTARG ;;
    s) TEMP_MIN=$OPTARG ;;
    e) TEMP_MAX=$OPTARG ;;
    d) DROP=$OPTARG ;;
    i) BATT_IDLE=$OPTARG ;;
    t) BATT_TX=$OPTARG ;;
    c) BATT_CHG=$OPTARG ;;
    f) PROFILES=$OPTARG ;;
    ?) usage ;;
  esac
done

# Check if battery charge is a number and between 0-100
if ! [[ "$BATT_CHG" =~ ^[0-9]+(\.[0-9]+)?$ ]] || (( $(echo "$BATT_CHG > 100" | bc -l) )) || (( $(echo "$BATT_CHG < 0" | bc -l) )); then
  echo "Error: Battery charge (-c) must be a number between 0 and 100." >&2
  exit 1
fi

# Basic check for Port range
if [[ "$PORT" -lt 1024 || "$PORT" -gt 65535 ]]; then
  echo "Error: Port (-p) must be between 1024 and 65535." >&2
  exit 1
fi

# Verify PROFILES is valid JSON
if ! echo "$PROFILES" | jq empty >/dev/null 2>&1; then
  echo "Error: Invalid JSON format provided for delay profiles (-f)." >&2
  exit 1
fi

# Generate config JSON
jq -n \
  --arg host "$HOST" \
  --argjson port "$PORT" \
  --argjson lat "$LAT" \
  --argjson lon "$LON" \
  --arg uuid "$UUID" \
  --argjson t_min "$TEMP_MIN" \
  --argjson t_max "$TEMP_MAX" \
  --argjson drop "$DROP" \
  --argjson b_idle "$BATT_IDLE" \
  --argjson b_tx "$BATT_TX" \
  --argjson b_chg "$BATT_CHG" \
  --argjson profiles "$PROFILES" \
  '{
    "server_host": $host,
    "server_port": $port,
    "resource_path": ["device", "data"],
    "coordinate": {
      "latitude": $lat,
      "longitude": $lon
    },
    "temperature_range": [$t_min, $t_max],
    "drop_percentage": $drop,
    "delay_profiles": $profiles,
    "uuid": $uuid,
    "battery_idle_discharge": $b_idle,
    "battery_transmit_discharge": $b_tx,
    "battery_charge": $b_chg
  }'
