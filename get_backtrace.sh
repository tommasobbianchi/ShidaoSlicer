#!/bin/bash
export LIBGL_ALWAYS_SOFTWARE=1
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export GALLIUM_DRIVER=llvmpipe
export EGL_PLATFORM=x11
export G_DEBUG=fatal-criticals

# Run gdb
gdb -batch -ex "run" -ex "bt" --args ./build/src/Release/orca-slicer
