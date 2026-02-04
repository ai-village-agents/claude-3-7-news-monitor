#!/bin/bash

# Script to run the international courts monitor

echo "=== Running International Courts Monitor ==="

# Create log directory if it doesn't exist
mkdir -p ~/claude-3-7-news-monitor/logs

# Log file with timestamp
LOG_FILE=~/claude-3-7-news-monitor/logs/courts_monitor_$(date +%Y%m%d_%H%M%S).log

echo "Starting courts monitor at $(date)" | tee -a "$LOG_FILE"

# Run the courts monitor using Python
python3 ~/claude-3-7-news-monitor/scripts/run_courts_monitor.py 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
  echo "Courts monitor execution failed with exit code $EXIT_CODE" | tee -a "$LOG_FILE"
  exit $EXIT_CODE
fi

echo "=== Courts monitor execution completed successfully at $(date) ===" | tee -a "$LOG_FILE"
exit 0
