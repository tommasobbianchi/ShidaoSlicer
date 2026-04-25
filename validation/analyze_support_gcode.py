#!/usr/bin/env python3
"""Analyze belt printer G-code to check if support follows gravity.

For a belt printer with 45° inclined slicing, support should drift in -Y
as Z decreases (gravity in virtual space = (0, -1, -1)).

If supports are perpendicular to the slicing plane, support Y stays constant
across all Z layers → WRONG.
If supports follow gravity, support Y decreases as Z decreases → CORRECT.
"""
import sys, re
from collections import defaultdict

def analyze(path):
    layer_z = None
    in_support = False
    layer_num = 0

    # Track Y ranges per layer, separately for support and object
    support_y_per_layer = defaultdict(list)
    object_y_per_layer = defaultdict(list)

    with open(path) as f:
        for line in f:
            line = line.strip()

            # Track layer changes
            if line == ';LAYER_CHANGE':
                layer_num += 1

            # Track Z changes
            m = re.match(r';Z:([\d.]+)', line)
            if m:
                layer_z = float(m.group(1))

            # Detect support vs object regions
            if line == ';TYPE:Support' or line == ';TYPE:Support interface':
                in_support = True
            elif line.startswith(';TYPE:'):
                in_support = False

            # Track Y coordinates of extrusion moves
            if layer_z is not None and 'E' in line and line.startswith('G1'):
                ym = re.search(r'Y([\d.]+)', line)
                if ym:
                    y = float(ym.group(1))
                    if in_support:
                        support_y_per_layer[layer_z].append(y)
                    else:
                        object_y_per_layer[layer_z].append(y)

    print(f"File: {path}")
    print(f"Total layers: {layer_num}")
    print(f"Layers with support: {len(support_y_per_layer)}")
    print(f"Layers with object: {len(object_y_per_layer)}")
    print()

    if not support_y_per_layer:
        print("NO SUPPORT FOUND IN G-CODE!")
        return

    # Sort by Z
    sorted_z = sorted(support_y_per_layer.keys())

    print(f"{'Layer Z':>10} | {'Supp Y min':>10} | {'Supp Y max':>10} | {'Supp Y mid':>10} | {'Obj Y mid':>10} | {'dY/layer':>10}")
    print("-" * 80)

    prev_y_mid = None
    y_mid_values = []
    z_values = []

    for i, z in enumerate(sorted_z):
        sy = support_y_per_layer[z]
        oy = object_y_per_layer.get(z, [])

        s_min, s_max = min(sy), max(sy)
        s_mid = (s_min + s_max) / 2
        o_mid = (min(oy) + max(oy)) / 2 if oy else float('nan')

        delta = s_mid - prev_y_mid if prev_y_mid is not None else 0
        prev_y_mid = s_mid

        y_mid_values.append(s_mid)
        z_values.append(z)

        # Print every 5th layer + first + last
        if i == 0 or i == len(sorted_z)-1 or i % 5 == 0:
            print(f"{z:10.3f} | {s_min:10.3f} | {s_max:10.3f} | {s_mid:10.3f} | {o_mid:10.3f} | {delta:+10.3f}")

    print()

    # Analyze drift
    if len(y_mid_values) >= 2:
        total_y_drift = y_mid_values[-1] - y_mid_values[0]
        total_z_range = z_values[-1] - z_values[0]

        print(f"Support Z range: {z_values[0]:.3f} to {z_values[-1]:.3f} ({total_z_range:.3f} mm)")
        print(f"Support Y start: {y_mid_values[0]:.3f} mm")
        print(f"Support Y end:   {y_mid_values[-1]:.3f} mm")
        print(f"Total Y drift:   {total_y_drift:+.3f} mm")

        if abs(total_y_drift) < 0.5:
            print("\nVERDICT: SUPPORT IS PERPENDICULAR TO SLICING PLANE (Y nearly constant)")
            print("         → WRONG for belt! Support should drift ~1mm Y per 1mm Z for 45°.")
        else:
            ratio = total_y_drift / total_z_range if total_z_range > 0 else 0
            print(f"Y/Z ratio:       {ratio:+.3f} (expected ~-1.0 for 45° belt)")
            if -1.5 < ratio < -0.5:
                print("\nVERDICT: SUPPORT FOLLOWS GRAVITY ✓")
            else:
                print(f"\nVERDICT: UNEXPECTED RATIO (expected ~-1.0, got {ratio:.3f})")

    # Also check object Y range for reference
    if object_y_per_layer:
        all_obj_y = [y for ys in object_y_per_layer.values() for y in ys]
        all_sup_y = [y for ys in support_y_per_layer.values() for y in ys]
        print(f"\nObject Y range: {min(all_obj_y):.3f} to {max(all_obj_y):.3f}")
        print(f"Support Y range: {min(all_sup_y):.3f} to {max(all_sup_y):.3f}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: analyze_support_gcode.py <gcode_file>")
        sys.exit(1)
    analyze(sys.argv[1])
