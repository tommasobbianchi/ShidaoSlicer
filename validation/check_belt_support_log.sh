#!/bin/bash
# Quick script to extract belt support diagnostics from OrcaSlicer log.
# Usage: ./check_belt_support_log.sh [log_file]

LOG="${1:-$(ls -t ~/.config/OrcaSlicer/log/debug_*.log.0 2>/dev/null | head -1)}"

if [ -z "$LOG" ] || [ ! -f "$LOG" ]; then
    echo "No log file found. Usage: $0 [path/to/debug.log.0]"
    exit 1
fi

echo "=== Belt Support Diagnostics ==="
echo "Log: $LOG"
echo "Modified: $(stat -c %Y "$LOG" | xargs -I{} date -d @{} '+%Y-%m-%d %H:%M:%S')"
echo ""

strings "$LOG" | grep -E "Belt support:" | while IFS= read -r line; do
    echo "  $line"
done

echo ""
echo "=== Support Generator Belt Info ==="
strings "$LOG" | grep -E "Support generator.*BELT" | while IFS= read -r line; do
    echo "  $line"
done
