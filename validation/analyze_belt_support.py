#!/usr/bin/env python3
"""Analyze belt support validation output.

Reads /tmp/belt_support_validation.txt written by _generate_support_material()
and produces a diagnostic report with PASS/FAIL checks.

Usage:
    python3 validation/analyze_belt_support.py [path_to_validation_file]
"""
import sys
import re
from pathlib import Path

DEFAULT_PATH = "/tmp/belt_support_validation.txt"

def parse_validation_file(path):
    """Parse the validation file into structured data."""
    data = {
        'header': {},
        'layers': [],
        'validation': {},
        'paths': [],
        'summary': {},
    }

    section = 'header'
    with open(path) as f:
        for line in f:
            line = line.rstrip()
            if not line:
                continue

            if '--- P1 OVERHANG ---' in line:
                section = 'p1'
                continue
            elif '--- P2 SUPPORT REGIONS ---' in line:
                section = 'p2'
                continue
            elif '--- VALIDATION ---' in line:
                section = 'validation'
                continue
            elif '--- P3 EXTRUSION PATHS' in line:
                section = 'paths'
                continue
            elif '--- SUMMARY ---' in line:
                section = 'summary'
                continue

            if section == 'header':
                if line.startswith('n_layers:'):
                    data['header']['n_layers'] = int(line.split(':')[1].strip())
                elif line.startswith('angle_deg:'):
                    parts = line.split()
                    data['header']['angle_deg'] = int(parts[1])
                    data['header']['gap_xy'] = float(parts[3])
                elif line.startswith('layer0_z:'):
                    parts = line.split()
                    data['header']['layer0_z'] = float(parts[1])
                    data['header']['layerN_z'] = float(parts[3])

            elif section == 'p1':
                m = re.search(r'oh_layers:\s+(\d+)/(\d+)', line)
                if m:
                    data['header']['oh_layers'] = int(m.group(1))
                m = re.search(r'oh_area:\s+([\d.]+)', line)
                if m:
                    data['header']['oh_area'] = float(m.group(1))

            elif section == 'p2':
                m = re.match(r'L(\d+)\s+z=([\d.]+)\s+area=([\d.]+)\s+nex=(\d+)\s+'
                             r'sup_bb=\[([-\d.]+),([-\d.]+)\]-\[([-\d.]+),([-\d.]+)\]\s+'
                             r'mod_bb=\[([-\d.]+),([-\d.]+)\]-\[([-\d.]+),([-\d.]+)\]', line)
                if m:
                    data['layers'].append({
                        'idx': int(m.group(1)),
                        'z': float(m.group(2)),
                        'area': float(m.group(3)),
                        'nex': int(m.group(4)),
                        'sup_bb': ((float(m.group(5)), float(m.group(6))),
                                   (float(m.group(7)), float(m.group(8)))),
                        'mod_bb': ((float(m.group(9)), float(m.group(10))),
                                   (float(m.group(11)), float(m.group(12)))),
                    })

            elif section == 'validation':
                m = re.search(r'wedge_ratio:\s+([\d.]+)\s+(\w+)', line)
                if m:
                    data['validation']['wedge_ratio'] = float(m.group(1))
                    data['validation']['wedge_pass'] = m.group(2) == 'PASS'

            elif section == 'paths':
                m = re.match(r'SL(\d+)\s+z=([\d.]+)\s+entities=(\d+)', line)
                if m:
                    data['paths'].append({
                        'sl_idx': int(m.group(1)),
                        'z': float(m.group(2)),
                        'entities': int(m.group(3)),
                    })
                m = re.match(r'\s+path\[0\]\s+pts=(\d+):(.*)', line)
                if m and data['paths']:
                    coords = re.findall(r'\(([-\d.]+),([-\d.]+)\)', m.group(2))
                    data['paths'][-1]['first_path_pts'] = int(m.group(1))
                    data['paths'][-1]['first_path_coords'] = [(float(x), float(y)) for x, y in coords]

            elif section == 'summary':
                for key in ['support_layers', 'layers_with_fills', 'total_entities']:
                    if line.startswith(key + ':'):
                        val = line.split(':')[1].strip().split()[0]
                        data['summary'][key] = int(val)
                if line.startswith('continuity:'):
                    data['summary']['continuity'] = 'PASS' in line
                if line.startswith('wedge:'):
                    data['summary']['wedge'] = 'PASS' in line
                if line.startswith('RESULT:'):
                    data['summary']['result'] = line.split(':')[1].strip()

    return data


