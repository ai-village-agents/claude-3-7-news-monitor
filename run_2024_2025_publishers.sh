#!/bin/bash
set -e

cd "$(dirname "$0")"

# Run 2024 publisher
while true; do
  echo "Running 2024 batch at $(date)"
  python3 systematic_batch_publisher.py --batch-size 400 --year 2024
  sleep 120  # 2 minute delay
done &

# Run 2025 publisher
while true; do
  echo "Running 2025 batch at $(date)"
  python3 systematic_batch_publisher.py --batch-size 400 --year 2025
  sleep 120  # 2 minute delay
done &

echo "Both publishers are running in the background"
