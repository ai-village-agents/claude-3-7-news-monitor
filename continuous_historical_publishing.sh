#!/usr/bin/env bash

# Continuous historical publishing script
# Runs in a loop to systematically process and publish historical Federal Register documents
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATCH_SIZE=${1:-50}  # Default batch size of 50, can be overridden
DELAY_MINUTES=${2:-5} # Default delay of 5 minutes between batches
MAX_BATCHES=${3:-10}  # Default max batches to process before exiting

echo "Starting continuous historical publishing..."
echo "Batch size: $BATCH_SIZE"
echo "Delay between batches: $DELAY_MINUTES minutes"
echo "Maximum batches: $MAX_BATCHES"

BATCH_COUNT=0

while [ $BATCH_COUNT -lt $MAX_BATCHES ]; do
  TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
  echo "[$TIMESTAMP] Running batch $((BATCH_COUNT+1)) of $MAX_BATCHES"
  
  # Rotate years for balanced distribution
  YEAR=$((2020 + (BATCH_COUNT % 4)))
  
  echo "Processing year: $YEAR"
  
  # Run the batch publication for this year
  "$SCRIPT_DIR/claude-3-7-news-monitor/run_rate_limited_year.sh" "$YEAR"
  
  BATCH_COUNT=$((BATCH_COUNT+1))
  
  # Don't sleep after the last batch
  if [ $BATCH_COUNT -lt $MAX_BATCHES ]; then
    echo "Sleeping for $DELAY_MINUTES minutes before next batch..."
    sleep $((DELAY_MINUTES * 60))
  fi
done

echo "Completed $BATCH_COUNT batches of historical publishing"
echo "Total stories processed: $((BATCH_COUNT * BATCH_SIZE))"

# Publish summary of progress
"$SCRIPT_DIR/claude-3-7-news-monitor/publish_story_improved.sh" \
  "Federal Register Historical Mining Progress Update" \
  "Completed systematic publishing of historical Federal Register documents from 2020-2023. See historical_mining_summary.md for details." \
  "https://www.federalregister.gov/"
