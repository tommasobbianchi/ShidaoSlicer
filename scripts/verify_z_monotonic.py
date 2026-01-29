#!/usr/bin/env python3
import sys
import re

def verify_z_monotonicity(filename):
    print(f"Checking monotonicity of Z in {filename}...")
    
    last_z = -99999.0
    max_z_drop = 0.0
    failures = 0
    line_num = 0
    
    with open(filename, 'r') as f:
        for line in f:
            line_num += 1
            # Parse Z
            match = re.search(r'Z([0-9.-]+)', line)
            if match:
                z = float(match.group(1))
                
                # Check for drop
                if z < last_z:
                    drop = last_z - z
                    if drop > 0.1: # Tolerance 0.1mm
                        print(f"WARN: Z dropped from {last_z} to {z} (delta {-drop}) at line {line_num}: {line.strip()}")
                        max_z_drop = max(max_z_drop, drop)
                        failures += 1
                
                last_z = z

    print("-" * 40)
    print(f"Verification Complete.")
    print(f"Total significant Z drops (>0.1mm): {failures}")
    print(f"Max Z drop observed: {max_z_drop} mm")
    
    if failures > 5: # Some start G-code might reset Z, so allow very few
        print("FAIL: Z is not monotonic. Belt moves backwards repeatedly!")
        sys.exit(1)
    else:
        print("PASS: Z appears monotonic (Belt is advancing correctly).")
        sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: verify_z_monotonic.py <gcode_file>")
        sys.exit(1)
    
    verify_z_monotonicity(sys.argv[1])
