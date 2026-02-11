#!/bin/bash
set -e

# Configuration
REMOTE_HOST="<WORKSTATION_HOST>"
REMOTE_USER="tommaso"
REMOTE_PASS="${BEHEMOTH_PASS:?Set BEHEMOTH_PASS env var — see ~/.secrets/credentials.yaml}"
REMOTE_DIR="/home/user/projects/ORCA_BELT"
LOCAL_DIR="/home/user/projects/ORCA_BELT/"

echo "========================================"
echo "SYNCING TO BEHEMOTH ($REMOTE_HOST)..."
echo "========================================"

# Sync source code to Behemoth
# Excluding build/ and other heavy/local artifacts
sshpass -p "$REMOTE_PASS" rsync -avz --delete \
    --exclude 'build' \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    "$LOCAL_DIR" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"

echo "========================================"
echo "TRIGGERING BUILD ON BEHEMOTH..."
echo "========================================"

# Run the build script on Behemoth
# Assuming build_linux.sh exists there (synced or pre-existing)
sshpass -p "$REMOTE_PASS" ssh "${REMOTE_USER}@${REMOTE_HOST}" \
    "cd ${REMOTE_DIR} && export CMAKE_BUILD_PARALLEL_LEVEL=12 && ./build_linux.sh -s -r"

echo "========================================"
echo "BUILD COMPLETE"
echo "========================================"
