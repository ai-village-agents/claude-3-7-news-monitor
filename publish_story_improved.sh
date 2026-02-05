#!/usr/bin/env bash

# Improved script to publish a story into docs/DATE/SLUG.html
set -euo pipefail

SCRIPT_NAME=${0##*/}

log() {
    local level="$1"; shift
    printf '%s [%s] %s\n' "$(date +'%Y-%m-%d %H:%M:%S')" "$level" "$*" >&2
}

error_handler() {
    local exit_code=$1
    local line_no=$2
    log "ERROR" "${SCRIPT_NAME} failed with exit code ${exit_code} at line ${line_no}"
}
trap 'error_handler $? $LINENO' ERR

usage() {
    cat <<EOF
Usage: ${SCRIPT_NAME} <title> <summary> <url>

Publishes a story as docs/YYYYMMDD/<slug>.html
EOF
}

if [[ $# -lt 3 ]]; then
    usage
    exit 1
fi

TITLE="$1"
SUMMARY="$2"
URL="$3"

if [[ -z "$TITLE" ]]; then
    log "ERROR" "Title cannot be empty."
    exit 1
fi

if [[ -z "$SUMMARY" ]]; then
    log "ERROR" "Summary cannot be empty."
    exit 1
fi

if [[ -z "$URL" ]]; then
    log "ERROR" "URL cannot be empty."
    exit 1
fi

if [[ ! "$URL" =~ ^https?:// ]]; then
    log "ERROR" "URL must start with http:// or https://"
    exit 1
fi

generate_slug() {
    local title="$1"
    local raw_slug truncated_slug
    raw_slug=$(echo "$title" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')
    if [[ -z "$raw_slug" ]]; then
        raw_slug="story"
    fi
    if (( ${#raw_slug} > 150 )); then
        truncated_slug=${raw_slug:0:150}
        truncated_slug=$(echo "$truncated_slug" | sed 's/-$//')
        if [[ -z "$truncated_slug" ]]; then
            truncated_slug="story"
        fi
        echo "$truncated_slug"
    else
        echo "$raw_slug"
    fi
}

SLUG=$(generate_slug "$TITLE")

DATE=$(date +%Y%m%d)
OUTDIR="docs/${DATE}"

log "INFO" "Creating output directory at ${OUTDIR}"
mkdir -p "$OUTDIR"

HTML_FILE="${OUTDIR}/${SLUG}.html"

log "INFO" "Writing story to ${HTML_FILE}"
cat > "$HTML_FILE" <<HTML
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${TITLE}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #333; }
        .metadata { color: #666; font-size: 0.9em; }
        .summary { margin-top: 20px; line-height: 1.5; }
        .source { margin-top: 20px; }
    </style>
</head>
<body>
    <h1>${TITLE}</h1>
    <div class="metadata">Published: $(date '+%Y-%m-%d %H:%M:%S')</div>
    <div class="summary">${SUMMARY}</div>
    <div class="source">Source: <a href="${URL}" target="_blank" rel="noopener noreferrer">${URL}</a></div>
</body>
</html>
HTML

log "INFO" "Story published: ${HTML_FILE}"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    log "INFO" "Adding ${HTML_FILE} to git index"
    git add "$HTML_FILE"
    log "INFO" "Creating git commit"
    git commit -m "Add story: ${TITLE}"
else
    log "INFO" "Not inside a git repository; skipping git add/commit"
fi
