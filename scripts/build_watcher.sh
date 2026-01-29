#!/usr/bin/env bash
# Build watcher that creates dispatch file for Antigravity feedback loop
set -euo pipefail

DISPATCH_DIR="${HOME}/.gemini/antigravity/dispatch"
DISPATCH_FILE="${DISPATCH_DIR}/build_error_dispatch.json"
STATE_FILE="build_state.json"
LOG_DIR="logs"

mkdir -p "${DISPATCH_DIR}"

echo "🔄 Watching build status for errors..."

while true; do
    if [[ -f "${STATE_FILE}" ]]; then
        STATUS=$(jq -r '.status // "unknown"' "${STATE_FILE}")
        EXIT_CODE=$(jq -r '.exit_code // "null"' "${STATE_FILE}")
        LOG_FILE=$(jq -r '.log_file_path // ""' "${STATE_FILE}")
        JOB_ID=$(jq -r '.job_id // ""' "${STATE_FILE}")
        
        if [[ "${STATUS}" == "failure" || "${STATUS}" == "error" ]]; then
            echo "❌ Build FAILED! Creating dispatch..."
            
            # Extract last errors from log
            LAST_ERRORS=""
            if [[ -f "${LOG_FILE}" ]]; then
                LAST_ERRORS=$(grep -iE "error:|FAILED:" "${LOG_FILE}" | tail -20 | sed 's/"/\\"/g' | tr '\n' '|')
            fi
            
            # Create dispatch file for Antigravity
            cat > "${DISPATCH_FILE}" <<EOF
{
    "type": "BUILD_ERROR",
    "priority": "HIGH",
    "timestamp": "$(date -Iseconds)",
    "job_id": "${JOB_ID}",
    "exit_code": ${EXIT_CODE:-1},
    "log_file": "${LOG_FILE}",
    "errors_summary": "${LAST_ERRORS}",
    "action_required": "Analyze errors and fix compilation issues",
    "project": "ORCA_BELT"
}
EOF
            echo "📤 Dispatch created: ${DISPATCH_FILE}"
            
            # Send Telegram notification about dispatch
            source .config.env 2>/dev/null || true
            ./telegram_notify.sh finish "ORCA_BELT" "FAILURE" "${LOG_FILE}" "${EXIT_CODE}" || true
            
            exit 1
            
        elif [[ "${STATUS}" == "success" ]]; then
            echo "✅ Build SUCCESS!"
            
            # Create success dispatch
            cat > "${DISPATCH_FILE}" <<EOF
{
    "type": "BUILD_SUCCESS",
    "priority": "LOW",
    "timestamp": "$(date -Iseconds)",
    "job_id": "${JOB_ID}",
    "exit_code": 0,
    "action_required": "Proceed with testing",
    "project": "ORCA_BELT"
}
EOF
            exit 0
        fi
    fi
    
    sleep 10
done
