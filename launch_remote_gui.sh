#!/bin/bash
# Wrapper to launch OrcaSlicer safely in Remote Desktop (xRDP) environments.
# Forces software rendering to avoid OpenGL crashes with llvmpipe/XRDP.

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BINARY="$PROJECT_DIR/build/src/Release/orca-slicer"

echo "--- Launching OrcaSlicer in Remote Mode ---"
echo "Setting LIBGL_ALWAYS_SOFTWARE=1"
export LIBGL_ALWAYS_SOFTWARE=1

# Force llvmpipe explicitly to avoid autodetection of hardware
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export GALLIUM_DRIVER=llvmpipe
export EGL_PLATFORM=x11

# Debugging info
echo "--- Environment Check ---"
id
ls -l /dev/dri/card0 2>/dev/null || echo "No /dev/dri/card0 access"
echo "-----------------------"

# Link resources if needed
if [ ! -L "$PROJECT_DIR/build/src/Release/resources" ]; then
    echo "Linking resources..."
    ln -s "$PROJECT_DIR/resources" "$PROJECT_DIR/build/src/Release/resources"
fi

if [ -f "$BINARY" ]; then
    "$BINARY" "$@" > "$PROJECT_DIR/launch.log" 2>&1
else
    echo "Error: Binary not found at $BINARY"
    exit 1
fi
