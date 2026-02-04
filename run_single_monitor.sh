#!/bin/bash

# Script to run a single monitor with timeout protection

# Default timeout in seconds
TIMEOUT=120

# Parse arguments
MONITOR="all"
while getopts "m:t:" opt; do
  case $opt in
    m) MONITOR="$OPTARG" ;;
    t) TIMEOUT="$OPTARG" ;;
    *) echo "Usage: $0 [-m monitor] [-t timeout]" >&2
       echo "  -m: Monitor to run (cisa|usgs|noaa|sec|all)" >&2
       echo "  -t: Timeout in seconds (default: 120)" >&2
       exit 1 ;;
  esac
done

# Create log directory if it doesn't exist
mkdir -p ~/claude-3-7-news-monitor/logs

# Log file with timestamp
LOG_FILE=~/claude-3-7-news-monitor/logs/monitor_${MONITOR}_$(date +%Y%m%d_%H%M%S).log

echo "=== Running $MONITOR monitor with ${TIMEOUT}s timeout ===" | tee -a "$LOG_FILE"

# Use timeout command to prevent hanging
timeout "$TIMEOUT" python3 ~/claude-3-7-news-monitor/src/run_monitors_updated.py --monitor "$MONITOR" 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 124 ]; then
  echo "Monitor execution timed out after ${TIMEOUT} seconds" | tee -a "$LOG_FILE"
  exit 1
elif [ $EXIT_CODE -ne 0 ]; then
  echo "Monitor execution failed with exit code $EXIT_CODE" | tee -a "$LOG_FILE"
  exit $EXIT_CODE
fi

echo "=== Monitor execution completed successfully ===" | tee -a "$LOG_FILE"
exit 0
