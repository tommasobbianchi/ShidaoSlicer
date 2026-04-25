#!/usr/bin/env python3
"""
Belt Z-Monotonic Path Validator
Checks that Z values (= belt position) are mostly increasing within each layer,
meaning the belt advances forward rather than oscillating back and forth.
"""
import re
import sys
from pathlib import Path

def analyze_z_monotonicity(gcode_file: str):
    """Analyze Z-monotonicity within each layer of belt printer gcode."""

    layers = []       # list of (layer_z, moves) where moves = [(z, line_num, is_extrusion), ...]
    current_layer_z = None
    current_moves = []
    current_z = 0.0

    with open(gcode_file) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Detect layer changes
            m = re.match(r';LAYER_CHANGE', line)
            if m:
                if current_moves:
                    layers.append((current_layer_z, current_moves))
                current_moves = []
                continue

            m = re.match(r';Z:([\d.]+)', line)
            if m:
                current_layer_z = float(m.group(1))
                continue

            # Parse G0/G1 moves
            if not (line.startswith('G0') or line.startswith('G1')):
                continue

            z_match = re.search(r'Z([-\d.]+)', line)
            e_match = re.search(r'E([-\d.]+)', line)

            if z_match:
                current_z = float(z_match.group(1))
                is_extrusion = e_match is not None
                current_moves.append((current_z, line_num, is_extrusion))

    # Don't forget last layer
    if current_moves:
        layers.append((current_layer_z, current_moves))

    print(f"Analyzed {len(layers)} layers from {gcode_file}\n")

    total_reversals = 0
    total_extrusion_reversals = 0
    total_reversal_distance = 0.0
    total_moves = 0

    for layer_idx, (layer_z, moves) in enumerate(layers):
        if len(moves) < 2:
            continue

        reversals = 0
        extrusion_reversals = 0
        reversal_dist = 0.0
        max_swing = 0.0

        for i in range(1, len(moves)):
            dz = moves[i][0] - moves[i-1][0]
            if dz < -0.01:  # Z went backward (belt reversed)
                reversals += 1
                rev_dist = abs(dz)
                reversal_dist += rev_dist
                max_swing = max(max_swing, rev_dist)
                if moves[i][2]:  # extrusion move reversed
                    extrusion_reversals += 1

        total_reversals += reversals
        total_extrusion_reversals += extrusion_reversals
        total_reversal_distance += reversal_dist
        total_moves += len(moves)

        # Print per-layer details for layers with significant reversals
        if reversals > 0 and layer_idx < 5:  # Show first 5 layers with issues
            lz_str = f"{layer_z:.3f}" if layer_z is not None else "?"
            print(f"  Layer {layer_idx} (Z={lz_str}): {len(moves)} moves, "
                  f"{reversals} reversals ({extrusion_reversals} during extrusion), "
                  f"max swing: {max_swing:.3f}mm, total reversal: {reversal_dist:.3f}mm")

    # Summary
    print(f"\n{'='*60}")
    print(f"Z-MONOTONICITY SUMMARY")
    print(f"{'='*60}")
    print(f"Total layers:              {len(layers)}")
    print(f"Total Z-moves:             {total_moves}")
    print(f"Total belt reversals:      {total_reversals}")
    print(f"  During extrusion:        {total_extrusion_reversals}")
    print(f"  During travel:           {total_reversals - total_extrusion_reversals}")
    print(f"Total reversal distance:   {total_reversal_distance:.2f}mm")
    if total_moves > 0:
        print(f"Reversal rate:             {total_reversals/total_moves*100:.1f}% of Z-moves")

    # Show a sample of the first layer's Z values to illustrate the pattern
    if layers:
        sample_layer = None
        for lz, moves in layers:
            if len(moves) > 5:
                sample_layer = (lz, moves)
                break
        if sample_layer:
            lz, moves = sample_layer
            print(f"\nFirst non-trivial layer Z sequence (layer Z={lz:.3f}):")
            for z, ln, ext in moves[:20]:
                marker = "E" if ext else "T"
                print(f"  line {ln:5d}: Z={z:8.3f} [{marker}]")
            if len(moves) > 20:
                print(f"  ... ({len(moves) - 20} more moves)")

    print(f"\n{'='*60}")
    if total_extrusion_reversals == 0:
        print("PASS: No belt reversals during extrusion")
    elif total_reversal_distance < 5.0:
        print(f"ACCEPTABLE: Minor reversals ({total_reversal_distance:.1f}mm total)")
    else:
        print(f"WARN: Significant belt reversals ({total_reversal_distance:.1f}mm total)")
    print(f"{'='*60}")

    return total_extrusion_reversals

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <gcode_file>")
        sys.exit(1)

    gcode = sys.argv[1]
    if not Path(gcode).exists():
        print(f"File not found: {gcode}")
        sys.exit(1)

    reversals = analyze_z_monotonicity(gcode)
    sys.exit(0 if reversals == 0 else 1)
