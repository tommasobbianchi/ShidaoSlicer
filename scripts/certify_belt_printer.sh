#!/bin/bash
# Belt Printer Certification Automation Script
# Executes certification tests sequentially with verification

set -e

CERT_DIR="/home/user/projects/ORCA_BELT/certification_tests"
PRINTER_IP="${PRINTER_IP:-}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if remote access is configured
if [ -n "$PRINTER_IP" ]; then
    REMOTE_MODE=true
    echo -e "${BLUE}🌐 Remote mode: $PRINTER_IP${NC}"
else
    REMOTE_MODE=false
    echo -e "${YELLOW}📁 Local mode: Files will be copied to current directory${NC}"
fi

# Function to run a test
run_test() {
    local test_file="$1"
    local test_name="$2"
    local phase="$3"
    
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}TEST: $test_name${NC}"
    echo -e "${BLUE}File: $(basename $test_file)${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    
    if [ "$REMOTE_MODE" = true ]; then
        # Upload and run remotely
        python3 scripts/klipper_remote.py --ip $PRINTER_IP upload "$test_file"
        python3 scripts/klipper_remote.py --ip $PRINTER_IP start "$(basename $test_file)"
        
        echo -e "\n${YELLOW}Monitor the printer now...${NC}"
        python3 scripts/klipper_remote.py --ip $PRINTER_IP monitor &
        MONITOR_PID=$!
        
        # Wait for user confirmation
        read -p "$(echo -e ${GREEN}Test complete? [y/n/abort]:${NC}) " -r
        kill $MONITOR_PID 2>/dev/null || true
        
        case $REPLY in
            y|Y)
                echo -e "${GREEN}✅ Test PASSED${NC}"
                return 0
                ;;
            a|A)
                echo -e "${RED}🛑 ABORT - Certification stopped${NC}"
                exit 1
                ;;
            *)
                echo -e "${RED}❌ Test FAILED${NC}"
                return 1
                ;;
        esac
    else
        # Local mode - just copy file
        cp "$test_file" "./"
        echo -e "${GREEN}✅ File copied: $(basename $test_file)${NC}"
        echo -e "${YELLOW}Upload to printer manually and run${NC}"
        read -p "$(echo -e ${GREEN}Test passed? [y/n]:${NC}) " -r
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            return 0
        else
            return 1
        fi
    fi
}

# Phase selection
PHASE=${1:-all}

echo -e "${GREEN}🎯 Belt Printer Certification Protocol${NC}"
echo -e "Phase: $PHASE\n"

# Phase 1: Basic Operations
if [ "$PHASE" = "all" ] || [ "$PHASE" = "1" ]; then
    echo -e "\n${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}   PHASE 1: BASIC OPERATIONS (15 min)${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}\n"
    
    run_test "$CERT_DIR/test_01_bed_heating.gcode" "Bed Heating to 80°C" "1.1" || exit 1
    run_test "$CERT_DIR/test_02_hotend_heating.gcode" "Hotend Heating to 235°C" "1.2" || exit 1
    run_test "$CERT_DIR/test_03_both_heaters.gcode" "Both Heaters Simultaneous" "1.3" || exit 1
    
    echo -e "\n${GREEN}✅ PHASE 1 COMPLETE${NC}"
fi

# Phase 2: Movement Verification
if [ "$PHASE" = "all" ] || [ "$PHASE" = "2" ]; then
    echo -e "\n${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}  PHASE 2: MOVEMENT VERIFICATION (20 min)${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}\n"
    
    run_test "$CERT_DIR/test_04_xy_homing.gcode" "XY Homing" "2.1" || exit 1
    run_test "$CERT_DIR/test_05_z_movement.gcode" "Z Movement (Belt Axis)" "2.2" || exit 1
    
    echo -e "\n${RED}⚠️  CRITICAL TEST AHEAD${NC}"
    echo -e "${YELLOW}Next test verifies V→F coordinate transform${NC}"
    echo -e "${YELLOW}Y coordinate MUST remain constant!${NC}"
    read -p "$(echo -e ${GREEN}Ready? [Enter to continue]:${NC})"
    
    run_test "$CERT_DIR/test_06_coordinate_pattern.gcode" "Coordinate Pattern (V→F Transform)" "2.3" || exit 1
    
    echo -e "\n${GREEN}✅ PHASE 2 COMPLETE${NC}"
fi

# Phase 3: Extrusion Tests
if [ "$PHASE" = "all" ] || [ "$PHASE" = "3" ]; then
    echo -e "\n${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}    PHASE 3: EXTRUSION TESTS (15 min)${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}\n"
    
    run_test "$CERT_DIR/test_07_cold_check.gcode" "Cold Extrusion Prevention" "3.1" || exit 1
    run_test "$CERT_DIR/test_08_hot_extrusion.gcode" "Hot Extrusion Test" "3.2" || exit 1
    run_test "$CERT_DIR/test_09_move_extrude.gcode" "Movement + Extrusion" "3.3" || exit 1
    
    echo -e "\n${GREEN}✅ PHASE 3 COMPLETE${NC}"
fi

# Phase 4: First Layer Certification
if [ "$PHASE" = "all" ] || [ "$PHASE" = "4" ]; then
    echo -e "\n${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${RED}  PHASE 4: FIRST LAYER CERTIFICATION (30 min)${NC}"
    echo -e "${RED}           ⚠️  CRITICAL TESTS ⚠️${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}\n"
    
    echo -e "${YELLOW}These tests are CRITICAL for belt printer success${NC}"
    echo -e "${YELLOW}Watch carefully for adhesion, uniformity, and stability${NC}"
    read -p "$(echo -e ${GREEN}Ready? [Enter to continue]:${NC})"
    
    run_test "$CERT_DIR/test_10_first_layer_line.gcode" "First Layer Single Line" "4.1" || exit 1
    run_test "$CERT_DIR/test_11_first_layer_square.gcode" "First Layer Square Outline" "4.2" || exit 1
    
    echo -e "\n${GREEN}✅ PHASE 4 COMPLETE${NC}"
    echo -e "${GREEN}🎉 First layer certification PASSED!${NC}"
fi

# Final summary
echo -e "\n${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}   CERTIFICATION TESTS COMPLETE!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}\n"

echo -e "${YELLOW}Next Steps:${NC}"
echo -e "  1. Phase 5: Multi-layer tests (generate with OrcaSlicer)"
echo -e "  2. Phase 6: Full cube print"
echo -e "\n${BLUE}Certification progress saved${NC}\n"
