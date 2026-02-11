#!/bin/bash
# Script per avviare OrcaSlicer in locale (con accelerazione hardware)

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BINARY="$PROJECT_DIR/build/src/Release/orca-slicer"

# 1. Verifica e collega la cartella resources (fondamentale per evitare crash)
if [ ! -L "$PROJECT_DIR/build/src/Release/resources" ]; then
    echo "🔗 Linking resources..."
    ln -s "$PROJECT_DIR/resources" "$PROJECT_DIR/build/src/Release/resources"
fi

# 2. Imposta l'ambiente per GTK/GLib (LC_ALL=C) e GSettings
export LC_ALL=C
export GSETTINGS_SCHEMA_DIR=/usr/share/glib-2.0/schemas/
# Suppress harmless wxWidgets assertions and force X11
export WXSUPPRESS_SIZER_FLAGS_CHECK=1
export GDK_BACKEND=x11

# Compatibility Fixes
export WXSUPPRESS_SIZER_FLAGS_CHECK=1
export GDK_BACKEND=x11
export UBUNTU_MENUPROXY=0
export GTK_OVERLAY_SCROLLING=0
export WEBKIT_DISABLE_DMABUF_RENDERER=1

# Disable Zink/Mesa overrides to allow native NVIDIA GLX
# export MESA_LOADER_DRIVER_OVERRIDE=zink
# export GALLIUM_DRIVER=zink
# export __GLX_VENDOR_LIBRARY_NAME=mesa

# 3. Avvia l'eseguibile
if [ -f "$BINARY" ]; then
    echo "🚀 Starting OrcaSlicer GUI (LC_ALL=C)..."
    "$BINARY" "$@"
else
    echo "❌ Binary not found at $BINARY"
    echo "   Did you run remote_build.sh?"
    exit 1
fi
