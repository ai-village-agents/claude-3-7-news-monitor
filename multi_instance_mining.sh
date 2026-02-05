#!/usr/bin/env bash

set -euo pipefail
IFS=$'\n\t'

# Determine project root from script location
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run metadata
RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_ROOT="${PROJECT_ROOT}/logs/multi_instance_runs"
RUN_LOG_DIR="${LOG_ROOT}/${RUN_ID}"
mkdir -p "${RUN_LOG_DIR}"

STATUS_FILE="${RUN_LOG_DIR}/run_status.log"
touch "${STATUS_FILE}"

YEARS=(2020 2021 2022 2023 2024 2025)

# Distinct page ranges per year to split coverage
declare -A PAGE_RANGES=(
    [2020]="10-30,30-50,50-70,70-90,90-110,110-130"
    [2021]="130-150,150-170,170-190,190-210,210-230,230-250"
    [2022]="250-270,270-290,290-310,310-330,330-350,350-370"
    [2023]="370-390,390-410,410-430,430-450,450-470,470-490"
    [2024]="490-510,510-530,530-550,550-570,570-590,590-610"
    [2025]="610-630,630-650,650-670,670-690,690-710,710-730"
)

THREADS_PER_JOB=4
MAX_RETRIES=7
BASE_DELAY=3.0
MAX_DELAY=120.0
LAUNCH_BACKOFF_SECONDS=2

declare -a PIDS=()
declare -A YEAR_BY_PID=()
declare -A YEAR_STATUS=()
declare -A YEAR_LOG=()
declare -A YEAR_OUTPUT=()

log() {
    local message="$1"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "${timestamp} | ${message}" | tee -a "${STATUS_FILE}"
}

handle_signal() {
    local signal="$1"
    log "Received signal ${signal}. Terminating active mining jobs..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
        fi
    done
    log "Shutdown complete due to signal ${signal}."
    exit 1
}

cleanup_on_exit() {
    local exit_code=$?
    if [[ ${exit_code} -ne 0 ]]; then
        log "Script exiting with code ${exit_code}. Attempting to clean up background processes."
        for pid in "${PIDS[@]}"; do
            if kill -0 "${pid}" 2>/dev/null; then
                kill "${pid}" 2>/dev/null || true
            fi
        done
    fi
}

trap 'cleanup_on_exit' EXIT
trap 'handle_signal INT' INT
trap 'handle_signal TERM' TERM

start_mining_job() {
    local year="$1"
    local page_ranges="${PAGE_RANGES[${year}]:-}"

    if [[ -z "${page_ranges}" ]]; then
        log "No page ranges configured for year ${year}; skipping."
        YEAR_STATUS["${year}"]="skipped (no page ranges)"
        return
    fi

    local log_file="${RUN_LOG_DIR}/rate_limited_${year}.log"
    local output_file="${RUN_LOG_DIR}/federal_register_results_${year}.txt"

    YEAR_LOG["${year}"]="${log_file}"
    YEAR_OUTPUT["${year}"]="${output_file}"

    {
        echo "============================================================"
        echo "Run ID: ${RUN_ID}"
        echo "Year: ${year}"
        echo "Log file: ${log_file}"
        echo "Output file: ${output_file}"
        echo "Page ranges: ${page_ranges}"
        echo "Started at: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "============================================================"
    } >>"${log_file}"

    local date_range="${year}-01-01,${year}-12-31"

    log "Launching mining job for ${year} (see ${log_file})."

    (
        cd "${PROJECT_ROOT}"
        nice -n 5 python3 "${PROJECT_ROOT}/rate_limited_register_miner.py" \
            --num-threads "${THREADS_PER_JOB}" \
            --page-ranges "${page_ranges}" \
            --date-range "${date_range}" \
            --output-file "${output_file}" \
            --max-retries "${MAX_RETRIES}" \
            --base-delay "${BASE_DELAY}" \
            --max-delay "${MAX_DELAY}"
    ) >>"${log_file}" 2>&1 &

    local pid=$!
    PIDS+=("${pid}")
    YEAR_BY_PID["${pid}"]="${year}"

    log "Started mining process for ${year} with PID ${pid}."
}

log "Starting multi-instance mining run ${RUN_ID}."
log "Logs will be stored in ${RUN_LOG_DIR}."

for year in "${YEARS[@]}"; do
    start_mining_job "${year}"
    sleep "${LAUNCH_BACKOFF_SECONDS}"
done

log "All mining jobs launched. Monitoring progress..."

all_success=true
for pid in "${PIDS[@]}"; do
    year="${YEAR_BY_PID[${pid}]}"
    if wait "${pid}"; then
        YEAR_STATUS["${year}"]="success"
        log "Mining completed successfully for ${year} (PID ${pid})."
    else
        exit_code=$?
        YEAR_STATUS["${year}"]="failed (exit code ${exit_code})"
        all_success=false
        log "Mining failed for ${year} (PID ${pid}, exit code ${exit_code})."
    fi
done

{
    echo "Run summary for ${RUN_ID}"
    echo "----------------------------------------"
    for year in "${YEARS[@]}"; do
        status="${YEAR_STATUS[${year}]:-not started}"
        echo "Year ${year}: ${status}"
        if [[ -n "${YEAR_LOG[${year}]:-}" ]]; then
            echo "  Log: ${YEAR_LOG[${year}]}"
        fi
        if [[ -n "${YEAR_OUTPUT[${year}]:-}" ]]; then
            echo "  Output: ${YEAR_OUTPUT[${year}]}"
        fi
    done
} | tee -a "${STATUS_FILE}" >"${RUN_LOG_DIR}/summary.txt"

if [[ "${all_success}" == true ]]; then
    log "All mining jobs completed successfully."
else
    log "At least one mining job failed. Review logs before publishing."
fi

PUBLISH_LOG="${RUN_LOG_DIR}/publishing.log"
{
    echo "============================================================"
    echo "Unified publishing phase for run ${RUN_ID}"
    echo "Started at: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"
} >>"${PUBLISH_LOG}"

if [[ "${all_success}" == true ]]; then
    log "Starting unified publishing phase (systematic_batch_publisher.py)."
else
    log "Proceeding with publishing despite failures to ensure pipeline continuity."
fi

if (
    cd "${PROJECT_ROOT}"
    nice -n 5 python3 "${PROJECT_ROOT}/systematic_batch_publisher.py" --batch-size 50
) >>"${PUBLISH_LOG}" 2>&1; then
    log "Publishing phase completed successfully. Details logged to ${PUBLISH_LOG}."
    echo "Publishing completed at $(date '+%Y-%m-%d %H:%M:%S')" >>"${PUBLISH_LOG}"
else
    publish_exit=$?
    log "Publishing phase failed with exit code ${publish_exit}. See ${PUBLISH_LOG}."
    echo "Publishing failed at $(date '+%Y-%m-%d %H:%M:%S') with exit code ${publish_exit}" >>"${PUBLISH_LOG}"
fi

log "Preparing git commit for mining run ${RUN_ID}."

(
    cd "${PROJECT_ROOT}"
    git add -A
    if git diff --cached --quiet; then
        log "No changes detected; skipping git commit and push."
    else
        git commit -m "Multi-instance register mining run ${RUN_ID}"
        git push
        log "Git commit and push completed for run ${RUN_ID}."
    fi
)

log "Run ${RUN_ID} complete. Summary available at ${RUN_LOG_DIR}/summary.txt."
