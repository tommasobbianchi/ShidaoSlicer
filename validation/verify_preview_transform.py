#!/usr/bin/env python3
"""
Quick verification of the K=1/√2 preview transform on G-code coordinates.
Parses G-code, applies the machine→model inverse, reports bounding boxes.
"""
import sys
import re
import math

SQRT2 = math.sqrt(2)
INV_SQRT2 = 1.0 / SQRT2

def parse_extrusion_moves(filepath):
    """Parse G-code for extrusion moves (after first LAYER_CHANGE)."""
    moves = []
    x, y, z, e = 0.0, 0.0, 0.0, 0.0
    layer = -1
    move_type = "unknown"

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line.startswith(";LAYER_CHANGE"):
                layer += 1
                continue
            if line.startswith(";TYPE:"):
                move_type = line[6:]
                continue
            if line.startswith("G92"):
                for axis, val in re.findall(r'([XYZE])([-\d.]+)', line):
                    if axis == 'X': x = float(val)
                    elif axis == 'Y': y = float(val)
                    elif axis == 'Z': z = float(val)
                    elif axis == 'E': e = float(val)
                continue
            if not (line.startswith("G0 ") or line.startswith("G1 ")):
                continue
            old_e = e
            for axis, val in re.findall(r'([XYZE])([-\d.]+)', line):
                if axis == 'X': x = float(val)
                elif axis == 'Y': y = float(val)
                elif axis == 'Z': z = float(val)
                elif axis == 'E': e = float(val)
            if layer >= 0 and e > old_e:
                moves.append({'x': x, 'y': y, 'z': z, 'layer': layer, 'type': move_type})
    return moves

def transform_k(moves, k_val):
    """Apply Y_model = Z - Y*K, Z_model = Y*K transform."""
    results = []
    for m in moves:
        z_model = m['y'] * k_val
        y_model = m['z'] - z_model
        results.append({'x': m['x'], 'y': y_model, 'z': z_model, 'layer': m['layer']})
    return results

def bbox(moves, key='x'):
    vals = [m[key] for m in moves]
    return min(vals), max(vals), max(vals) - min(vals)

def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else "/tmp/plate_1.gcode"
    moves = parse_extrusion_moves(filepath)
    print(f"File: {filepath}")
    print(f"Extrusion moves: {len(moves)}")

    if not moves:
        print("No extrusion moves found!")
        return

    # Raw G-code bounding box
    print(f"\n--- RAW G-CODE (machine coords) ---")
    print(f"  X: [{bbox(moves,'x')[0]:.3f}, {bbox(moves,'x')[1]:.3f}]  span={bbox(moves,'x')[2]:.3f}")
    print(f"  Y: [{bbox(moves,'y')[0]:.3f}, {bbox(moves,'y')[1]:.3f}]  span={bbox(moves,'y')[2]:.3f}")
    print(f"  Z: [{bbox(moves,'z')[0]:.3f}, {bbox(moves,'z')[1]:.3f}]  span={bbox(moves,'z')[2]:.3f}")

    # Try different K values
    ks = {
        'K=2.0 (old: 1+tan45)': 2.0,
        'K=1/√2 (new: undo √2)': INV_SQRT2,
        'K=1.0 (undo forward only)': 1.0,
        'K=0 (no Y factor)': 0.0,
        'K=√2 (just √2)': SQRT2,
    }

    for name, k in ks.items():
        t = transform_k(moves, k)
        xb = bbox(t, 'x')
        yb = bbox(t, 'y')
        zb = bbox(t, 'z')
        # Score: how close are Y_span and Z_span to each other (for a cube)
        span_diff = abs(yb[2] - zb[2])
        # Also check: is Z_min close to 0? (model sitting on bed)
        z_min_score = abs(zb[0])
        print(f"\n--- {name} ---")
        print(f"  X: [{xb[0]:.3f}, {xb[1]:.3f}]  span={xb[2]:.3f}")
        print(f"  Y: [{yb[0]:.3f}, {yb[1]:.3f}]  span={yb[2]:.3f}")
        print(f"  Z: [{zb[0]:.3f}, {zb[1]:.3f}]  span={zb[2]:.3f}")
        print(f"  Quality: Y_span≈Z_span diff={span_diff:.3f}, Z_min={zb[0]:.3f}")

    # Also check if any debug log exists
    try:
        with open("/tmp/belt_preview_debug.log") as f:
            print(f"\n--- /tmp/belt_preview_debug.log ---")
            print(f.read())
    except:
        print(f"\n(No debug log found at /tmp/belt_preview_debug.log)")

if __name__ == "__main__":
    main()
