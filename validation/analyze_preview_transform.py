#!/usr/bin/env python3
"""
Analyze belt G-code coordinates and validate the inverse transform
used in GCodeViewer to map G-code space back to model space.

Usage: python3 analyze_preview_transform.py <gcode_file>
"""

import sys
import re
import math
import numpy as np

BELT_ANGLE = 45.0  # degrees
THETA = math.radians(BELT_ANGLE)
TAN_THETA = math.tan(THETA)  # 1.0 for 45°
K = 1.0 + TAN_THETA  # 2.0 for 45°
COS_THETA = math.cos(THETA)
SQRT2 = math.sqrt(2)

def parse_gcode_moves(filepath):
    """Parse G-code file and extract all G0/G1 moves with extrusion info."""
    moves = []
    x, y, z, e = 0.0, 0.0, 0.0, 0.0
    layer = -1
    move_type = "travel"

    with open(filepath) as f:
        for line in f:
            line = line.strip()

            # Track layer changes
            if line.startswith(";LAYER_CHANGE"):
                layer += 1
                continue
            if line.startswith(";TYPE:"):
                move_type = line[6:]
                continue

            # Skip non-G0/G1
            if not (line.startswith("G0 ") or line.startswith("G1 ") or
                    line.startswith("G0\t") or line.startswith("G1\t")):
                # Check for G92 (position reset)
                if line.startswith("G92"):
                    m = re.search(r'X([-\d.]+)', line)
                    if m: x = float(m.group(1))
                    m = re.search(r'Y([-\d.]+)', line)
                    if m: y = float(m.group(1))
                    m = re.search(r'Z([-\d.]+)', line)
                    if m: z = float(m.group(1))
                    m = re.search(r'E([-\d.]+)', line)
                    if m: e = float(m.group(1))
                continue

            # Parse G0/G1
            has_e = False
            m = re.search(r'X([-\d.]+)', line)
            if m: x = float(m.group(1))
            m = re.search(r'Y([-\d.]+)', line)
            if m: y = float(m.group(1))
            m = re.search(r'Z([-\d.]+)', line)
            if m: z = float(m.group(1))
            m = re.search(r'E([-\d.]+)', line)
            if m:
                new_e = float(m.group(1))
                has_e = (new_e > e)
                e = new_e

            if layer >= 0:  # Only after first layer change
                moves.append({
                    'x': x, 'y': y, 'z': z,
                    'layer': layer,
                    'extrusion': has_e,
                    'type': move_type
                })

    return moves

def inverse_transform(x_gc, y_gc, z_gc):
    """
    Current GCodeViewer inverse: G-code → model space
    X_model = X_gcode
    Y_model = Z_gcode - Y_gcode * K  (K = 1 + tan(45°) = 2)
    Z_model = Y_gcode
    """
    x_model = x_gc
    y_model = z_gc - y_gc * K
    z_model = y_gc
    return x_model, y_model, z_model

def forward_transform(x_model, y_model, z_model):
    """
    Forward: model → virtual space (trafo_centered)
    Y_virt = Z_model
    Z_virt = Y_model + Z_model
    """
    x_virt = x_model
    y_virt = z_model
    z_virt = y_model + z_model
    return x_virt, y_virt, z_virt

def inclined_z(x_virt, y_virt, z_virt):
    """
    Virtual → G-code (inclined Z)
    X_gcode = X_virt
    Y_gcode = Y_virt
    Z_gcode = Z_virt + Y_virt * tan(θ)
    """
    x_gc = x_virt
    y_gc = y_virt
    z_gc = z_virt + y_virt * TAN_THETA
    return x_gc, y_gc, z_gc

def machine_transform(x_gc, y_gc, z_gc):
    """
    G-code → machine coordinates (what the printer sees)
    X_mach = X_gcode
    Y_mach = √2 × Y_gcode  (gantry moves along 45° incline)
    Z_mach = -Y_gcode + Z_gcode  (belt motion)
    """
    x_mach = x_gc
    y_mach = SQRT2 * y_gc
    z_mach = -y_gc + z_gc
    return x_mach, y_mach, z_mach

