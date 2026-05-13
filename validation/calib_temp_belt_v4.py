#!/usr/bin/env python3
"""
calib_temp_belt_v4 — single merged mesh approach.

Reason: OrcaBelt's belt slicer auto-keel-aligns each instance individually,
collapsing multi-instance plates to a single Z_gcode range. So we build ONE
big mesh containing all 9 zones in sequence along Y_world, with text-cut
baked into each tower via trimesh.boolean.difference.

Output:
  /tmp/calib_temp_belt_v6/calib_temp_belt_merged.3mf  (the 3MF user slices)

M104 transitions embedded in Metadata/custom_gcode_per_layer.xml so they fire
at slice time without post-processing.

User instruction: slice in OrcaBelt GUI, M104 emit automatically per zone.
"""
from __future__ import annotations

import argparse, json, re, shutil, subprocess, sys, zipfile
from pathlib import Path
import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = Path("/tmp/calib_temp_belt_v6")
COMBINED_SRC = OUT_DIR / "calib_temp_belt_v6.3mf"  # produced by v3 script
MERGED_OUT = OUT_DIR / "calib_temp_belt_merged.3mf"

TEMPS = [230, 225, 220, 215, 210, 205, 200, 195, 190]
T_WEDGE = 220
GAP_MM = 5.0
LAYER_HEIGHT = 0.283
WEDGE_LAYERS = 31  # template's wedge spans 31 belt layers


def split_scene_by_instance(scene: trimesh.Scene) -> list[tuple[trimesh.Trimesh, trimesh.Trimesh]]:
    """Group the 18 sub-geoms into 9 (part1, part2) pairs by Y_world center.

    The combined 3MF has 9 Part1 (tower geom, ~600 faces) + 9 Part2 (text, ~700-1300 faces).
    Group by world Y_center proximity.
    """
    # Bake each sub-geom to world coords
    baked = []
    for name in scene.geometry.keys():
        # scene.dump returns transformed meshes by name when concatenate=False
        m = scene.geometry[name].copy()
        # Apply scene-graph transform
        try:
            T = scene.graph.get(name)
            transform = T[0] if isinstance(T, tuple) else T
            m.apply_transform(transform)
        except Exception:
            pass
        cy = float(m.bounds.mean(axis=0)[1])
        baked.append((cy, len(m.vertices), m, name))

    # Sort by Y center
    baked.sort(key=lambda x: x[0])

    # Group into pairs of similar Y center (within instance's Y extent ~25mm)
    pairs = []
    used = set()
    for i, (cy_i, nv_i, m_i, name_i) in enumerate(baked):
        if i in used:
            continue
        # Find nearest in Y within tolerance
        for j, (cy_j, nv_j, m_j, name_j) in enumerate(baked):
            if j <= i or j in used:
                continue
            if abs(cy_i - cy_j) < 15.0:  # same instance group
                # Assign bigger as part1, smaller as part2
                if nv_i >= nv_j:
                    pairs.append((m_i, m_j))
                else:
                    pairs.append((m_j, m_i))
                used.add(i)
                used.add(j)
                break
    if len(pairs) != 9:
        print(f"  WARN: expected 9 pairs, got {len(pairs)}")
    return pairs


def build_merged_mesh() -> tuple[trimesh.Trimesh, list[tuple[float, float]]]:
    """Load combined 3MF, do boolean.difference per pair, concatenate.

    Returns (merged_mesh, per_instance_zg_ranges) where each tuple is
    (z_gcode_min, z_gcode_max) for that instance in world coords.
    """
    print(f"  Loading {COMBINED_SRC}...")
    scene = trimesh.load(str(COMBINED_SRC))
    pairs = split_scene_by_instance(scene)
    print(f"  Grouped {len(pairs)} (part1, part2) pairs")

    instances_with_zg = []
    out_meshes = []
    for i, (part1, part2) in enumerate(pairs):
        T = TEMPS[i]
        # Boolean difference: subtract text from tower
        try:
            cut = part1.difference(part2)
        except Exception as e:
            print(f"  [{i}] T={T}: boolean.difference failed ({e}), falling back to concatenate")
            cut = trimesh.util.concatenate([part1, part2])
        # Compute Z_gcode range of this instance
        yz = cut.vertices[:, 1] + cut.vertices[:, 2]
        zg_min, zg_max = float(yz.min()), float(yz.max())
        instances_with_zg.append((zg_min, zg_max))
        out_meshes.append(cut)
        print(f"  [{i+1}/9] T={T}: cut mesh {len(cut.vertices)} verts, Z_gcode=[{zg_min:.2f}, {zg_max:.2f}]")

    merged = trimesh.util.concatenate(out_meshes)
    return merged, instances_with_zg


