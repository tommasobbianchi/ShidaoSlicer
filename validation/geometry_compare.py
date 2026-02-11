#!/usr/bin/env python3
"""
Extract and compare actual print geometry from G-code
Ignores setup/metadata, focuses on toolpaths
"""

import re
from collections import defaultdict

def extract_toolpaths(gcode_file):
    """Extract only actual print moves (with extrusion)"""
    toolpaths = []
    
    with open(gcode_file) as f:
        for line in f:
            # Only G1 moves with extrusion
            if not line.startswith('G1'):
                continue
            if 'E' not in line:
                continue
                
            # Extract coordinates
            coords = {}
            for axis in ['X', 'Y', 'Z', 'E', 'F']:
                m = re.search(f'{axis}([\\d.-]+)', line)
                if m:
                    coords[axis] = float(m.group(1))
            
            if 'X' in coords or 'Y' in coords or 'Z' in coords:
                toolpaths.append(coords)
    
    return toolpaths

def analyze_geometry(toolpaths, name):
    """Analyze actual printed geometry"""
    print(f"\n{'='*60}")
    print(f"{name} - Geometry Analysis")
    print(f"{'='*60}")
    
    # Collect all coordinates
    x_vals = [p['X'] for p in toolpaths if 'X' in p]
    y_vals = [p['Y'] for p in toolpaths if 'Y' in p]
    z_vals = [p['Z'] for p in toolpaths if 'Z' in p]
    e_vals = [p['E'] for p in toolpaths if 'E' in p]
    
    print(f"\nTotal print moves: {len(toolpaths)}")
    print(f"\nCoordinate ranges:")
    print(f"  X: {min(x_vals):.2f} to {max(x_vals):.2f} (span: {max(x_vals)-min(x_vals):.2f}mm)")
    print(f"  Y: {min(y_vals):.2f} to {max(y_vals):.2f} (span: {max(y_vals)-min(y_vals):.2f}mm)")
    print(f"  Z: {min(z_vals):.2f} to {max(z_vals):.2f} (span: {max(z_vals)-min(z_vals):.2f}mm)")
    
    # Calculate total extrusion
    total_e = max(e_vals) if e_vals else 0
    print(f"\nTotal extrusion: {total_e:.2f}mm")
    
    # Detect layers (Z changes)
    z_changes = []
    prev_z = None
    for p in toolpaths:
        if 'Z' in p and p['Z'] != prev_z:
            z_changes.append(p['Z'])
            prev_z = p['Z']
    
    print(f"\nZ changes (layers): {len(z_changes)}")
    if len(z_changes) > 1:
        avg_layer = sum(z_changes[i+1] - z_changes[i] for i in range(len(z_changes)-1)) / (len(z_changes)-1)
        print(f"Average Z increment: {avg_layer:.3f}mm")
    
    return {
        'x_span': max(x_vals) - min(x_vals),
        'y_span': max(y_vals) - min(y_vals),
        'z_span': max(z_vals) - min(z_vals),
        'total_e': total_e,
        'moves': len(toolpaths),
        'z_layers': len(z_changes)
    }

def compare_geometries(geo1, geo2, name1, name2):
    """Compare two geometries"""
    print(f"\n{'='*60}")
    print(f"Geometry Comparison: {name1} vs {name2}")
    print(f"{'='*60}\n")
    
    metrics = ['x_span', 'y_span', 'z_span', 'total_e', 'moves', 'z_layers']
    
    for metric in metrics:
        v1 = geo1[metric]
        v2 = geo2[metric]
        diff = abs(v1 - v2)
        pct = (diff / v1 * 100) if v1 > 0 else 0
        
        match = "✅" if pct < 10 else "⚠️" if pct < 30 else "❌"
        
        print(f"{metric:12s}: {v1:8.2f} vs {v2:8.2f} | diff: {diff:6.2f} ({pct:5.1f}%) {match}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 3:
        print("Usage: python3 geometry_compare.py ref.gcode test.gcode")
        sys.exit(1)
    
    ref_file = sys.argv[1]
    test_file = sys.argv[2]
    
    print("Extracting toolpaths...")
    ref_paths = extract_toolpaths(ref_file)
    test_paths = extract_toolpaths(test_file)
    
    print(f"IdeaMaker: {len(ref_paths)} print moves")
    print(f"OrcaSlicer: {len(test_paths)} print moves")
    
    geo1 = analyze_geometry(ref_paths, "IdeaMaker")
    geo2 = analyze_geometry(test_paths, "OrcaSlicer")
    
    compare_geometries(geo1, geo2, "IdeaMaker", "OrcaSlicer")
    
    print(f"\n{'='*60}")
    print("Conclusion:")
    print(f"{'='*60}")
    print("\nIf geometry metrics match within 10-30%, slicers produce")
    print("equivalent output despite different G-code structure.")
