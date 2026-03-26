#!/bin/bash
# Launch OrcaSlicer GUI via xrdp (software rendering)
# Connect via Remmina RDP to nativedev (<DEV_HOST>)

# Kill existing instances
pkill -f "orca-slicer" 2>/dev/null
sleep 1

export DISPLAY=:10
export LIBGL_ALWAYS_SOFTWARE=1
export MESA_GL_VERSION_OVERRIDE=3.3
export EGL_PLATFORM=x11
export GALLIUM_DRIVER=llvmpipe

exec /home/user/projects/ORCA_BELT/build/src/Release/orca-slicer "$@"