def analyze(data):
    """Run diagnostic checks and print report."""
    layers = data['layers']
    header = data['header']
    summary = data['summary']

    print("=" * 60)
    print("BELT SUPPORT VALIDATION REPORT")
    print("=" * 60)

    print(f"\nConfig: angle={header.get('angle_deg')}° gap_xy={header.get('gap_xy')}mm")
    print(f"Layers: {header.get('n_layers')} total, {header.get('oh_layers')} with overhangs")
    print(f"Z range: {header.get('layer0_z'):.3f} — {header.get('layerN_z'):.3f}")

    if not layers:
        print("\n*** NO SUPPORT LAYERS — nothing to analyze ***")
        return

    # 1. Area profile
    print(f"\n--- Area Profile ({len(layers)} support layers) ---")
    areas = [l['area'] for l in layers]
    area_max = max(areas) if areas else 0
    area_first = areas[0] if areas else 0
    area_last = areas[-1] if areas else 0

    print(f"First layer (L{layers[0]['idx']}): area={area_first:.2f} mm²")
    print(f"Max area: {area_max:.2f} mm² (at L{layers[areas.index(area_max)]['idx']})")
    print(f"Last layer (L{layers[-1]['idx']}): area={area_last:.2f} mm²")

    # Wedge check
    wedge = area_first / area_max if area_max > 0 else 0
    print(f"\nWedge ratio (first/max): {wedge:.3f}", end="")
    if wedge > 0.5:
        print(" ✓ GOOD (>0.5)")
    elif wedge > 0.3:
        print(" ~ MARGINAL (0.3-0.5)")
    else:
        print(" ✗ BAD — thin wedge at base!")

    # 2. Bounding box alignment
    print("\n--- XY Alignment Check ---")
    misaligned = 0
    for l in layers:
        sb = l['sup_bb']
        mb = l['mod_bb']
        # Check X overlap
        x_overlap = min(sb[1][0], mb[1][0]) - max(sb[0][0], mb[0][0])
        if x_overlap < 0:
            misaligned += 1
            if misaligned <= 3:
                print(f"  L{l['idx']}: NO X overlap! sup_x=[{sb[0][0]:.1f},{sb[1][0]:.1f}]"
                      f" mod_x=[{mb[0][0]:.1f},{mb[1][0]:.1f}]")

    if misaligned == 0:
        print("All layers have X overlap with model ✓")
    else:
        print(f"{misaligned} layers with NO X overlap ✗")

    # 3. Area continuity
    print("\n--- Area Continuity ---")
    jumps = []
    for i in range(1, len(layers)):
        if layers[i]['idx'] - layers[i-1]['idx'] > 3:
            jumps.append((layers[i-1]['idx'], layers[i]['idx']))
    if jumps:
        print(f"GAPS detected: {jumps[:5]}")
    else:
        print("No gaps in support sequence ✓")

    # Area smoothness
    big_drops = []
    for i in range(1, len(layers)):
        if areas[i-1] > 0:
            ratio = areas[i] / areas[i-1]
            if ratio < 0.3 or ratio > 3.0:
                big_drops.append((layers[i]['idx'], ratio))
    if big_drops:
        print(f"Large area jumps: {big_drops[:5]}")
    else:
        print("Area changes smooth ✓")

    # 4. Extrusion path coordinates
    print("\n--- Extrusion Path Coordinates ---")
    for p in data.get('paths', []):
        coords = p.get('first_path_coords', [])
        print(f"SL{p['sl_idx']} z={p['z']:.3f}: {p['entities']} entities", end="")
        if coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            print(f"  path[0] X=[{min(xs):.1f},{max(xs):.1f}] Y=[{min(ys):.1f},{max(ys):.1f}]")
        else:
            print()

    # 5. Summary
    print("\n" + "=" * 60)
    result = summary.get('result', 'UNKNOWN')
    print(f"RESULT: {result}")
    if result != 'OK':
        print("Issues detected — check details above")
    print("=" * 60)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    if not Path(path).exists():
        print(f"Validation file not found: {path}")
        print("Run OrcaSlicer with belt support enabled, then re-run this script.")
        sys.exit(1)

    data = parse_validation_file(path)
    analyze(data)


if __name__ == '__main__':
    main()