def write_merged_3mf(merged: trimesh.Trimesh, instances_zg: list[tuple[float, float]],
                    out_path: Path):
    """Export the merged mesh to 3MF and embed custom_gcode_per_layer.xml
    with M104 transitions per zone."""
    merged.export(str(out_path), file_type="3mf")

    # Compute M104 boundaries (per-instance: wedge_T at wedge_start, T_n at tower_start)
    wedge_zg_local = WEDGE_LAYERS * LAYER_HEIGHT  # 8.77mm wedge in Z_gcode within an instance
    boundaries = []  # list of (z_gcode, T_celsius, comment)
    for i, (zg_min, zg_max) in enumerate(instances_zg):
        wedge_start = zg_min
        tower_start = zg_min + wedge_zg_local
        # Wedge M104 (skip for i==0 since start_gcode sets initial)
        if i > 0:
            boundaries.append((wedge_start, T_WEDGE, f"inst{i}-wedge"))
        boundaries.append((tower_start, TEMPS[i], f"inst{i}-tower-T{TEMPS[i]}"))
    boundaries.sort(key=lambda x: x[0])

    # Build custom_gcode_per_layer.xml
    items_xml = []
    for zg, T, tag in boundaries:
        gc = f"M104 S{T} ; {tag}"
        items_xml.append(
            f'<layer top_z="{zg:.4f}" type="4" extruder="1" color="" '
            f'extra="{gc}" gcode="{gc}"/>'
        )
    items_str = "\n".join(items_xml)
    cgcode_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<custom_gcodes_per_layer>
 <plate>
  <plate_info id="1"/>
  {items_str}
  <mode value="SingleExtruder"/>
 </plate>
</custom_gcodes_per_layer>'''

    # Inject into the 3MF
    tmp = out_path.with_suffix(".tmp.3mf")
    with zipfile.ZipFile(out_path, "r") as zin, zipfile.ZipFile(
        tmp, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.namelist():
            zout.writestr(item, zin.read(item))
        zout.writestr("Metadata/custom_gcode_per_layer.xml", cgcode_xml)
    tmp.replace(out_path)

    return boundaries


def main() -> int:
    print(f"=== calib_temp_belt v4 — merged mesh + custom_gcode ===")
    if not COMBINED_SRC.exists():
        print(f"ERROR: combined 3MF missing at {COMBINED_SRC}")
        print(f"Run calib_temp_belt_v3.py first to generate the 9-instance combined.")
        return 1

    print(f"[1/3] Building merged mesh with boolean.difference per instance...")
    merged, instances_zg = build_merged_mesh()
    mb = merged.bounds
    print(f"  Merged: {len(merged.vertices)} verts, bounds X=[{mb[0,0]:.2f},{mb[1,0]:.2f}], "
          f"Y=[{mb[0,1]:.2f},{mb[1,1]:.2f}], Z=[{mb[0,2]:.2f},{mb[1,2]:.2f}]")
    yz = merged.vertices[:, 1] + merged.vertices[:, 2]
    print(f"  Z_gcode total: [{yz.min():.2f}, {yz.max():.2f}]")

    print(f"\n[2/3] Writing 3MF + embedded custom_gcode_per_layer.xml...")
    boundaries = write_merged_3mf(merged, instances_zg, MERGED_OUT)
    print(f"  M104 events ({len(boundaries)}):")
    for zg, T, tag in boundaries:
        print(f"    Z_gcode ≥ {zg:.2f}mm → M104 S{T}  ({tag})")

    print(f"\n[3/3] Output ready: {MERGED_OUT} ({MERGED_OUT.stat().st_size} bytes)")
    print(f"\nNext step: SCP to behemoth + load via OrcaBelt GUI → slice → upload to printer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
