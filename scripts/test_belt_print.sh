#!/bin/bash
# Automated Belt Printer Test Workflow
# Usage: ./test_belt_print.sh [config_tweaks]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
PRINTER_IP="${PRINTER_IP:-}"  # Set via environment or edit here
MODEL="${1:-tests/fixtures/belt_test_cube.stl}"
OUTPUT="/tmp/belt_test_$(date +%s).3mf"
GCODE_NAME="belt_test_$(date +%H%M%S).gcode"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Automated Belt Printer Test Workflow${NC}\n"

# Check printer IP
if [ -z "$PRINTER_IP" ]; then
    echo -e "${RED}❌ PRINTER_IP not set!${NC}"
    echo "   Set via: export PRINTER_IP=100.x.x.x"
    echo "   Or edit this script"
    exit 1
fi

echo "📋 Configuration:"
echo "   Model: $MODEL"
echo "   Printer: $PRINTER_IP"
echo "   Output: $OUTPUT"
echo ""

# Step 1: Generate G-code
echo -e "${YELLOW}[1/5]${NC} Generating G-code with OrcaSlicer..."
cd "$PROJECT_ROOT"

./build/src/Release/orca-slicer "$MODEL" \
    --load-settings "tests/fixtures/belt_machine.json;tests/fixtures/belt_process_petg_safe.json" \
    --load-filaments "tests/fixtures/belt_filament_petg.json" \
    --slice 1 \
    --export-3mf "$OUTPUT"

if [ ! -f "$OUTPUT" ]; then
    echo -e "${RED}❌ G-code generation failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ G-code generated${NC}\n"

# Step 2: Extract G-code from 3MF
echo -e "${YELLOW}[2/5]${NC} Extracting G-code..."
GCODE_FILE="/tmp/${GCODE_NAME}"
unzip -p "$OUTPUT" Metadata/plate_1.gcode > "$GCODE_FILE"

echo "   G-code: $GCODE_FILE"
echo "   Lines: $(wc -l < "$GCODE_FILE")"
echo ""

# Step 3: Upload to printer
echo -e "${YELLOW}[3/5]${NC} Uploading to printer..."
python3 "$SCRIPT_DIR/klipper_remote.py" \
    --ip "$PRINTER_IP" \
    upload "$GCODE_FILE" --name "$GCODE_NAME"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Upload failed!${NC}"
    exit 1
fi

echo ""

# Step 4: Ask confirmation
echo -e "${YELLOW}[4/5]${NC} Ready to start print"
echo "   File uploaded: $GCODE_NAME"
read -p "   Start print now? [y/N] " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}ℹ️  Print not started (manual start required)${NC}"
    echo "   To start later:"
    echo "   python3 scripts/klipper_remote.py --ip $PRINTER_IP start $GCODE_NAME"
    exit 0
fi

# Step 5: Start print and monitor
echo -e "${YELLOW}[5/5]${NC} Starting print..."
python3 "$SCRIPT_DIR/klipper_remote.py" \
    --ip "$PRINTER_IP" \
    start "$GCODE_NAME"

echo ""
echo -e "${GREEN}✅ Print started!${NC}"
echo ""
echo "Starting live monitor in 3 seconds..."
echo "(Press Ctrl+C to stop monitoring, print will continue)"
sleep 3

python3 "$SCRIPT_DIR/klipper_remote.py" \
    --ip "$PRINTER_IP" \
    monitor

echo -e "\n${GREEN}🎉 Workflow complete!${NC}"
