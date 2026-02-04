#!/bin/bash

# Orchestrate the historical Federal Register backlog pipeline end-to-end.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/historical_federal_register_$(date +%Y%m%d_%H%M%S).log"

CURRENT_STEP="initialization"

log() {
    local message="$1"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    echo "${timestamp} | ${message}" | tee -a "${LOG_FILE}"
}

handle_error() {
    local exit_code=$?
    log "ERROR: Step '${CURRENT_STEP}' failed with exit code ${exit_code}."
    log "For details, inspect ${LOG_FILE}."
    exit "${exit_code}"
}

trap handle_error ERR INT

run_step() {
    local step_number="$1"
    local total_steps="$2"
    local description="$3"
    shift 3

    CURRENT_STEP="${description}"

    log "Starting step ${step_number}/${total_steps}: ${description}"
    printf "[%d/%d] %s...\n" "${step_number}" "${total_steps}" "${description}"

    {
        cd "${PROJECT_ROOT}"
        "$@"
    } 2>&1 | tee -a "${LOG_FILE}"

    local status=${PIPESTATUS[0]}
    if [[ "${status}" -ne 0 ]]; then
        return "${status}"
    fi

    log "Completed step ${step_number}/${total_steps}: ${description}"
    printf "[%d/%d] %s... done\n" "${step_number}" "${total_steps}" "${description}"
}

main() {
    log "=== Starting Federal Register historical pipeline ==="
    printf "Log file: %s\n\n" "${LOG_FILE}"

    local total_steps=2

    run_step 1 "${total_steps}" "Process historical Federal Register data" \
        python3 "${PROJECT_ROOT}/process_historical_register.py"

    run_step 2 "${total_steps}" "Publish processed historical backlog" \
        python3 "${PROJECT_ROOT}/publish_backlog.py"

    CURRENT_STEP="completed"
    log "=== Historical pipeline finished successfully ==="
    printf "\nAll steps completed successfully. See %s for full details.\n" "${LOG_FILE}"
}

main "$@"
