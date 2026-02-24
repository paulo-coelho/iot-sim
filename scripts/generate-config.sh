#!/bin/bash

# No default values; require template JSON as first argument
TEMPLATE_JSON="$1"
shift

if [[ -z "$TEMPLATE_JSON" || ! -f "$TEMPLATE_JSON" ]]; then
  echo "Error: First argument must be a path to a template JSON file." >&2
  exit 1
fi

# Initialize override variables as empty
HOST=""
PORT=""
LAT=""
LON=""
UUID=""
TEMP_MIN=""
TEMP_MAX=""
DROP=""
BATT_IDLE=""
BATT_TX=""
BATT_CHG=""
PROFILES=""


usage() {
  echo "Usage: $0 TEMPLATE_JSON [OPTIONS]"
  echo "  TEMPLATE_JSON   Path to a template JSON file with default config values."
  echo "Options (override template fields):"
  echo "  -h HOST     Server host"
  echo "  -p PORT     Server port"
  echo "  -a LAT      Latitude"
  echo "  -o LON      Longitude"
  echo "  -u UUID     UUID string"
  echo "  -s MIN      Min temperature"
  echo "  -e MAX      Max temperature"
  echo "  -d DROP     Drop percentage"
  echo "  -i IDLE     Battery idle discharge"
  echo "  -t TX       Battery transmit discharge"
  echo "  -c CHARGE   Battery charge % (0-100)"
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


# Check if battery charge is a number and between 0-100 (if provided)
if [[ -n "$BATT_CHG" ]]; then
  if ! [[ "$BATT_CHG" =~ ^[0-9]+(\.[0-9]+)?$ ]] || (( $(echo "$BATT_CHG > 100" | bc -l) )) || (( $(echo "$BATT_CHG < 0" | bc -l) )); then
    echo "Error: Battery charge (-c) must be a number between 0 and 100." >&2
    exit 1
  fi
fi

# Basic check for Port range (if provided)
if [[ -n "$PORT" ]]; then
  if [[ "$PORT" -lt 1024 || "$PORT" -gt 65535 ]]; then
    echo "Error: Port (-p) must be between 1024 and 65535." >&2
    exit 1
  fi
fi

# Verify PROFILES is valid JSON (if provided)
if [[ -n "$PROFILES" ]]; then
  if ! echo "$PROFILES" | jq empty >/dev/null 2>&1; then
    echo "Error: Invalid JSON format provided for delay profiles (-f)." >&2
    exit 1
  fi
fi

# Build jq filter for overrides
JQ_FILTER='.'
[[ -n "$HOST" ]] && JQ_FILTER+=" | .server_host=\"$HOST\""
[[ -n "$PORT" ]] && JQ_FILTER+=" | .server_port=($PORT|tonumber)"
[[ -n "$LAT" ]] && JQ_FILTER+=" | .coordinate.latitude=($LAT|tonumber)"
[[ -n "$LON" ]] && JQ_FILTER+=" | .coordinate.longitude=($LON|tonumber)"
[[ -n "$UUID" ]] && JQ_FILTER+=" | .uuid=\"$UUID\""
[[ -n "$TEMP_MIN" ]] && JQ_FILTER+=" | .temperature_range[0]=($TEMP_MIN|tonumber)"
[[ -n "$TEMP_MAX" ]] && JQ_FILTER+=" | .temperature_range[1]=($TEMP_MAX|tonumber)"
[[ -n "$DROP" ]] && JQ_FILTER+=" | .drop_percentage=($DROP|tonumber)"
[[ -n "$BATT_IDLE" ]] && JQ_FILTER+=" | .battery_idle_discharge=($BATT_IDLE|tonumber)"
[[ -n "$BATT_TX" ]] && JQ_FILTER+=" | .battery_transmit_discharge=($BATT_TX|tonumber)"
[[ -n "$BATT_CHG" ]] && JQ_FILTER+=" | .battery_charge=($BATT_CHG|tonumber)"
[[ -n "$PROFILES" ]] && JQ_FILTER+=" | .delay_profiles=($PROFILES|fromjson)"

# Output the final config
jq "$JQ_FILTER" "$TEMPLATE_JSON"

