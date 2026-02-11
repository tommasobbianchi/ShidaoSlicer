#!/bin/bash
set -e

# Configuration — uses SSH key auth via ~/.ssh/config
REMOTE_HOST="behemoth"
REMOTE_DIR="/home/user/projects/ORCA_BELT"
LOCAL_DIR="/home/user/projects/ORCA_BELT/"

echo "========================================"
echo "SYNCING TO BEHEMOTH..."
echo "========================================"

# Sync source code to Behemoth
# Excluding build/ and other heavy/local artifacts
rsync -avz --delete \
    --exclude 'build' \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    "$LOCAL_DIR" "${REMOTE_HOST}:${REMOTE_DIR}"

echo "========================================"
echo "TRIGGERING BUILD ON BEHEMOTH..."
echo "========================================"

# Run the build script on Behemoth
ssh "$REMOTE_HOST" \
    "cd ${REMOTE_DIR} && export CMAKE_BUILD_PARALLEL_LEVEL=12 && ./build_linux.sh -s -r"

echo "========================================"
echo "BUILD COMPLETE"
echo "========================================"
