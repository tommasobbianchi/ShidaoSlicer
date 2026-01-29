#!/usr/bin/env bash
set -euo pipefail

# Configuration
[ -f .config.env ] && source .config.env

UNIT_PREFIX="orcabelt-build"
BUILD_DIR="${BUILD_DIR:-build}"
LOG_DIR="logs"
STATE_FILE="build_state.json"
LATEST_LOG="${LOG_DIR}/latest.log"

# Resource Limits
CPU_QUOTA="50%"
MEMORY_LIMIT="4G"

# Scripts
NOTIFY_SCRIPT="./telegram_notify.sh"

mkdir -p "${LOG_DIR}"

# Function to update JSON state
update_state() {
    local status=$1
    local exit_code=${2:-null}
    local log_path=${3:-$(readlink -f "${LATEST_LOG}" || echo "null")}
    local job_id=${4:-$(jq -r '.job_id // ""' "${STATE_FILE}" 2>/dev/null || echo "null")}
    
    local NOW=$(date +%Y-%m-%dT%H:%M:%S)
    local START_TIME=$(jq -r '.start_time // "'${NOW}'"' "${STATE_FILE}" 2>/dev/null || echo "${NOW}")

    jq -n \
        --arg job_id "${job_id}" \
        --arg hostname "$(hostname)" \
        --arg start_time "${START_TIME}" \
        --arg last_update_time "${NOW}" \
        --arg status "${status}" \
        --argjson exit_code "${exit_code}" \
        --arg log_file_path "${log_path}" \
        '{job_id: $job_id, hostname: $hostname, start_time: $start_time, last_update_time: $last_update_time, status: $status, exit_code: $exit_code, log_file_path: $log_file_path}' \
        > "${STATE_FILE}.tmp" && mv "${STATE_FILE}.tmp" "${STATE_FILE}"
}

COMMAND="${1:-status}"
shift || true

case "${COMMAND}" in
  build)
    # Check if a build is already running via systemd
    if systemctl --user is-active --quiet "${UNIT_PREFIX}-*"; then
        echo "A build is already running."
        exit 0
    fi

    JOB_ID="${UNIT_PREFIX}-$(date +%s)"
    LOG_FILE="${LOG_DIR}/build_$(date +%Y%m%d_%H%M%S).log"
    touch "${LOG_FILE}"
    ln -sf "$(basename "${LOG_FILE}")" "${LATEST_LOG}"

    # Prepare command
    if [ $# -gt 0 ]; then
        BUILD_COMMAND="./build_linux.sh $*"
    else
        BUILD_COMMAND="./build_linux.sh -s -r"
    fi

    # Initial State
    ABS_STATE_FILE="$(readlink -f "${STATE_FILE}")"
    ABS_NOTIFY_SCRIPT="$(readlink -f "${NOTIFY_SCRIPT}")"
    update_state "starting" null "$(readlink -f "${LOG_FILE}")" "${JOB_ID}"
    
    # Notify Start
    "${ABS_NOTIFY_SCRIPT}" start "ORCA_BELT" "${JOB_ID}" || true

    echo "Launching async build via systemd-run..."
    
    # Run via systemd-run
    # We pass the absolute paths and current directory to the unit
    systemd-run --user --unit="${JOB_ID}" \
        --description="Orca Belt Async Build" \
        --property=WorkingDirectory="$(pwd)" \
        --property=CPUQuota="${CPU_QUOTA}" \
        --property=MemoryLimit="${MEMORY_LIMIT}" \
        --setenv=TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}" \
        --setenv=TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}" \
        --setenv=CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-1}" \
        /usr/bin/bash -c "
            set -o pipefail
            
            # Use absolute paths in the unit environment
            echo \"Starting build: ${BUILD_COMMAND}\" >> \"${LOG_FILE}\"
            
            ${BUILD_COMMAND} >> \"${LOG_FILE}\" 2>&1
            EXIT_CODE=\$?
            
            STATUS=\"success\"
            [[ \$EXIT_CODE -ne 0 ]] && STATUS=\"failure\"
            
            # Update state file
            NOW=\$(date +%Y-%m-%dT%H:%M:%S)
            /usr/bin/jq --arg status \"\$STATUS\" --argjson exit \"\$EXIT_CODE\" --arg now \"\$NOW\" \
               '.status = \$status | .exit_code = \$exit | .last_update_time = \$now' \
               \"${ABS_STATE_FILE}\" > \"${ABS_STATE_FILE}.tmp\" && mv \"${ABS_STATE_FILE}.tmp\" \"${ABS_STATE_FILE}\"
            
            # Notify Finish
            \"${ABS_NOTIFY_SCRIPT}\" finish \"ORCA_BELT\" \"\$STATUS\" \"${LOG_FILE}\" \"\$EXIT_CODE\" || true
        "

    update_state "running" null "$(readlink -f "${LOG_FILE}")" "${JOB_ID}"
    
    echo "Async build started: ${JOB_ID}"
    echo "Log file: ${LOG_FILE}"
    ;;

  status)
    if [[ -f "${STATE_FILE}" ]]; then
        jq . "${STATE_FILE}"
        
        # Cross-check with systemd
        JOB_ID=$(jq -r '.job_id' "${STATE_FILE}")
        if [[ "${JOB_ID}" != "null" ]]; then
            echo "--- Systemd Info ---"
            systemctl --user status "${JOB_ID}" --no-pager || true
        fi
    else
        echo "No build state found."
    fi
    ;;

  logs)
    LATEST=$(readlink -f "${LATEST_LOG}" 2>/dev/null || true)
    if [[ -n "${LATEST}" && -f "${LATEST}" ]]; then
        tail -f "${LATEST}"
    else
        echo "No log files found."
    fi
    ;;

  stop)
    if [[ -f "${STATE_FILE}" ]]; then
        JOB_ID=$(jq -r '.job_id' "${STATE_FILE}")
        if [[ "${JOB_ID}" != "null" ]]; then
            systemctl --user stop "${JOB_ID}"
            update_state "stopped" 130
            echo "Build ${JOB_ID} stopped."
        else
            echo "No active job ID in state file."
        fi
    else
        echo "No build state found."
    fi
    ;;

  *)
    echo "Usage: $0 {build|status|logs|stop} [extra_args...]"
    exit 1
    ;;
esac
