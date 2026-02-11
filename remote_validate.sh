#!/bin/bash
set -e

# Configuration — uses SSH key auth via ~/.ssh/config
REMOTE_HOST="behemoth"
REMOTE_DIR="/home/user/projects/ORCA_BELT"

echo "========================================"
echo "RUNNING VALIDATION ON BEHEMOTH..."
echo "========================================"

# Sync scripts AND config file
rsync -avz \
    scripts/ \
    "${REMOTE_HOST}:${REMOTE_DIR}/scripts/"

rsync -avz \
    belt_transform.ini \
    "${REMOTE_HOST}:${REMOTE_DIR}/"

# Run validation loop
ssh "$REMOTE_HOST" \
    "cd ${REMOTE_DIR} && ./scripts/belt_validation_loop.sh"
