#!/usr/bin/env python3
"""
calib_temp_belt_v5 — final merged-mesh single-object 3MF.

Takes the 9-instance combined 3MF (text as positive parts at correct world
positions) and re-exports as a SINGLE OBJECT 3MF (concatenated meshes, no
boolean.difference — text appears as positive bump, not cut).

Single object → single keel-align in slicer → Z_gcode expanded correctly
across 9 zones (~280mm). Multi-instance bug (collapse) avoided.

Embed M104 boundaries via custom_gcode_per_layer.xml so the slicer emits
temperature changes at slice time (Orca reads `Metadata/custom_gcode_per_layer.xml`).

Output: /tmp/calib_temp_belt_v6/calib_temp_belt_v5.3mf
Also SCP'd to behemoth at /home/user/orca-belt-local/validation/.
"""
from __future__ import annotations

import json, re, shutil, subprocess, sys, zipfile
from pathlib import Path
import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = Path("/tmp/calib_temp_belt_v6")
SRC_3MF = OUT_DIR / "calib_temp_belt_v6.3mf"  # 9-instance combined
OUT_3MF = OUT_DIR / "calib_temp_belt_v5.3mf"

TEMPS = [230, 225, 220, 215, 210, 205, 200, 195, 190]
T_WEDGE = 220
LAYER_HEIGHT = 0.283
WEDGE_LAYERS = 31


def main() -> int:
    print(f"=== calib_temp_belt v5 — merged-mesh + M104 events ===")
    if not SRC_3MF.exists():
        print(f"ERROR: source 9-instance 3MF missing at {SRC_3MF}")
        return 1

    print(f"[1/4] Loading + flattening to single merged mesh...")
    scene = trimesh.load(str(SRC_3MF))
    geoms = []
    instance_zg_ranges = []

    if hasattr(scene, "geometry") and len(scene.geometry) > 0:
        # Group by Y_world center: identify 9 instance pairs
        baked = []
        for name in scene.geometry.keys():
            m = scene.geometry[name].copy()
            try:
                T = scene.graph.get(name)
                m.apply_transform(T[0] if isinstance(T, tuple) else T)
            except Exception:
                pass
            baked.append(m)
        # Concatenate everything as positive meshes
        merged = trimesh.util.concatenate(baked)
        # Compute per-instance Z_gcode ranges from Y_world centers
        ys = [m.bounds.mean(axis=0)[1] for m in baked]
        sorted_idxs = sorted(range(len(baked)), key=lambda i: ys[i])
        # group every 2 adjacent (part1 + part2)
        groups = [sorted_idxs[i:i+2] for i in range(0, len(sorted_idxs), 2)]
        for grp in groups:
            group_meshes = [baked[i] for i in grp]
            verts = np.vstack([m.vertices for m in group_meshes])
            yz = verts[:, 1] + verts[:, 2]
            instance_zg_ranges.append((float(yz.min()), float(yz.max())))
    else:
        merged = scene.to_geometry()

    print(f"  Merged: {len(merged.vertices)} verts, {len(merged.faces)} faces")
    mb = merged.bounds
    print(f"  Bounds: X=[{mb[0,0]:.2f},{mb[1,0]:.2f}] Y=[{mb[0,1]:.2f},{mb[1,1]:.2f}] Z=[{mb[0,2]:.2f},{mb[1,2]:.2f}]")
    yz_total = merged.vertices[:, 1] + merged.vertices[:, 2]
    print(f"  Z_gcode total: [{yz_total.min():.2f}, {yz_total.max():.2f}]mm")
    print(f"  Per-instance Z_gcode ranges:")
    for i, (zg_min, zg_max) in enumerate(instance_zg_ranges):
        print(f"    inst{i} T={TEMPS[i]}°C: [{zg_min:.2f}, {zg_max:.2f}]mm")

    print(f"\n[2/4] Writing merged 3MF...")
    merged.export(str(OUT_3MF), file_type="3mf")
    print(f"  {OUT_3MF} ({OUT_3MF.stat().st_size} bytes)")

    print(f"\n[3/4] Embedding custom_gcode_per_layer.xml with M104 events...")
    wedge_zg_local = WEDGE_LAYERS * LAYER_HEIGHT
    boundaries = []
    for i, (zg_min, zg_max) in enumerate(instance_zg_ranges):
        wedge_start = zg_min
        tower_start = zg_min + wedge_zg_local
        if i > 0:
            boundaries.append((wedge_start, T_WEDGE, f"inst{i}-wedge"))
        boundaries.append((tower_start, TEMPS[i], f"inst{i}-tower-T{TEMPS[i]}"))
    boundaries.sort(key=lambda x: x[0])

    items_xml = "\n  ".join(
        f'<layer top_z="{zg:.4f}" type="4" extruder="1" color="" '
        f'extra="M104 S{T} ; {tag}" gcode="M104 S{T} ; {tag}"/>'
        for zg, T, tag in boundaries
    )
    cgcode_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<custom_gcodes_per_layer>
 <plate>
  <plate_info id="1"/>
  {items_xml}
  <mode value="SingleExtruder"/>
 </plate>
</custom_gcodes_per_layer>'''

    tmp = OUT_3MF.with_suffix(".tmp.3mf")
    with zipfile.ZipFile(OUT_3MF, "r") as zin, zipfile.ZipFile(
        tmp, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.namelist():
            if item == "Metadata/custom_gcode_per_layer.xml":
                continue
            zout.writestr(item, zin.read(item))
        zout.writestr("Metadata/custom_gcode_per_layer.xml", cgcode_xml)
    tmp.replace(OUT_3MF)

    print(f"  {len(boundaries)} M104 events embedded:")
    for zg, T, tag in boundaries:
        print(f"    Z_gcode ≥ {zg:6.2f}mm → M104 S{T}  ({tag})")

    print(f"\n[4/4] SCP to behemoth for GUI slicing...")
    remote = "/home/user/orca-belt-local/validation/calib_temp_belt_v5.3mf"
    subprocess.run(
        ["sshpass", "-p", "<PASSWORD>", "scp", "-o", "StrictHostKeyChecking=no",
         str(OUT_3MF), f"user@<WORKSTATION_HOST>:{remote}"],
        check=True, capture_output=True,
    )
    print(f"  → behemoth:{remote}")

    print(f"\n=== Done ===")
    print(f"Open in OrcaBelt GUI on behemoth, slice, send to printer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
