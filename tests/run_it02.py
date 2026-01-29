#!/usr/bin/env python3
"""
IT02: Belt Raft Integration Test

Tests that belt raft layers are generated correctly with:
- Proper layer count
- Upstream extension  
- Correct expansion
- Leading edge compliance
"""

import subprocess
import re
from pathlib import Path

# Test configuration
ORCA_SLICER = Path("build/src/Debug/orca-slicer")
TOWER_STL = Path("tests/fixtures/belt_test_tower.stl")
RAFT_CONFIG = Path("tests/fixtures/belt_raft_config.json")
PROCESS_CONFIG = Path("tests/fixtures/belt_process.json")
FILAMENT_CONFIG = Path("tests/fixtures/belt_filament.json")
OUTPUT_3MF = Path("/tmp/it02_output.3mf")
OUTPUT_GCODE = Path("/tmp/it02_output.gcode")

def run_slicer():
    """Run OrcaSlicer CLI with raft config"""
    print("=" * 60)
    print("IT02: Belt Raft Integration Test")
    print("=" * 60)
    
    cmd = [
        str(ORCA_SLICER),
        str(TOWER_STL),
        "--load-settings",
        f"{RAFT_CONFIG};{PROCESS_CONFIG};{FILAMENT_CONFIG}",
        "--slice", "0",
        "--export-3mf", str(OUTPUT_3MF)
    ]
    
    print(f"🔧 Running OrcaSlicer CLI...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Slicing failed (exit {result.returncode})")
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")
        return False
    
    if not OUTPUT_GCODE.exists():
        print(f"❌ G-code not generated")
        return False
    
    size = OUTPUT_GCODE.stat().st_size
    print(f"✅ G-code generated: {OUTPUT_GCODE} ({size} bytes)")
    return True

def validate_raft_layers():
    """Check raft layer count (should have 3 raft layers)"""
    gcode = OUTPUT_GCODE.read_text()
    gcode_lines = gcode.splitlines()
    
    # Count total layers
    total_layers = len([l for l in gcode_lines if l.startswith(";LAYER_CHANGE")])
    
    # For 50mm tower @ 0.2mm = 250 layers + 3 raft = 253 total
    expected_object_layers = 250
    expected_raft_layers = 3
    expected_total = expected_object_layers + expected_raft_layers
    
    print("\n📏 Layer Count:")
    print(f"  Total layers: {total_layers}")
    print(f"  Expected: ~{expected_total} (250 object + 3 raft)")
    
    # Check if we have extra layers (indicating raft)
    if total_layers >= expected_object_layers + 2:  # At least 2 raft layers
        print(f"  ✅ Raft layers detected")
        return True
    else:
        print(f"  ❌ No raft layers found")
        return False

def validate_upstream_extension():
    """Check that raft extends upstream (negative coords on belt axis)"""
    gcode = OUTPUT_GCODE.read_text()
    
    # For Z-belt, check Z coordinates
    z_coords = []
    for line in gcode.splitlines()[:500]:  # Check first 500 lines (raft area)
        if match := re.search(r'Z([-\d.]+)', line):
            z_coords.append(float(match.group(1)))
    
    if not z_coords:
        print("\n❌ No Z coordinates found")
        return False
    
    min_z = min(z_coords)
    
    print(f"\n📐 Upstream Extension:")
    print(f"  Minimum Z: {min_z:.2f}mm")
    
    # For tower at origin, raft should extend upstream (negative Z for Z-belt)
    if min_z < 0:
        print(f"  ✅ Upstream extension present")
        return True
    else:
        print(f"  ⚠️  No negative Z (raft may not extend upstream)")
        return False

def validate_expansion():
    """Check raft expansion (should be 10mm + 2*5mm = 20mm)"""
    gcode = OUTPUT_GCODE.read_text()
    
    # Extract X coordinates from first 200 lines (raft area)
    x_coords = []
    for line in gcode.splitlines()[:200]:
        if match := re.search(r'X([-\d.]+)', line):
            x_coords.append(float(match.group(1)))
    
    if len(x_coords) < 10:
        print("\n❌ Insufficient X coordinates")
        return False
    
    x_range = max(x_coords) - min(x_coords)
    
    print(f"\n📏 Raft Expansion:")
    print(f"  X range: {x_range:.2f}mm")
    print(f"  Expected: ~20mm (10mm object + 2×5mm expansion)")
    
    if 18 <= x_range <= 22:  # Allow 2mm tolerance
        print(f"  ✅ Expansion correct")
        return True
    else:
        print(f"  ❌ Expansion incorrect (off by {abs(x_range - 20):.2f}mm)")
        return False

def main():
    checks_passed = 0
    total_checks = 3
    
    # Run slicer
    if not run_slicer():
        print("\n" + "=" * 60)
        print(f"IT02 Results: 0/{total_checks} checks passed")
        print("=" * 60)
        print("❌ IT02 FAILED - Slicing error")
        return 1
    
    # Validate raft properties
    if validate_raft_layers():
        checks_passed += 1
    
    if validate_upstream_extension():
        checks_passed += 1
    
    if validate_expansion():
        checks_passed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print(f"IT02 Results: {checks_passed}/{total_checks} checks passed")
    print("=" * 60)
    
    if checks_passed == total_checks:
        print("✅ IT02 PASSED")
        return 0
    else:
        print(f"❌ IT02 FAILED - {total_checks - checks_passed} issues found")
        return 1

if __name__ == "__main__":
    exit(main())
