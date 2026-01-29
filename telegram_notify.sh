#!/usr/bin/env bash
set -euo pipefail

# Configuration - should be set via environment variables
TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-}"

if [[ -z "${TOKEN}" || -z "${CHAT_ID}" ]]; then
    echo "Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Notifications disabled." >&2
    exit 0
fi

SEND_MESSAGE() {
    local message="$1"
    curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "text=${message}" \
        -d "parse_mode=Markdown" > /dev/null
}

EVENT="$1"
shift

case "${EVENT}" in
    start)
        PROJECT="${1:-Unknown Project}"
        JOB_ID="${2:-N/A}"
        MSG="🚀 *Build Started*\nProject: \`${PROJECT}\`\nJob ID: \`${JOB_ID}\`\nHost: \`$(hostname)\`"
        SEND_MESSAGE "${MSG}"
        ;;
    finish)
        PROJECT="${1:-Unknown Project}"
        STATUS="${2:-UNKNOWN}"
        LOG_FILE="${3:-}"
        EXIT_CODE="${4:-0}"
        
        EMOJI="✅"
        [[ "${STATUS}" != "SUCCESS" ]] && EMOJI="❌"
        
        MSG="${EMOJI} *Build Finished*\nProject: \`${PROJECT}\`\nStatus: *${STATUS}*\nExit Code: \`${EXIT_CODE}\`"
        
        if [[ -f "${LOG_FILE}" && "${STATUS}" != "SUCCESS" ]]; then
            TAIL=$(tail -n 20 "${LOG_FILE}")
            MSG="${MSG}\n\n*Last Log Lines*:\n\`\`\`\n${TAIL}\n\`\`\`"
        fi
        
        SEND_MESSAGE "${MSG}"
        ;;
    test)
        SEND_MESSAGE "🔔 *Telegram Notification Test*\nIf you see this, connectivity is working!"
        ;;
    *)
        echo "Usage: $0 {start|finish|test} [args...]"
        exit 1
        ;;
esac
