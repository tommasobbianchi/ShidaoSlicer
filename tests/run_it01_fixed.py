#!/usr/bin/env python3
"""
IT01: Belt Slicing Integration Test (CORRECTED)
End-to-end test of V-frame slicing pipeline
"""
import subprocess
import sys
import re
from pathlib import Path

# Paths
ORCA_SLICER = Path("/home/user/projects/ORCA_BELT/build/src/Release/orca-slicer")
TEST_STL = Path("/home/user/projects/ORCA_BELT/tests/fixtures/belt_test_cube.stl")
TEST_CONFIG_MACHINE = Path("/home/user/projects/ORCA_BELT/tests/fixtures/belt_machine.json")
TEST_CONFIG_PROCESS = Path("/home/user/projects/ORCA_BELT/tests/fixtures/belt_process.json")
TEST_CONFIG_FILAMENT = Path("/home/user/projects/ORCA_BELT/tests/fixtures/belt_filament.json")
OUTPUT_3MF = Path("/tmp/it01_output.3mf")
OUTPUT_GCODE = Path("/tmp/it01_output.gcode")

def run_slice():
    """Execute OrcaSlicer CLI slice"""
    
    # Correct CLI format: semicolon-separated in SINGLE string
    settings_str = f"{TEST_CONFIG_MACHINE};{TEST_CONFIG_PROCESS}"
    
    cmd = [
        str(ORCA_SLICER),
        str(TEST_STL),
        "--load-settings", settings_str,
        "--load-filaments", str(TEST_CONFIG_FILAMENT),
        "--slice", "1",
        "--export-3mf", str(OUTPUT_3MF)
    ]
    
    print("🔧 Running OrcaSlicer CLI...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        print(f"❌ Slicing failed (exit {result.returncode})")
        print(f"STDERR: {result.stderr[-500:]}")  # Last 500 chars
        print(f"STDOUT: {result.stdout[-500:]}")
        return False
    
    if not OUTPUT_3MF.exists():
        print("❌ 3MF file not generated")
        return False
    
    # Extract G-code from 3MF (it's a zip file)
    import zipfile
    try:
        with zipfile.ZipFile(OUTPUT_3MF, 'r') as zf:
            gcode_files = [f for f in zf.namelist() if f.endswith('.gcode')]
            if not gcode_files:
                print("❌ No G-code found in 3MF")
                return False
            
            # Extract first gcode file
            with zf.open(gcode_files[0]) as gf:
                OUTPUT_GCODE.write_bytes(gf.read())
    except Exception as e:
        print(f"❌ Failed to extract G-code from 3MF: {e}")
        return False
    
    print(f"✅ G-code generated: {OUTPUT_GCODE} ({OUTPUT_GCODE.stat().st_size} bytes)")
    return True

def validate_coordinates():
    """Validate V→F coordinate mapping"""
    gcode = OUTPUT_GCODE.read_text()
    
    # Extract moves with all 3 coordinates
    moves = re.findall(r'G1 X([\\d\\.\\-]+) Y([\\d\\.\\-]+) Z([\\d\\.\\-]+)', gcode)
    
    if not moves:
        print("❌ No G1 XYZ moves found in G-code")
        return False
    
    x_coords = [float(m[0]) for m in moves[:100]]
    y_coords = [float(m[1]) for m in moves[:100]]
    z_coords = [float(m[2]) for m in moves[:100]]
    
    x_range = max(x_coords) - min(x_coords)
    y_range = max(y_coords) - min(y_coords)
    z_range = max(z_coords) - min(z_coords)
    
    print(f"\\n📊 Coordinate Analysis (first 100 XYZ moves):")
    print(f"  X range: {min(x_coords):.2f} to {max(x_coords):.2f} (Δ={x_range:.2f}mm)")
    print(f"  Y range: {min(y_coords):.2f} to {max(y_coords):.2f} (Δ={y_range:.2f}mm)")
    print(f"  Z range: {min(z_coords):.2f} to {max(z_coords):.2f} (Δ={z_range:.2f}mm)")
    
    # Validation checks
    checks_passed = 0
    checks_total = 3
    
    if 15 < x_range < 25:  # ~20mm cube width
        print("  ✅ X range correct (~20mm cube width)")
        checks_passed += 1
    else:
        print(f"  ❌ X range unexpected (expected ~20mm)")
    
    if y_range < 5:  # Y should be relatively stable (Yv belt travel)
        print("  ✅ Y stable (belt travel direction)")
        checks_passed += 1
    else:
        print("  ❌ Y range too large (should be stable)")
    
    if z_range > 10:  # Z should increase significantly (Zv layers)
        print("  ✅ Z increases with layers (V→F mapping OK)")
        checks_passed += 1
    else:
        print("  ❌ Z range too small")
    
    return checks_passed == checks_total

def validate_layer_count():
    """Check layer count matches object height"""
    gcode = OUTPUT_GCODE.read_text()
    gcode_lines = gcode.splitlines()
    
    print("\\n📏 Layer Count:")
    layer_count = len([line for line in gcode_lines if line.startswith(";LAYER_CHANGE")])
    expected_layers = 100
    print(f"  Found: {layer_count} layers")
    print(f"  Expected: ~{expected_layers} layers (20mm / 0.2mm)")
    
    if layer_count >= expected_layers * 0.8:  # Allow 20% tolerance
        print(f"  ✅ Layer count reasonable (within 20% of expected)")
        return True
    else:
        print(f"  ❌ Layer count mismatch (off by {abs(layer_count - expected_layers)})") 
        return False

def main():
    print("=" * 60)
    print("IT01: Belt Slicing Integration Test (FIXED)")
    print("=" * 60)
    
    # Check prerequisites
    if not ORCA_SLICER.exists():
        print(f"❌ OrcaSlicer binary not found: {ORCA_SLICER}")
        print("Run build first!")
        return 1
    
    if not TEST_STL.exists():
        print(f"❌ Test STL not found: {TEST_STL}")
        return 1
   
    # Run tests
    tests_passed = 0
    tests_total = 3
    
    if run_slice():
        tests_passed += 1
        
        if validate_coordinates():
            tests_passed += 1
        
        if validate_layer_count():
            tests_passed += 1
    
    # Summary
    print("\\n" + "=" * 60)
    print(f"IT01 Results: {tests_passed}/{tests_total} checks passed")
    print("=" * 60)
    
    if tests_passed == tests_total:
        print("✅ IT01 PASSED - V-frame slicing working correctly!")
        return 0
    else:
        print(f"❌ IT01 FAILED - {tests_total - tests_passed} issues found")
        return 1

if __name__ == "__main__":
    sys.exit(main())
