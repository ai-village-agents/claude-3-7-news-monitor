#!/usr/bin/env bash

# Run the historical mining pipeline with rate limiting, publish results, and push changes.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs/historical_runs"
mkdir -p "${LOG_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/rate_limited_mining_${TIMESTAMP}.log"
CURRENT_STEP="initialization"

exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
    local message="$1"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    echo "${timestamp} | ${message}"
}

handle_error() {
    local exit_code=$?
    local line_no=$1
    log "ERROR: Step '${CURRENT_STEP}' failed at line ${line_no} with exit code ${exit_code}."
    log "Review ${LOG_FILE} for details."
    exit "${exit_code}"
}

trap 'handle_error ${LINENO}' ERR INT

# Use smaller page chunks to better handle rate limiting
PAGE_RANGES="20-35,35-50,50-65,65-80,80-95,95-110"

mine_year_with_rate_limiting() {
    local year="$1"
    local output_file="${LOG_DIR}/federal_register_results_${year}.txt"
    local date_range="${year}-01-01,${year}-12-31"

    python3 "${PROJECT_ROOT}/rate_limited_register_miner.py" \
        --num-threads 6 \
        --page-ranges "${PAGE_RANGES}" \
        --date-range "${date_range}" \
        --output-file "${output_file}" \
        --max-retries 7 \
        --base-delay 3.0 \
        --max-delay 120.0
}

publish_batch() {
    python3 "${PROJECT_ROOT}/publish_historical_stories.py" --batch-size 100
}

git_push_changes() {
    cd "${PROJECT_ROOT}"
    git add -A
    git status --short

    if git diff --cached --quiet; then
        log "No staged changes detected. Skipping commit and push."
        return 0
    fi

    local commit_message="Historical mining run ${TIMESTAMP} with rate limiting"
    git commit -m "${commit_message}"
    git push
}

run_step() {
    local step="$1"
    local total="$2"
    local description="$3"
    shift 3

    CURRENT_STEP="${description}"

    log "Starting step ${step}/${total}: ${description}"
    printf "[%d/%d] %s...\n" "${step}" "${total}" "${description}"

    (
        cd "${PROJECT_ROOT}"
        "$@"
    )

    log "Completed step ${step}/${total}: ${description}"
    printf "[%d/%d] %s... done\n" "${step}" "${total}" "${description}"
}

main() {
    log "=== Rate-limited historical mining run started ==="
    printf "Log file: %s\n\n" "${LOG_FILE}"

    # Starting with 2023 to prioritize more recent data
    local years=(2023 2022 2021 2020)
    local total_steps=$(( ${#years[@]} + 2 ))
    local step_counter=1

    for year in "${years[@]}"; do
        run_step "${step_counter}" "${total_steps}" "Mine Federal Register data for ${year} with rate limiting" \
            mine_year_with_rate_limiting "${year}"
        ((step_counter++))
    done

    run_step "${step_counter}" "${total_steps}" "Publish up to 100 historical stories" \
        publish_batch
    ((step_counter++))

    run_step "${step_counter}" "${total_steps}" "Commit and push mining updates" \
        git_push_changes

    CURRENT_STEP="completed"
    log "=== Rate-limited historical mining run finished successfully ==="
    printf "\nAll steps completed successfully. Detailed output in %s\n" "${LOG_FILE}"
}

main "$@"
