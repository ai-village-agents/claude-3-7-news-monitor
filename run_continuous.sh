#!/usr/bin/env bash

set -u
set -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
DELAY_SECONDS=$((15 * 60))
keep_running=true

handle_interrupt() {
  echo
  echo "CTRL+C received. Shutting down gracefully..."
  keep_running=false
}

trap handle_interrupt INT

mkdir -p "${LOG_DIR}"

while [[ "${keep_running}" == "true" ]]; do
  run_timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
  log_filename="monitor_$(date +"%Y%m%d_%H%M%S").log"
  log_path="${LOG_DIR}/${log_filename}"

  echo "[${run_timestamp}] Starting monitor run; logging to ${log_path}"

  python3 "${SCRIPT_DIR}/run_monitors.py" "$@" 2>&1 | tee "${log_path}"
  command_status=${PIPESTATUS[0]}

  if (( command_status == 0 )); then
    echo "[${run_timestamp}] Monitor run completed successfully." | tee -a "${log_path}"
  else
    echo "[${run_timestamp}] Monitor run failed with exit code ${command_status}." | tee -a "${log_path}"
  fi

  if [[ "${keep_running}" != "true" ]]; then
    break
  fi

  echo "Sleeping for ${DELAY_SECONDS} seconds before the next run."
  sleep "${DELAY_SECONDS}" || true
done

echo "Monitor loop exited."
