#!/bin/bash

# Master script to coordinate backlog publishing and courts monitoring
echo "=== Starting publishing pipeline at $(date) ==="

# Create log directory if it doesn't exist
mkdir -p ~/claude-3-7-news-monitor/logs

# Log file with timestamp
LOG_FILE=~/claude-3-7-news-monitor/logs/publishing_pipeline_$(date +%Y%m%d_%H%M%S).log

echo "Starting publishing pipeline at $(date)" | tee -a "$LOG_FILE"

# Check if it's time to run the international courts monitor (around 12:00 PM PT)
CURRENT_HOUR=$(date +%H)
CURRENT_MINUTE=$(date +%M)

echo "Current time: $CURRENT_HOUR:$CURRENT_MINUTE" | tee -a "$LOG_FILE"

# Function to run the courts monitor
run_courts_monitor() {
    echo "=== Running International Courts Monitor at $(date) ===" | tee -a "$LOG_FILE"
    cd ~/claude-3-7-news-monitor
    ./scripts/run_courts_monitor.py 2>&1 | tee -a "$LOG_FILE"
}

# Function to run the backlog publisher
run_backlog_publisher() {
    echo "=== Running Backlog Publisher at $(date) ===" | tee -a "$LOG_FILE"
    cd ~/claude-3-7-news-monitor
    python3 ./publish_backlog.py 2>&1 | tee -a "$LOG_FILE"
}

# Run the courts monitor if it's around 12:00 PM PT
if [ "$CURRENT_HOUR" = "12" ] || ([ "$CURRENT_HOUR" = "11" ] && [ "$CURRENT_MINUTE" -ge "55" ]); then
    echo "It's time for the courts monitoring window!" | tee -a "$LOG_FILE"
    run_courts_monitor
else
    echo "Not yet time for the courts monitoring window. Will continue with backlog publishing." | tee -a "$LOG_FILE"
fi

# Always run the backlog publisher
run_backlog_publisher

echo "=== Publishing pipeline completed at $(date) ===" | tee -a "$LOG_FILE"
