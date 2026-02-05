#!/usr/bin/env bash

# Process a specific year of Federal Register data with rate limiting
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <year>"
    echo "Example: $0 2022"
    exit 1
fi

YEAR="$1"
if ! [[ "$YEAR" =~ ^20(20|21|22|23)$ ]]; then
    echo "Error: Year must be 2020, 2021, 2022, or 2023"
    exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs/historical_runs"
mkdir -p "${LOG_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/rate_limited_${YEAR}_${TIMESTAMP}.log"
OUTPUT_FILE="${LOG_DIR}/federal_register_results_${YEAR}.txt"
DATE_RANGE="${YEAR}-01-01,${YEAR}-12-31"

# Smaller page ranges for better rate limiting handling
PAGE_RANGES="20-35,35-50,50-65,65-80,80-95,95-110"

echo "Starting rate-limited mining for $YEAR..."
echo "Log file: $LOG_FILE"

python3 "${PROJECT_ROOT}/rate_limited_register_miner.py" \
    --num-threads 6 \
    --page-ranges "${PAGE_RANGES}" \
    --date-range "${DATE_RANGE}" \
    --output-file "${OUTPUT_FILE}" \
    --max-retries 7 \
    --base-delay 3.0 \
    --max-delay 120.0 | tee -a "${LOG_FILE}"

echo "Mining completed for $YEAR. Publishing stories..."

python3 "${PROJECT_ROOT}/publish_historical_stories.py" \
    --year "${YEAR}" \
    --batch-size 50 | tee -a "${LOG_FILE}"

cd "${PROJECT_ROOT}"
git add -A

if git diff --cached --quiet; then
    echo "No changes detected. Skipping commit and push."
else
    git commit -m "Published Federal Register stories from ${YEAR} mining run"
    git push
fi

echo "Process completed for $YEAR"
