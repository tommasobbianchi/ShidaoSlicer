#!/usr/bin/env python3
"""Detailed G-code coordinate analysis - show actual moves per layer."""
import sys
import re
import math

def parse_detailed(filepath):
    x, y, z, e = 0.0, 0.0, 0.0, 0.0
    layer = -1
    layer_z_comment = None
    move_type = "unknown"
    layer_data = {}

    with open(filepath) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            if line.startswith(";LAYER_CHANGE"):
                layer += 1
                continue
            if line.startswith(";Z:"):
                layer_z_comment = float(line[3:])
                continue
            if line.startswith(";TYPE:"):
                move_type = line[6:]
                continue

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

            if not (line.startswith("G0 ") or line.startswith("G1 ")):
                continue

            old_e = e
            m = re.search(r'X([-\d.]+)', line)
            if m: x = float(m.group(1))
            m = re.search(r'Y([-\d.]+)', line)
            if m: y = float(m.group(1))
            m = re.search(r'Z([-\d.]+)', line)
            if m: z = float(m.group(1))
            m = re.search(r'E([-\d.]+)', line)
            if m: e = float(m.group(1))

            has_e = (e > old_e)

            if layer >= 0:
                if layer not in layer_data:
                    layer_data[layer] = {
                        'z_comment': layer_z_comment,
                        'moves': [],
                        'ext_moves': []
                    }
                move = {'x': x, 'y': y, 'z': z, 'e': has_e, 'type': move_type, 'line': line_num}
                layer_data[layer]['moves'].append(move)
                if has_e:
                    layer_data[layer]['ext_moves'].append(move)

    return layer_data

def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else "/tmp/plate_1.gcode"
    data = parse_detailed(filepath)

    print(f"File: {filepath}")
    print(f"Total layers: {len(data)}")
    print()

    TAN45 = 1.0  # tan(45°)

    # Show first 5 layers in detail
    for layer_num in range(min(5, len(data))):
        ld = data[layer_num]
        ext = ld['ext_moves']
        if not ext:
            print(f"Layer {layer_num}: z_comment={ld['z_comment']:.4f}, NO extrusion moves")
            continue

        gc_ys = [m['y'] for m in ext]
        gc_zs = [m['z'] for m in ext]
        layer_z = ld['z_comment']

        print(f"Layer {layer_num}: z_comment={layer_z:.4f}, {len(ext)} extrusion moves")
        print(f"  Y: [{min(gc_ys):.4f}, {max(gc_ys):.4f}]")
        print(f"  Z: [{min(gc_zs):.4f}, {max(gc_zs):.4f}]")

        # Check if Z = layer_z + Y * tan(45°)
        print(f"  Checking Z = layer_z + Y * tan(45°) = {layer_z:.4f} + Y:")
        errors = []
        for m in ext:
            expected_z = layer_z + m['y'] * TAN45
            err = m['z'] - expected_z
            errors.append(err)
        print(f"    Z error: min={min(errors):.4f}, max={max(errors):.4f}, mean={sum(errors)/len(errors):.4f}")

        # Show first 10 moves
        print(f"  First 10 extrusion moves:")
        for m in ext[:10]:
            expected_z = layer_z + m['y'] * TAN45
            z_err = m['z'] - expected_z
            mach_z = -m['y'] + m['z']
            print(f"    X={m['x']:8.3f} Y={m['y']:8.3f} Z={m['z']:8.3f}  "
                  f"expected_Z={expected_z:8.3f} z_err={z_err:+.4f}  "
                  f"Z_mach={mach_z:8.3f}  type={m['type']}")

        print()

    # Summary stats for all layers
    print("=" * 80)
    print("ALL LAYERS SUMMARY:")
    print(f"{'Layer':>5} {'Z_comment':>10} {'N_ext':>6} {'Y_min':>8} {'Y_max':>8} "
          f"{'Z_min':>8} {'Z_max':>8} {'Z_err_max':>10} {'Z_mach_spread':>14}")
    for layer_num in sorted(data.keys()):
        ld = data[layer_num]
        ext = ld['ext_moves']
        if not ext:
            print(f"{layer_num:>5} {ld['z_comment']:>10.4f} {0:>6}")
            continue

        layer_z = ld['z_comment']
        gc_ys = [m['y'] for m in ext]
        gc_zs = [m['z'] for m in ext]

        z_errors = [m['z'] - (layer_z + m['y'] * TAN45) for m in ext]
        mach_zs = [-m['y'] + m['z'] for m in ext]

        print(f"{layer_num:>5} {layer_z:>10.4f} {len(ext):>6} "
              f"{min(gc_ys):>8.3f} {max(gc_ys):>8.3f} "
              f"{min(gc_zs):>8.3f} {max(gc_zs):>8.3f} "
              f"{max(abs(e) for e in z_errors):>10.4f} "
              f"{max(mach_zs)-min(mach_zs):>14.4f}")

if __name__ == "__main__":
    main()
