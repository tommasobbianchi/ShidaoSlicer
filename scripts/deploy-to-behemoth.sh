#!/bin/bash
# deploy-to-behemoth.sh — sync OrcaBelt binary + resources to behemoth for local execution
#
# Usage:
#   ./scripts/deploy-to-behemoth.sh           # sync binary + resources
#   ./scripts/deploy-to-behemoth.sh --binary  # binary only (quick after rebuild)
#   ./scripts/deploy-to-behemoth.sh --resources # resources only
#
# Architecture:
#   nativedev (<DEV_HOST>) — build server, git repo lives here
#   behemoth  (<WORKSTATION_HOST>)  — runs binary locally (GPU, display, fast disk)
#   Binary: build/src/Debug/orca-slicer (Release has linker error → 0 bytes)

set -e

BEHEMOTH="<WORKSTATION_HOST>"
REMOTE_DIR="/home/user/orca-belt-local"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BINARY="$REPO_ROOT/build/src/Debug/orca-slicer"
RESOURCES="$REPO_ROOT/resources"

SYNC_BINARY=1
SYNC_RESOURCES=1

for arg in "$@"; do
    case "$arg" in
        --binary)    SYNC_RESOURCES=0 ;;
        --resources) SYNC_BINARY=0 ;;
    esac
done

# Layout on behemoth:
#   $REMOTE_DIR/bin/orca-slicer   <- binary (OrcaSlicer resolves resources via parent_path().parent_path())
#   $REMOTE_DIR/resources/        <- found automatically as $REMOTE_DIR/resources/

# Ensure remote dirs exist
ssh "$BEHEMOTH" "mkdir -p $REMOTE_DIR/bin $REMOTE_DIR/resources"

if [ "$SYNC_BINARY" = "1" ]; then
    if [ ! -f "$BINARY" ]; then
        echo "ERROR: binary not found at $BINARY — run a build first" >&2
        exit 1
    fi
    echo "==> Syncing binary ($(du -sh "$BINARY" | cut -f1))…"
    rsync -ah --progress --checksum "$BINARY" "$BEHEMOTH:$REMOTE_DIR/bin/orca-slicer"
    echo "    binary deployed"
fi

if [ "$SYNC_RESOURCES" = "1" ]; then
    echo "==> Syncing resources ($(du -sh "$RESOURCES" | cut -f1))…"
    rsync -ah --progress --delete \
        --exclude='*.pyc' --exclude='__pycache__' \
        "$RESOURCES/" "$BEHEMOTH:$REMOTE_DIR/resources/"
    echo "    resources deployed"
fi

echo ""
echo "Deploy complete → $BEHEMOTH:$REMOTE_DIR"
echo "Launch with:  ssh $BEHEMOTH orca-belt [model.3mf]"
