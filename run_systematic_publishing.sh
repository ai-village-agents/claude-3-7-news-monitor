#!/usr/bin/env bash

# Run the systematic batch publisher with appropriate settings
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATCH_SIZE=${1:-100}  # Default batch size of 100
MAX_BATCHES=${2:-5}   # Default to 5 batches
DELAY_MINUTES=${3:-3} # Default 3 minute delay between batches

echo "Starting systematic batch publishing with:"
echo "- Batch size: $BATCH_SIZE stories per batch"
echo "- Maximum batches: $MAX_BATCHES"
echo "- Delay between batches: $DELAY_MINUTES minutes"

# Log file for the run
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_DIR="${SCRIPT_DIR}/logs/publishing_runs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/systematic_publishing_${TIMESTAMP}.log"

echo "Logging to: $LOG_FILE"

# Run in continuous mode with specified parameters
python3 "${SCRIPT_DIR}/systematic_batch_publisher.py" \
  --continuous \
  --batch-size "$BATCH_SIZE" \
  --max-batches "$MAX_BATCHES" \
  --delay "$DELAY_MINUTES" | tee -a "$LOG_FILE"

echo "Systematic publishing complete"
echo "See $LOG_FILE for details"