def analyze_roundtrip():
    """Verify the math with a 10mm cube at known position."""
    print("=" * 70)
    print("ROUNDTRIP VERIFICATION: 10mm cube, corners at model-space")
    print("  After trafo_centered shift: Y_min=0, Z_min=0")
    print("  Cube: X=[120,130], Y=[0,10], Z=[0,10]")
    print("=" * 70)

    corners = [
        (120, 0, 0), (130, 0, 0),
        (120, 10, 0), (130, 10, 0),
        (120, 0, 10), (130, 0, 10),
        (120, 10, 10), (130, 10, 10),
    ]

    print(f"\n{'Model (X,Y,Z)':>25} → {'Virtual (X,Y,Z)':>25} → {'G-code (X,Y,Z)':>25} → {'Inverse (X,Y,Z)':>25} → {'Match?':>6}")
    print("-" * 120)

    all_match = True
    for mx, my, mz in corners:
        vx, vy, vz = forward_transform(mx, my, mz)
        gx, gy, gz = inclined_z(vx, vy, vz)
        ix, iy, iz = inverse_transform(gx, gy, gz)
        match = abs(ix-mx)<0.001 and abs(iy-my)<0.001 and abs(iz-mz)<0.001
        if not match: all_match = False
        print(f"  ({mx:6.1f},{my:6.1f},{mz:6.1f}) → ({vx:6.1f},{vy:6.1f},{vz:6.1f}) → ({gx:6.1f},{gy:6.1f},{gz:6.1f}) → ({ix:6.1f},{iy:6.1f},{iz:6.1f}) → {'OK' if match else 'FAIL'}")

    # Also check machine coords
    print(f"\n{'G-code (X,Y,Z)':>25} → {'Machine (X,Y,Z)':>25} → Z_mach const per layer?")
    print("-" * 80)
    for mx, my, mz in corners:
        vx, vy, vz = forward_transform(mx, my, mz)
        gx, gy, gz = inclined_z(vx, vy, vz)
        machx, machy, machz = machine_transform(gx, gy, gz)
        print(f"  ({gx:6.1f},{gy:6.1f},{gz:6.1f}) → ({machx:7.1f},{machy:7.1f},{machz:7.1f})   Z_mach={machz:.3f}")

    return all_match

