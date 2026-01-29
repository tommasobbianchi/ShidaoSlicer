#!/bin/bash
# Wrapper to DEBUG OrcaSlicer in Remote Desktop (xRDP) environments.

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BINARY="$PROJECT_DIR/build/src/Release/orca-slicer"

echo "--- Debugging OrcaSlicer (Software Render) ---"

# Force llvmpipe
export LIBGL_ALWAYS_SOFTWARE=1
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export GALLIUM_DRIVER=llvmpipe
export EGL_PLATFORM=x11

# Run with GDB
# - ex run: starts program
# - ex "bt full": prints backtrace if crash
# - ex quit: exits gdb
gdb -ex run -ex "bt full" -ex quit --args "$BINARY" "$@"
