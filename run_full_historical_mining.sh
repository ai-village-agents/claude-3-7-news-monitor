#!/usr/bin/env bash

# Run the full historical mining pipeline, publish results, and push changes.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs/historical_runs"
mkdir -p "${LOG_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/full_historical_mining_${TIMESTAMP}.log"
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

PAGE_RANGES="20-40,40-60,60-80,80-100,100-120,120-140"

mine_year() {
    local year="$1"
    local output_file="${LOG_DIR}/federal_register_results_${year}.txt"
    local date_range="${year}-01-01,${year}-12-31"

    python3 "${PROJECT_ROOT}/historical_register_miner.py" \
        --num-threads 8 \
        --page-ranges "${PAGE_RANGES}" \
        --date-range "${date_range}" \
        --output-file "${output_file}"
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

    local commit_message="Historical mining run ${TIMESTAMP}"
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
    log "=== Full historical mining run started ==="
    printf "Log file: %s\n\n" "${LOG_FILE}"

    local years=(2020 2021 2022 2023)
    local total_steps=$(( ${#years[@]} + 2 ))
    local step_counter=1

    for year in "${years[@]}"; do
        run_step "${step_counter}" "${total_steps}" "Mine Federal Register data for ${year}" \
            mine_year "${year}"
        ((step_counter++))
    done

    run_step "${step_counter}" "${total_steps}" "Publish up to 100 historical stories" \
        publish_batch
    ((step_counter++))

    run_step "${step_counter}" "${total_steps}" "Commit and push mining updates" \
        git_push_changes

    CURRENT_STEP="completed"
    log "=== Full historical mining run finished successfully ==="
    printf "\nAll steps completed successfully. Detailed output in %s\n" "${LOG_FILE}"
}

main "$@"
