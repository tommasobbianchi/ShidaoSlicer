#!/usr/bin/env python3
"""
analyze_support_trimesh.py — Analyze belt support geometry via G-code parsing + trimesh.

Parses G-code, extracts support extrusion paths, reconstructs them as 3D geometry,
and evaluates correctness for belt printer support placement.

Usage:
    python3 validation/analyze_support_trimesh.py [gcode_file] [--verbose]
"""

import trimesh
import numpy as np
import re
import sys
import os
import json


def parse_gcode_support(gcode_path):
    """Parse G-code and extract support extrusion segments as (x,y,z,e) tuples."""
    segments = []  # list of (x0,y0,z0, x1,y1,z1) for support moves
    model_segments = []

    x, y, z, e = 0.0, 0.0, 0.0, 0.0
    in_support = False
    in_model = False
    current_type = None

    with open(gcode_path) as f:
        for line in f:
            line = line.strip()

            # Track section type
            if line.startswith(";TYPE:"):
                current_type = line[6:].strip()
                in_support = "support" in current_type.lower() or "Support" in current_type
                in_model = not in_support and current_type in [
                    "Outer wall", "Inner wall", "Solid infill", "Internal infill",
                    "Top surface", "Bottom surface", "Bridge", "Overhang wall",
                    "Sparse infill"
                ]
                continue

            if not line.startswith("G1 ") and not line.startswith("G0 "):
                continue

            # Parse G1/G0 move
            nx, ny, nz, ne = x, y, z, e
            for part in line.split():
                if part.startswith("X"):
                    try: nx = float(part[1:])
                    except: pass
                elif part.startswith("Y"):
                    try: ny = float(part[1:])
                    except: pass
                elif part.startswith("Z"):
                    try: nz = float(part[1:])
                    except: pass
                elif part.startswith("E"):
                    try: ne = float(part[1:])
                    except: pass

            # Only record extrusion moves (E increases)
            if ne > e:
                if in_support:
                    segments.append((x, y, z, nx, ny, nz))
                elif in_model:
                    model_segments.append((x, y, z, nx, ny, nz))

            x, y, z, e = nx, ny, nz, ne

    return segments, model_segments


def segments_to_bounds(segments):
    """Convert list of (x0,y0,z0,x1,y1,z1) to per-Z-layer bounding info."""
    if not segments:
        return {}

    # Group by Z (rounded to 0.01mm)
    by_z = {}
    for x0, y0, z0, x1, y1, z1 in segments:
        zk = round(z1, 2)
        if zk not in by_z:
            by_z[zk] = {"x_min": 1e9, "x_max": -1e9,
                        "y_min": 1e9, "y_max": -1e9,
                        "n_moves": 0, "total_len": 0.0}
        d = by_z[zk]
        d["x_min"] = min(d["x_min"], x0, x1)
        d["x_max"] = max(d["x_max"], x0, x1)
        d["y_min"] = min(d["y_min"], y0, y1)
        d["y_max"] = max(d["y_max"], y0, y1)
        d["n_moves"] += 1
        d["total_len"] += np.sqrt((x1-x0)**2 + (y1-y0)**2 + (z1-z0)**2)

    return by_z


