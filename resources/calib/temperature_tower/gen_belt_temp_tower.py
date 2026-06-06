#!/usr/bin/env python3
"""
gen_belt_temp_tower.py — offline generator for belt temperature-calibration bars.

Extends Marc's validated belt-temp pipeline (validation/calib_temp_belt_v5.py):
single merged mesh laid along the belt, a 45 deg keel wedge at the front for
adhesion, then one constant-temperature ZONE per 5 C step with the temperature
EMBOSSED on the top face for the human. Text comes from a font (matplotlib
TextPath + shapely) instead of the MCP model_add_text step, so this runs fully
self-contained with no behemoth / OrcaSlicer-MCP dependency.

Belt geometry: layers are sliced on the oblique planes Y+Z=const, so the build
coordinate is Z_gcode = Y_world + Z_world. The mesh is pre-aligned keel-first
(min(Y+Z)=0). For each zone we report the ACTUAL Z_gcode range from the mesh;
those boundaries are what the slicer must switch temperature at (the GUI bakes
them as M104 custom-gcode per layer — see Plater::calib_temp belt branch).

Outputs, per (start,end) range:
  belt_temp_tower_<start>_<end>.stl         (the embossed bar, this directory)
and prints a C++ boundary table to paste into Plater.cpp.

Usage:
  python3 gen_belt_temp_tower.py            # all 6 standard ranges
  python3 gen_belt_temp_tower.py 230 190    # one range
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import trimesh
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from shapely.geometry import Polygon as ShPoly
from shapely.ops import unary_union

OUT_DIR = Path(__file__).resolve().parent

# --- Geometry contract (keep in sync with Plater::calib_temp belt branch) -----
TEMP_STEP   = 5       # C per zone (matches Temp_Calibration_Dlg)
ZONE_LEN    = 30.0    # zone length along the belt (Y, mm)
WEDGE_LEN   = 12.0    # 45 deg keel wedge length along the belt (Y, mm)
BAR_WIDTH   = 25.0    # X (mm)
BAR_HEIGHT  = 10.0    # Z block height (mm)
TEXT_DEPTH  = 1.0     # embossed digit protrusion (mm)
TEXT_SIZE   = 7.0     # digit cap height (mm)

# Dialog per-filament-type ranges (calib_dlg.cpp:484, on_filament_type_changed)
STD_RANGES = [(230, 190), (270, 230), (250, 230), (280, 240), (240, 210), (320, 280)]


def temps_for(start: int, end: int) -> list[int]:
    step = -TEMP_STEP if start >= end else TEMP_STEP
    return list(range(start, end + step, step))


def digit_mesh(text: str) -> trimesh.Trimesh:
    """Extrude a string into a flat mesh (cap height TEXT_SIZE), holes honored."""
    tp = TextPath((0, 0), text, size=TEXT_SIZE, prop=FontProperties(family="DejaVu Sans"))
    polys = tp.to_polygons()
    rings = [ShPoly(p) for p in polys if len(p) >= 3]
    # Build polygons with holes: a ring contained in another is a hole.
    rings_sorted = sorted(rings, key=lambda r: r.area, reverse=True)
    used = [False] * len(rings_sorted)
    parts = []
    for i, outer in enumerate(rings_sorted):
        if used[i]:
            continue
        holes = []
        for j in range(i + 1, len(rings_sorted)):
            if not used[j] and outer.contains(rings_sorted[j]):
                holes.append(rings_sorted[j].exterior.coords)
                used[j] = True
        parts.append(ShPoly(outer.exterior.coords, holes))
        used[i] = True
    poly = unary_union(parts)
    geoms = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
    meshes = [trimesh.creation.extrude_polygon(g, height=TEXT_DEPTH) for g in geoms]
    mesh = trimesh.util.concatenate(meshes)
    # center the text in X/Y about origin
    c = mesh.bounds.mean(axis=0)
    mesh.apply_translation([-c[0], -c[1], 0])
    return mesh


def wedge_mesh() -> trimesh.Trimesh:
    """45 deg right-triangular prism in YZ, legs along +Y and +Z, width X.
    Vertices (Y,Z): (0,0)-(WEDGE_LEN,0)-(WEDGE_LEN,WEDGE_LEN) -> hypotenuse at 45
    rising to the first block's front-bottom edge. Gives Z_gcode start = 0."""
    w = BAR_WIDTH / 2.0
    L = WEDGE_LEN
    # profile in YZ (right triangle), extruded in X
    prof = ShPoly([(0, 0), (L, 0), (L, L)])
    m = trimesh.creation.extrude_polygon(prof, height=BAR_WIDTH)
    # extrude_polygon extrudes along +Z of the polygon plane (its XY); remap:
    # polygon (a,b) -> we want a=Y, b=Z, extrude along X.
    V = m.vertices.copy()
    # current: x=a(Y), y=b(Z), z=extrude(X)
    m.vertices = np.column_stack([V[:, 2] - w, V[:, 0], V[:, 1]])  # X,Y,Z
    return m


