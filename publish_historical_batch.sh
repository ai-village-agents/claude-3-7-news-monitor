#!/usr/bin/env bash

# Publish a batch of historical stories from existing mining data
set -euo pipefail

BATCH_SIZE=${1:-50} # Default to 50 stories if not specified

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs/historical_runs"
mkdir -p "${LOG_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/publishing_batch_${TIMESTAMP}.log"

echo "Starting batch publication of $BATCH_SIZE historical stories..."
echo "Log file: $LOG_FILE"

python3 "${PROJECT_ROOT}/publish_historical_stories.py" \
    --batch-size "${BATCH_SIZE}" | tee -a "${LOG_FILE}"

cd "${PROJECT_ROOT}"
git add -A

if git diff --cached --quiet; then
    echo "No changes detected. Skipping commit and push."
else
    git commit -m "Published batch of $BATCH_SIZE historical Federal Register stories"
    git push
fi

echo "Batch publication complete"
