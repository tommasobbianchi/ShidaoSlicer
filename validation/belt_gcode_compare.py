#!/usr/bin/env python3
"""Compare belt printer gcode output against IdeaMaker reference.

Parses both gcodes and checks:
- Z constancy within each layer (should be ~0 std dev)
- Y range within each layer (should grow with layer number)
- Z increment between layers (should be ~0.283mm)
- No negative Y or Z values
- First layer Z position

Uses LAYER_CHANGE markers from OrcaSlicer gcode for reliable layer detection.
Filters out support/preamble layers to focus on object extrusion quality.
"""

import re
import sys
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LayerData:
    layer_idx: int = 0
    z_values: list = field(default_factory=list)
    y_values: list = field(default_factory=list)
    x_values: list = field(default_factory=list)
    z_travel: Optional[float] = None
    layer_type: str = ""  # "object", "support", "preamble", "unknown"
    extrusion_types: list = field(default_factory=list)


def parse_gcode(filepath: str) -> list[LayerData]:
    """Parse gcode and extract per-layer coordinate data.

    Uses ;LAYER_CHANGE markers when available (OrcaSlicer).
    Falls back to Z-change detection (IdeaMaker and others).
    """
    layers = []
    current_layer = LayerData()
    last_z = None
    last_x = None
    last_y = None
    has_layer_markers = False
    in_start_gcode = True
    current_type = ""

    with open(filepath) as f:
        lines = f.readlines()

    # Check if file uses LAYER_CHANGE markers
    for line in lines[:200]:
        if ';LAYER_CHANGE' in line:
            has_layer_markers = True
            break

    for line in lines:
        line = line.strip()

        # Track extrusion types
        if line.startswith(';TYPE:'):
            current_type = line[6:]
            if current_type != 'Custom':
                in_start_gcode = False

        # Layer detection via markers (OrcaSlicer format)
        if has_layer_markers and line == ';LAYER_CHANGE':
            if current_layer.z_values or current_layer.y_values:
                layers.append(current_layer)
            current_layer = LayerData(layer_idx=len(layers))
            current_type = ""
            continue

        # Skip pure comments
        if line.startswith(';'):
            continue

        # Skip non-G0/G1 commands
        m = re.match(r'^G([01])\s', line)
        if not m:
            # G92 resets (common in belt gcode)
            if line.startswith('G92'):
                if 'Z0' in line.replace(' ', '') or 'Z 0' in line:
                    last_z = 0.0
            continue

        x_m = re.search(r'X([-\d.]+)', line)
        y_m = re.search(r'Y([-\d.]+)', line)
        z_m = re.search(r'Z([-\d.]+)', line)
        e_m = re.search(r'E([-\d.]+)', line)

        x = float(x_m.group(1)) if x_m else last_x
        y = float(y_m.group(1)) if y_m else last_y
        z = float(z_m.group(1)) if z_m else last_z

        # For files without LAYER_CHANGE markers, detect layers by Z change
        if not has_layer_markers and z_m and z != last_z:
            if in_start_gcode:
                last_z = z
                last_x = x
                last_y = y
                continue
            if current_layer.z_values or current_layer.y_values:
                layers.append(current_layer)
            current_layer = LayerData(layer_idx=len(layers))
            current_layer.z_travel = z

        # Record Z travel moves
        if z_m and m.group(1) == '0':
            current_layer.z_travel = float(z_m.group(1))

        # Record coordinates during extrusion moves that actually move the nozzle.
        # Skip E-only moves (retract/unretract) — they don't extrude material at a position.
        has_position_change = x_m is not None or y_m is not None
        if e_m and has_position_change and x is not None and y is not None and z is not None:
            current_layer.x_values.append(x)
            current_layer.y_values.append(y)
            current_layer.z_values.append(z)
            if current_type and current_type not in current_layer.extrusion_types:
                current_layer.extrusion_types.append(current_type)

        last_x = x
        last_y = y
        if z is not None:
            last_z = z

    # Don't forget the last layer
    if current_layer.z_values or current_layer.y_values:
        layers.append(current_layer)

    # Classify layers
    for layer in layers:
        types = set(current_type.lower() for current_type in layer.extrusion_types)
        support_types = {'support', 'support interface', 'support material'}
        object_types = {'outer wall', 'inner wall', 'solid infill', 'sparse infill',
                       'top surface', 'bottom surface', 'overhang wall', 'bridge'}
        if types & object_types:
            layer.layer_type = "object"
        elif types & support_types:
            layer.layer_type = "support"
        elif not types:
            layer.layer_type = "preamble"
        else:
            layer.layer_type = "unknown"

    return layers


