#!/bin/bash
# Script to set custom resolution in XRDP session
# Usage: ./set_resolution.sh [width] [height]

WIDTH=${1:-1920}
HEIGHT=${2:-1080}

echo "Setting resolution to ${WIDTH}x${HEIGHT}..."

# 1. Generate modeline
CVT_OUT=$(cvt $WIDTH $HEIGHT)
RAW_PARAMS=$(echo "$CVT_OUT" | grep "Modeline" | sed 's/^Modeline //')
CLEAN_PARAMS=$(echo "$RAW_PARAMS" | tr -d '"')
MODENAME=$(echo "$CLEAN_PARAMS" | awk '{print $1}')

OUTPUT=$(xrandr | grep " connected" | awk '{print $1}' | head -n 1)

echo "Detected output: $OUTPUT"
echo "Mode Name: $MODENAME"

# 2. Add mode if missing (ignoring errors)
xrandr --newmode $CLEAN_PARAMS 2>/dev/null
xrandr --addmode $OUTPUT $MODENAME 2>/dev/null

# 3. Apply using legacy -s command
# This is often more reliable than --output --mode for framebuffer resizing
echo "Applying mode using legacy xrandr -s..."
xrandr -s ${WIDTH}x${HEIGHT}

if [ $? -eq 0 ]; then
    echo "Success!"
else
    echo "Failed to set resolution inside the session."
    echo "Please try changing the resolution settings in your RDP Client (Remmina/Windows Remote Desktop) and reconnecting."
fi