def analyze_belt_support(gcode_path, belt_angle_deg=45, verbose=False):
    """Full analysis of belt support geometry from G-code."""

    print(f"Parsing: {os.path.basename(gcode_path)}")
    sup_segs, mod_segs = parse_gcode_support(gcode_path)
    print(f"  Support segments: {len(sup_segs)}")
    print(f"  Model segments:   {len(mod_segs)}")

    if not sup_segs:
        print("  NO SUPPORT FOUND")
        return {"result": "NO_SUPPORT"}

    # Convert to numpy arrays for analysis
    sup_arr = np.array(sup_segs)  # shape (N, 6)
    mod_arr = np.array(mod_segs) if mod_segs else np.empty((0, 6))

    # --- Global support bounds ---
    all_sup_pts = np.vstack([sup_arr[:, :3], sup_arr[:, 3:]])
    sup_bounds = {
        "x": (float(all_sup_pts[:, 0].min()), float(all_sup_pts[:, 0].max())),
        "y": (float(all_sup_pts[:, 1].min()), float(all_sup_pts[:, 1].max())),
        "z": (float(all_sup_pts[:, 2].min()), float(all_sup_pts[:, 2].max())),
    }
    print(f"\n  Support bounds:")
    print(f"    X: [{sup_bounds['x'][0]:.2f}, {sup_bounds['x'][1]:.2f}]")
    print(f"    Y: [{sup_bounds['y'][0]:.2f}, {sup_bounds['y'][1]:.2f}]")
    print(f"    Z: [{sup_bounds['z'][0]:.2f}, {sup_bounds['z'][1]:.2f}]")

    # --- Global model bounds ---
    if len(mod_arr) > 0:
        all_mod_pts = np.vstack([mod_arr[:, :3], mod_arr[:, 3:]])
        mod_bounds = {
            "x": (float(all_mod_pts[:, 0].min()), float(all_mod_pts[:, 0].max())),
            "y": (float(all_mod_pts[:, 1].min()), float(all_mod_pts[:, 1].max())),
            "z": (float(all_mod_pts[:, 2].min()), float(all_mod_pts[:, 2].max())),
        }
        print(f"\n  Model bounds:")
        print(f"    X: [{mod_bounds['x'][0]:.2f}, {mod_bounds['x'][1]:.2f}]")
        print(f"    Y: [{mod_bounds['y'][0]:.2f}, {mod_bounds['y'][1]:.2f}]")
        print(f"    Z: [{mod_bounds['z'][0]:.2f}, {mod_bounds['z'][1]:.2f}]")
    else:
        mod_bounds = None

    # --- Per-layer analysis ---
    sup_by_z = segments_to_bounds(sup_segs)
    mod_by_z = segments_to_bounds(mod_segs)

    z_levels = sorted(sup_by_z.keys())
    print(f"\n  Support at {len(z_levels)} Z levels")
    print(f"  Z range: [{z_levels[0]:.2f}, {z_levels[-1]:.2f}]")

    # --- Key checks ---
    checks = {}

    # C1: Support exists
    checks["support_exists"] = len(sup_segs) > 0

    # C2: Support reaches belt surface (Z near 0 or Y near 0)
    # In machine coords, belt is at Z=const (each layer). Y=0 is belt edge.
    checks["reaches_belt_y"] = sup_bounds["y"][0] < 1.0

    # C3: Support below model at each Z level
    below_count = 0
    total_shared = 0
    above_model_layers = []
    for zk in z_levels:
        sd = sup_by_z[zk]
        if zk in mod_by_z:
            md = mod_by_z[zk]
            total_shared += 1
            if sd["y_max"] <= md["y_min"] + 1.0:
                below_count += 1
            elif sd["y_max"] > md["y_max"] + 1.0:
                above_model_layers.append(zk)

    if total_shared > 0:
        below_ratio = below_count / total_shared
        checks["support_below_model"] = below_ratio > 0.7
        checks["below_ratio"] = below_ratio
    else:
        checks["support_below_model"] = False
        checks["below_ratio"] = 0

    # C4: No side wedge (support extending ABOVE model at non-arm layers)
    # The "side wedge" is support where sup_y_max > mod_y_max (support above model)
    checks["above_model_layer_count"] = len(above_model_layers)
    checks["no_side_wedge"] = len(above_model_layers) == 0

    # C5: Support Y span grows monotonically
    y_spans = []
    for zk in z_levels:
        sd = sup_by_z[zk]
        y_spans.append(sd["y_max"] - sd["y_min"])
    if len(y_spans) > 2:
        violations = sum(1 for i in range(1, len(y_spans))
                        if y_spans[i] < y_spans[i-1] * 0.90)
        checks["monotonic"] = violations <= len(y_spans) * 0.15
        checks["monotonic_violations"] = violations
    else:
        checks["monotonic"] = True
        checks["monotonic_violations"] = 0

    # C6: Z monotonic (no reversals)
    z_arr = np.array(z_levels)
    z_diffs = np.diff(z_arr)
    checks["z_monotonic"] = bool(np.all(z_diffs >= -0.01))

    # --- Print results ---
    print("\n  === CHECKS ===")
    all_pass = True
    for name, val in checks.items():
        if isinstance(val, bool):
            status = "PASS" if val else "FAIL"
            print(f"    [{status}] {name}")
            if not val:
                all_pass = False
        elif isinstance(val, (int, float)):
            print(f"    [{name}] = {val}")

    if above_model_layers and verbose:
        print(f"\n  Above-model layers ({len(above_model_layers)}):")
        for zk in above_model_layers[:10]:
            sd = sup_by_z[zk]
            md = mod_by_z.get(zk)
            if md:
                print(f"    Z={zk:.2f}: sup_y=[{sd['y_min']:.2f},{sd['y_max']:.2f}]"
                      f" mod_y=[{md['y_min']:.2f},{md['y_max']:.2f}]")

    # --- Per-layer detail (verbose) ---
    if verbose:
        print("\n  === PER-LAYER DETAIL ===")
        for zk in z_levels:
            sd = sup_by_z[zk]
            md = mod_by_z.get(zk)
            mod_str = ""
            if md:
                mod_str = f" mod_y=[{md['y_min']:.2f},{md['y_max']:.2f}]"
            print(f"    Z={zk:7.2f}: sup_y=[{sd['y_min']:.2f},{sd['y_max']:.2f}]"
                  f" moves={sd['n_moves']:3d} len={sd['total_len']:.1f}{mod_str}")

    result = "ALL_PASS" if all_pass else "ISSUES"
    print(f"\n  RESULT: {result}")
    return {"result": result, "checks": checks, "sup_bounds": sup_bounds,
            "n_support_layers": len(z_levels)}


if __name__ == "__main__":
    gcode = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") \
            else "/tmp/plate_1.gcode"
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    analyze_belt_support(gcode, verbose=verbose)