def filter_object_layers(layers: list[LayerData]) -> list[LayerData]:
    """Return only object layers (skip support, preamble, etc.)."""
    return [l for l in layers if l.layer_type == "object"]


def analyze_layers(layers: list[LayerData], label: str, show_all: bool = False) -> dict:
    """Analyze layers and return metrics."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Total layers: {len(layers)}")

    # Show type breakdown
    type_counts = {}
    for l in layers:
        t = l.layer_type or "raw"
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, c in sorted(type_counts.items()):
        print(f"    {t}: {c}")

    metrics = {
        'label': label,
        'num_layers': len(layers),
        'z_constancy_max_stddev': 0.0,
        'z_increments': [],
        'y_mins': [],
        'y_maxs': [],
        'neg_y_count': 0,
        'neg_z_count': 0,
        'first_layer_z': None,
    }

    if not layers:
        print("  NO LAYERS FOUND")
        return metrics

    prev_z_mean = None
    show_count = 10 if show_all else 10
    for i, layer in enumerate(layers[:show_count]):
        if not layer.z_values:
            continue

        z_vals = layer.z_values
        y_vals = layer.y_values
        x_vals = layer.x_values

        z_min = min(z_vals)
        z_max = max(z_vals)
        z_mean = sum(z_vals) / len(z_vals)
        z_stddev = math.sqrt(sum((z - z_mean)**2 for z in z_vals) / len(z_vals)) if len(z_vals) > 1 else 0

        y_min = min(y_vals) if y_vals else 0
        y_max = max(y_vals) if y_vals else 0
        x_min = min(x_vals) if x_vals else 0
        x_max = max(x_vals) if x_vals else 0

        z_inc = z_mean - prev_z_mean if prev_z_mean is not None else 0

        type_str = f" [{layer.layer_type}]" if layer.layer_type else ""
        print(f"\n  Layer {i}{type_str}:")
        print(f"    Z: mean={z_mean:.3f}  min={z_min:.3f}  max={z_max:.3f}  stddev={z_stddev:.4f}")
        print(f"    Y: min={y_min:.3f}  max={y_max:.3f}  range={y_max-y_min:.3f}")
        print(f"    X: min={x_min:.3f}  max={x_max:.3f}")
        if prev_z_mean is not None:
            print(f"    Z increment: {z_inc:.3f}")
        if layer.z_travel is not None:
            print(f"    Z travel (G0): {layer.z_travel:.3f}")

        metrics['z_constancy_max_stddev'] = max(metrics['z_constancy_max_stddev'], z_stddev)
        metrics['y_mins'].append(y_min)
        metrics['y_maxs'].append(y_max)
        if prev_z_mean is not None:
            metrics['z_increments'].append(z_inc)
        if i == 0:
            metrics['first_layer_z'] = z_mean

        prev_z_mean = z_mean

    # Count negatives across ALL layers
    for layer in layers:
        metrics['neg_y_count'] += sum(1 for y in layer.y_values if y < -0.001)
        metrics['neg_z_count'] += sum(1 for z in layer.z_values if z < -0.001)

    return metrics


def compare_metrics(ref: dict, test: dict) -> bool:
    """Compare test against reference metrics. Returns True if pass."""
    print(f"\n{'='*60}")
    print(f"  COMPARISON: {ref['label']} vs {test['label']}")
    print(f"{'='*60}")

    all_pass = True

    def check(name, condition, detail=""):
        nonlocal all_pass
        status = "PASS" if condition else "FAIL"
        if not condition:
            all_pass = False
        print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))

    # 1. Z constancy within layer
    check(
        "Z constant within layer",
        test['z_constancy_max_stddev'] < 0.001,
        f"max stddev = {test['z_constancy_max_stddev']:.4f} (ref: {ref['z_constancy_max_stddev']:.4f}, tol: <0.001)"
    )

    # 2. Z increment between layers (skip first increment which may differ due to first-layer height)
    if len(test['z_increments']) >= 2:
        steady_increments = test['z_increments'][1:]  # Skip first increment
        avg_inc = sum(steady_increments) / len(steady_increments)
        check(
            "Z increment ~0.283mm (steady state)",
            abs(avg_inc - 0.283) < 0.010,
            f"avg = {avg_inc:.3f} (target: 0.283, tol: ±0.010)"
        )
    elif test['z_increments']:
        avg_inc = test['z_increments'][0]
        check(
            "Z increment ~0.283mm",
            abs(avg_inc - 0.283) < 0.010,
            f"avg = {avg_inc:.3f} (target: 0.283, tol: ±0.010)"
        )

    # 3. First layer Z (allow wider tolerance — absolute offset depends on config)
    if test['first_layer_z'] is not None:
        check(
            "First layer Z positive",
            test['first_layer_z'] >= 0.0,
            f"value = {test['first_layer_z']:.3f} (must be >= 0)"
        )

    # 4. No negative coordinates
    check(
        "No negative Y values",
        test['neg_y_count'] == 0,
        f"count = {test['neg_y_count']}"
    )
    check(
        "No negative Z values",
        test['neg_z_count'] == 0,
        f"count = {test['neg_z_count']}"
    )

    # 5. Y_min small positive for first few object layers
    if test['y_mins']:
        check(
            "Y_min per layer >= 0",
            all(y >= -0.001 for y in test['y_mins']),
            f"first layer Y_min = {test['y_mins'][0]:.3f}"
        )

    # 6. Y_max grows with layers (check steady-state layers, skip first 2)
    if len(test['y_maxs']) >= 5:
        start = 2  # Skip first 2 layers which may have unusual ranges
        growing = all(test['y_maxs'][i+1] >= test['y_maxs'][i] - 0.05
                      for i in range(start, min(start+5, len(test['y_maxs'])-1)))
        check(
            "Y_max grows with layer number",
            growing,
            f"Y_maxs[{start}:{start+6}]: {[f'{v:.3f}' for v in test['y_maxs'][start:start+6]]}"
        )

    # 7. Y range varies within layers (not all zero — proves gantry traces cross-section)
    if len(test['y_mins']) >= 5 and len(test['y_maxs']) >= 5:
        has_y_variation = any(
            test['y_maxs'][i] - test['y_mins'][i] > 0.1
            for i in range(2, min(5, len(test['y_mins'])))
        )
        y_ranges = [f'{test["y_maxs"][i]-test["y_mins"][i]:.3f}' for i in range(min(5, len(test['y_mins'])))]
        check(
            "Y varies within layer (gantry traces cross-section)",
            has_y_variation,
            f"Y ranges: {y_ranges}"
        )

    # 8. Layer count reasonable
    if ref['num_layers'] > 0:
        ratio = test['num_layers'] / ref['num_layers']
        check(
            "Layer count reasonable",
            0.5 < ratio < 2.0,
            f"test={test['num_layers']}, ref={ref['num_layers']}, ratio={ratio:.2f}"
        )

    return all_pass


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <reference.gcode> <test.gcode>")
        sys.exit(1)

    ref_path = sys.argv[1]
    test_path = sys.argv[2]

    print(f"Reference: {ref_path}")
    print(f"Test:      {test_path}")

    ref_layers = parse_gcode(ref_path)
    test_layers = parse_gcode(test_path)

    # Analyze all layers (for overview)
    ref_metrics = analyze_layers(ref_layers, f"Reference ALL ({ref_path.split('/')[-1]})")
    test_metrics_all = analyze_layers(test_layers, f"Test ALL ({test_path.split('/')[-1]})")

    # Filter to object layers only for comparison
    ref_obj_layers = filter_object_layers(ref_layers) or ref_layers
    test_obj_layers = filter_object_layers(test_layers)

    if test_obj_layers:
        print(f"\n  Filtered to {len(test_obj_layers)} object layers (from {len(test_layers)} total)")
        test_metrics = analyze_layers(test_obj_layers, f"Test OBJECT layers ({test_path.split('/')[-1]})")
    else:
        print("\n  No object layers detected, using all layers")
        test_metrics = test_metrics_all

    ref_obj_metrics = analyze_layers(ref_obj_layers, f"Reference OBJECT layers ({ref_path.split('/')[-1]})")

    passed = compare_metrics(ref_obj_metrics, test_metrics)

    # Also report on all layers
    print(f"\n{'='*60}")
    print(f"  ALL LAYERS SUMMARY")
    print(f"{'='*60}")
    print(f"  Negative Y (all layers): {test_metrics_all['neg_y_count']}")
    print(f"  Negative Z (all layers): {test_metrics_all['neg_z_count']}")

    print(f"\n{'='*60}")
    if passed:
        print("  OVERALL: PASS")
    else:
        print("  OVERALL: FAIL")
    print(f"{'='*60}")

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
