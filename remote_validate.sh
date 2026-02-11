#!/bin/bash
set -e

# Configuration
REMOTE_HOST="<WORKSTATION_HOST>"
REMOTE_USER="tommaso"
REMOTE_PASS="${BEHEMOTH_PASS:?Set BEHEMOTH_PASS env var — see ~/.secrets/credentials.yaml}"
REMOTE_DIR="/home/user/projects/ORCA_BELT"

echo "========================================"
echo "RUNNING VALIDATION ON BEHEMOTH..."
echo "========================================"

# Sync scripts AND config file
sshpass -p "$REMOTE_PASS" rsync -avz \
    scripts/ \
    "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/scripts/"

sshpass -p "$REMOTE_PASS" rsync -avz \
    belt_transform.ini \
    "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

# Run validation loop
sshpass -p "$REMOTE_PASS" ssh "${REMOTE_USER}@${REMOTE_HOST}" \
    "cd ${REMOTE_DIR} && ./scripts/belt_validation_loop.sh"