def analyze_gcode(filepath):
    """Parse G-code and analyze coordinates before and after inverse transform."""
    print(f"\n{'=' * 70}")
    print(f"ANALYZING G-CODE: {filepath}")
    print(f"{'=' * 70}")

    moves = parse_gcode_moves(filepath)
    print(f"Total moves parsed: {len(moves)}")

    # Filter extrusion moves only (skip travels)
    ext_moves = [m for m in moves if m['extrusion']]
    print(f"Extrusion moves: {len(ext_moves)}")

    if not ext_moves:
        print("No extrusion moves found!")
        return

    # G-code space bounding box
    gc_x = [m['x'] for m in ext_moves]
    gc_y = [m['y'] for m in ext_moves]
    gc_z = [m['z'] for m in ext_moves]

    print(f"\n--- G-CODE SPACE (raw, as in G-code file) ---")
    print(f"  X: [{min(gc_x):.3f}, {max(gc_x):.3f}]  span={max(gc_x)-min(gc_x):.3f}")
    print(f"  Y: [{min(gc_y):.3f}, {max(gc_y):.3f}]  span={max(gc_y)-min(gc_y):.3f}")
    print(f"  Z: [{min(gc_z):.3f}, {max(gc_z):.3f}]  span={max(gc_z)-min(gc_z):.3f}")

    # Apply current inverse transform
    inv_moves = []
    for m in ext_moves:
        ix, iy, iz = inverse_transform(m['x'], m['y'], m['z'])
        inv_moves.append({'x': ix, 'y': iy, 'z': iz, 'layer': m['layer'], 'type': m['type']})

    inv_x = [m['x'] for m in inv_moves]
    inv_y = [m['y'] for m in inv_moves]
    inv_z = [m['z'] for m in inv_moves]

    print(f"\n--- AFTER INVERSE TRANSFORM (model space) ---")
    print(f"  X: [{min(inv_x):.3f}, {max(inv_x):.3f}]  span={max(inv_x)-min(inv_x):.3f}")
    print(f"  Y: [{min(inv_y):.3f}, {max(inv_y):.3f}]  span={max(inv_y)-min(inv_y):.3f}")
    print(f"  Z: [{min(inv_z):.3f}, {max(inv_z):.3f}]  span={max(inv_z)-min(inv_z):.3f}")

    # Expected for a 10mm cube (after trafo_centered, Y_min=0, Z_min=0)
    # X centered on bed (~125mm for 250mm bed)
    # Y: [0, ~10]
    # Z: [0, ~10]
    print(f"\n--- EXPECTED (10mm cube) ---")
    print(f"  X: ~[120, 130]  span=10")
    print(f"  Y: ~[0, 10]     span=10")
    print(f"  Z: ~[0, 10]     span=10")

    # Machine space check
    mach_z_per_layer = {}
    for m in ext_moves:
        _, _, mz = machine_transform(m['x'], m['y'], m['z'])
        l = m['layer']
        if l not in mach_z_per_layer:
            mach_z_per_layer[l] = []
        mach_z_per_layer[l].append(mz)

    print(f"\n--- MACHINE SPACE Z CONSISTENCY (should be constant per layer) ---")
    for layer in sorted(mach_z_per_layer.keys())[:5]:
        vals = mach_z_per_layer[layer]
        spread = max(vals) - min(vals)
        print(f"  Layer {layer:3d}: Z_mach=[{min(vals):.3f}, {max(vals):.3f}] spread={spread:.4f}")
    if len(mach_z_per_layer) > 5:
        print(f"  ... ({len(mach_z_per_layer)} layers total)")

    # Per-layer analysis of inverse transform
    print(f"\n--- PER-LAYER INVERSE TRANSFORM SAMPLE ---")
    layers_to_show = [0, 1, 2, len(set(m['layer'] for m in ext_moves))//2]
    for target_layer in layers_to_show:
        layer_moves = [m for m in ext_moves if m['layer'] == target_layer]
        layer_inv = [m for m in inv_moves if m['layer'] == target_layer]
        if not layer_moves:
            continue
        gc_ys = [m['y'] for m in layer_moves]
        gc_zs = [m['z'] for m in layer_moves]
        inv_ys = [m['y'] for m in layer_inv]
        inv_zs = [m['z'] for m in layer_inv]
        print(f"  Layer {target_layer}:")
        print(f"    G-code:  Y=[{min(gc_ys):.3f}, {max(gc_ys):.3f}]  Z=[{min(gc_zs):.3f}, {max(gc_zs):.3f}]")
        print(f"    Inverse: Y=[{min(inv_ys):.3f}, {max(inv_ys):.3f}]  Z=[{min(inv_zs):.3f}, {max(inv_zs):.3f}]")

    # Check: what does Prepare pane show?
    # The Prepare pane shows the object at its bed position. For a belt printer,
    # the object's model-space coords include the bed placement offset.
    # trafo_centered shifts Y_min=0, Z_min=0, then applies forward transform.
    # The resulting virtual-space coords are what the Plater uses for display?
    # Actually no - the Prepare pane shows the ORIGINAL model, not the virtual space.
    # It shows the model at its placed position on the bed.

    # For comparison, what does GCodeViewer normally show for non-belt printers?
    # It shows G-code XY on the bed, Z as height. Same as the model placement.
    # For belt printers, we need the same: X on bed, Y as depth, Z as height.

    print(f"\n--- DIAGNOSTIC: CHECKING ALTERNATIVE TRANSFORMS ---")

    # Alt 1: Just undo inclined Z (Z_gcode = Z_virt + Y_virt * tan(θ))
    # → Z_virt = Z_gcode - Y_gcode * tan(θ), Y_virt = Y_gcode
    alt1_y = [m['y'] for m in ext_moves]  # unchanged
    alt1_z = [m['z'] - m['y'] * TAN_THETA for m in ext_moves]
    print(f"  Alt1 (undo inclined Z only):")
    print(f"    Y: [{min(alt1_y):.3f}, {max(alt1_y):.3f}]  span={max(alt1_y)-min(alt1_y):.3f}")
    print(f"    Z: [{min(alt1_z):.3f}, {max(alt1_z):.3f}]  span={max(alt1_z)-min(alt1_z):.3f}")

    # Alt 2: Undo inclined Z, then inverse forward transform
    # virtual: Y_virt = Y_gcode, Z_virt = Z_gcode - Y_gcode * tan(θ)
    # inverse forward [0,1;1,1]^-1 = [1,-1;-1,2]? No...
    # Forward: Y_virt = Z_model, Z_virt = Y_model + Z_model
    # So: Z_model = Y_virt, Y_model = Z_virt - Z_model = Z_virt - Y_virt
    alt2_z_model = [m['y'] for m in ext_moves]
    alt2_y_model = [(m['z'] - m['y'] * TAN_THETA) - m['y'] for m in ext_moves]
    print(f"  Alt2 (undo inclined Z, then inverse forward):")
    print(f"    Y_model: [{min(alt2_y_model):.3f}, {max(alt2_y_model):.3f}]  span={max(alt2_y_model)-min(alt2_y_model):.3f}")
    print(f"    Z_model: [{min(alt2_z_model):.3f}, {max(alt2_z_model):.3f}]  span={max(alt2_z_model)-min(alt2_z_model):.3f}")
    print(f"  (This should equal current inverse: K=1+tan(θ)={K:.3f}, Z-Y*K = Z-Y*(1+tan) = (Z-Y*tan)-Y)")

    # Alt 3: No transform (identity - what preview shows without our fix)
    print(f"  Alt3 (no transform / identity):")
    print(f"    Y: [{min(gc_y):.3f}, {max(gc_y):.3f}]  span={max(gc_y)-min(gc_y):.3f}")
    print(f"    Z: [{min(gc_z):.3f}, {max(gc_z):.3f}]  span={max(gc_z)-min(gc_z):.3f}")

    # What does the Prepare pane ACTUALLY show?
    # The model instance is placed on the bed. For belt, the bed is tilted 45°.
    # The model's bounding box in bed coords: after instance transform.
    # In GLVolume, the model is rendered with its instance transform.
    # The G-code paths need to be in the same coordinate system.
    #
    # Key question: does Prepare show virtual-space coords or model-space coords?
    # Answer: Prepare shows the model in BED coordinates. For belt printers,
    # the bed has a 45° tilt. But the 3D view still uses XYZ with Z=up.
    # The model is placed with its trafo_centered transform applied.
    #
    # trafo_centered = forward_transform applied to shifted model.
    # The resulting virtual-space coords ARE what Prepare renders.
    # So the Preview should show virtual-space coords too!

    print(f"\n--- IMPORTANT INSIGHT ---")
    print(f"  If Prepare shows VIRTUAL-SPACE coords (after forward transform),")
    print(f"  then Preview should undo ONLY inclined Z, NOT the forward transform!")
    print(f"  Alt1 results should match what Prepare shows.")
    print(f"")
    print(f"  Virtual space for 10mm cube (Y_min=0, Z_min=0):")
    print(f"    Y_virt = Z_model: [0, 10]")
    print(f"    Z_virt = Y_model + Z_model: [0, 20]")
    print(f"  After inclined Z:  Z_gcode = Z_virt + Y_virt: [0, 30]")
    print(f"  After undo inclined Z (Alt1): Z=[0, 20]  (matches virtual Z)")

def main():
    # First: verify math roundtrip
    ok = analyze_roundtrip()
    print(f"\nRoundtrip verification: {'PASS' if ok else 'FAIL'}")

    # Then: analyze real G-code
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = "/tmp/plate_1.gcode"

    analyze_gcode(filepath)

if __name__ == "__main__":
    main()