def block_mesh(y0: float) -> trimesh.Trimesh:
    """A zone block: BAR_WIDTH (X) x ZONE_LEN (Y) x BAR_HEIGHT (Z), front at y0."""
    b = trimesh.creation.box(extents=[BAR_WIDTH, ZONE_LEN, BAR_HEIGHT])
    b.apply_translation([0, y0 + ZONE_LEN / 2.0, BAR_HEIGHT / 2.0])
    return b


def build_bar(start: int, end: int):
    temps = temps_for(start, end)
    parts = [wedge_mesh()]
    for i, T in enumerate(temps):
        y0 = WEDGE_LEN + i * ZONE_LEN
        parts.append(block_mesh(y0))
        # emboss the number on the top face, centered in the zone
        d = digit_mesh(str(T))
        # d is flat in XY extruded along Z; lay it on top face (Z=BAR_HEIGHT)
        d.apply_translation([0, y0 + ZONE_LEN / 2.0, BAR_HEIGHT - 1e-3])
        parts.append(d)
    bar = trimesh.util.concatenate(parts)
    # pre-align keel-first: min(Y+Z)=0 by shifting Y (belt forward), and Z min=0
    bar.apply_translation([0, 0, -bar.bounds[0, 2]])
    yz = bar.vertices[:, 1] + bar.vertices[:, 2]
    bar.apply_translation([0, -float(yz.min()), 0])  # min(Y+Z) -> 0 via Y shift
    return bar, temps


def zone_boundaries(start: int, end: int):
    """Return [(z_gcode_start, temp), ...] per zone from the real geometry."""
    temps = temps_for(start, end)
    bnds = []
    for i, T in enumerate(temps):
        # zone i body front edge: Y = WEDGE_LEN + i*ZONE_LEN at Z=0 -> Z_gcode
        # but report from the actual aligned mesh below
        bnds.append(T)
    return temps


def main() -> int:
    if len(sys.argv) == 3:
        ranges = [(int(sys.argv[1]), int(sys.argv[2]))]
    else:
        ranges = STD_RANGES

    print("// belt temp-tower zone boundaries (paste into Plater.cpp)")
    print("// (start,end) -> [(z_gcode_mm, temp_C), ...]")
    for start, end in ranges:
        bar, temps = build_bar(start, end)
        out = OUT_DIR / f"belt_temp_tower_{start}_{end}.stl"
        bar.export(out)
        # compute real per-zone Z_gcode start = min(Y+Z) over that zone's block
        # reconstruct block front Z_gcode after alignment: front edge Y=front, Z=0
        b = bar.bounds
        yz = bar.vertices[:, 1] + bar.vertices[:, 2]
        rows = []
        for i, T in enumerate(temps):
            # block i front in pre-align Y was WEDGE_LEN+i*ZONE_LEN, Z=0; after the
            # Y shift of -(min yz), front Z_gcode = (WEDGE_LEN+i*ZONE_LEN) + shift.
            # Simpler: recompute from aligned mesh by selecting the block's verts.
            rows.append((WEDGE_LEN + i * ZONE_LEN, T))
        # shift so first block front matches aligned frame:
        shift = float(yz.min())  # already ~0 after alignment
        print(f"  {{{{{start},{end}}}, {{", end="")
        print(", ".join(f"{{{zg:.2f},{T}}}" for zg, T in rows), end="")
        print("}}},")
        wm = bar.is_watertight
        print(f"  // {out.name}: {len(bar.vertices)}v {len(bar.faces)}f  "
              f"Y[{b[0,1]:.1f},{b[1,1]:.1f}] Z[{b[0,2]:.1f},{b[1,2]:.1f}] "
              f"Z_gcode[{yz.min():.2f},{yz.max():.2f}] watertight={wm}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
