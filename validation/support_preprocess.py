#!/usr/bin/env python3
"""
Support Pre-Processor: Standalone Compound Mesh Generator

Generates support geometry in pure Cartesian space (no belt awareness),
then fuses model + support into a single compound STL mesh.

The belt pipeline (placement -> trafo_centered -> oblique slice -> gcode)
receives the compound as a normal object and handles all 45-degree math.

Usage:
    python3 support_preprocess.py model.stl -o compound.stl
    python3 support_preprocess.py model.stl -c support.ini -o compound.stl
"""

import argparse
import configparser
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh


# ── Config ──────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "threshold_angle": 50.0,   # degrees - min overhang angle needing support
    "xy_gap": 0.35,            # mm - clearance between support and model
    "floor_z": 0.1,            # mm - support floor above Z=0
    "min_area": 1.0,           # mm² - skip tiny overhang faces
}


def load_config(config_path=None):
    """Load support parameters from INI file, falling back to defaults."""
    cfg = dict(DEFAULT_CONFIG)
    if config_path and Path(config_path).exists():
        parser = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
        parser.read(config_path)
        if "support" in parser:
            for key in cfg:
                if key in parser["support"]:
                    cfg[key] = float(parser["support"][key])
        print(f"Config loaded from {config_path}")
    else:
        print("Using default config")
    for k, v in cfg.items():
        print(f"  {k} = {v}")
    return cfg


# ── Overhang Detection ─────────────────────────────────────────────────────

def detect_overhangs(mesh, threshold_angle=50.0, floor_z=0.1, min_area=1.0):
    """
    Standard Cartesian overhang detection.

    A face needs support if:
      1. Its normal points downward enough: normal . [0,0,-1] > cos(90 - threshold)
      2. Its lowest vertex is above floor_z (not already on build plate)
      3. It belongs to a connected overhang region with total area >= min_area

    Connected-component area filtering ensures tessellated curved surfaces
    (e.g. spheres) are supported even when individual faces are small.

    Returns boolean mask over mesh.faces.
    """
    gravity = np.array([0.0, 0.0, -1.0])
    cos_thresh = np.cos(np.radians(90.0 - threshold_angle))

    normals = mesh.face_normals
    dots = normals @ gravity  # positive = face points downward

    # Per-face min Z
    face_verts = mesh.vertices[mesh.faces]  # (N, 3, 3)
    min_zs = face_verts[:, :, 2].min(axis=1)

    # Initial mask: angle + height check (no area filter yet)
    candidate = (dots >= cos_thresh) & (min_zs > floor_z)

    # Filter by connected-component area
    if min_area > 0 and candidate.any():
        mask = _filter_by_region_area(mesh, candidate, min_area)
    else:
        mask = candidate

    print(f"\nOverhang detection:")
    print(f"  Total faces: {len(mesh.faces)}")
    print(f"  Candidate faces (angle+height): {candidate.sum()}")
    print(f"  After region area filter (>= {min_area} mm²): {mask.sum()}")
    print(f"  Threshold angle: {threshold_angle}° (cos_thresh={cos_thresh:.4f})")
    print(f"  Floor Z: {floor_z} mm")

    return mask


def _filter_by_region_area(mesh, candidate_mask, min_area):
    """Filter overhang faces: keep only connected regions with total area >= min_area."""
    from scipy.sparse import lil_matrix
    from scipy.sparse.csgraph import connected_components

    candidate_indices = np.where(candidate_mask)[0]
    n = len(candidate_indices)
    if n == 0:
        return candidate_mask

    # Build adjacency among candidate faces (share an edge = share 2 vertices)
    idx_map = {fi: i for i, fi in enumerate(candidate_indices)}
    adj = lil_matrix((n, n), dtype=bool)

    # Use mesh face adjacency: two faces are adjacent if they share an edge
    face_adj = mesh.face_adjacency  # (M, 2) pairs of adjacent face indices
    for a, b in face_adj:
        if a in idx_map and b in idx_map:
            i, j = idx_map[a], idx_map[b]
            adj[i, j] = True
            adj[j, i] = True

    n_components, labels = connected_components(adj, directed=False)

    # Sum area per component
    areas = mesh.area_faces
    result_mask = np.copy(candidate_mask)
    for comp in range(n_components):
        comp_faces = candidate_indices[labels == comp]
        total_area = areas[comp_faces].sum()
        if total_area < min_area:
            result_mask[comp_faces] = False

    return result_mask


# ── Support Prism Generation ───────────────────────────────────────────────

def shrink_triangle(verts, gap):
    """Shrink a triangle toward its centroid by `gap` mm on each edge."""
    centroid = verts.mean(axis=0)
    directions = centroid - verts
    lengths = np.linalg.norm(directions, axis=1, keepdims=True)
    # Avoid division by zero for degenerate triangles
    lengths = np.maximum(lengths, 1e-10)
    normed = directions / lengths
    # Shrink by gap, but don't overshoot centroid
    shift = np.minimum(gap, lengths * 0.8)
    return verts + normed * shift


def create_prism(roof_verts, floor_z):
    """
    Create a watertight triangular prism from a roof triangle down to floor_z.

    Returns vertices (6, 3) and faces (8, 3):
      - 1 roof triangle (top)
      - 1 floor triangle (bottom)
      - 3 side quads (each split into 2 triangles)
    """
    # Ensure roof winding is CCW when viewed from above (normal points up)
    edge1 = roof_verts[1] - roof_verts[0]
    edge2 = roof_verts[2] - roof_verts[0]
    normal = np.cross(edge1, edge2)
    if normal[2] < 0:
        # Flip winding to make roof normal point up
        roof_verts = roof_verts[[0, 2, 1]]

    # Roof: v0, v1, v2  (original Z)
    # Floor: v3, v4, v5  (same XY, Z = floor_z)
    floor_verts = roof_verts.copy()
    floor_verts[:, 2] = floor_z

    vertices = np.vstack([roof_verts, floor_verts])  # (6, 3)

    # Faces with consistent outward-facing CCW winding
    faces = np.array([
        # Roof (top, normal up): v0 v1 v2
        [0, 1, 2],
        # Floor (bottom, normal down): v5 v4 v3
        [5, 4, 3],
        # Side 0-1: two tris forming quad (v0,v1,v4,v3)
        [0, 1, 4],
        [0, 4, 3],
        # Side 1-2: two tris forming quad (v1,v2,v5,v4)
        [1, 2, 5],
        [1, 5, 4],
        # Side 2-0: two tris forming quad (v2,v0,v3,v5)
        [2, 0, 3],
        [2, 3, 5],
    ], dtype=np.int64)

    return vertices, faces


def create_support_prisms(mesh, mask, xy_gap=0.35, floor_z=0.1):
    """
    Build support prisms from overhang faces down to build plate (Z=floor_z).

    Each overhang face generates one triangular prism:
      - Roof = overhang triangle, shrunk by xy_gap toward centroid
      - Floor = same XY footprint at Z=floor_z
    """
    overhang_indices = np.where(mask)[0]
    if len(overhang_indices) == 0:
        print("No overhang faces found — no support needed.")
        return None

    all_verts = []
    all_faces = []
    vert_offset = 0

    for fi in overhang_indices:
        tri_verts = mesh.vertices[mesh.faces[fi]]  # (3, 3)

        # Shrink roof triangle by xy_gap for clearance
        roof = shrink_triangle(tri_verts, xy_gap)

        # Skip degenerate triangles after shrinking
        edge1 = roof[1] - roof[0]
        edge2 = roof[2] - roof[0]
        area = 0.5 * np.linalg.norm(np.cross(edge1, edge2))
        if area < 0.01:  # skip tiny remnants
            continue

        verts, faces = create_prism(roof, floor_z)
        all_verts.append(verts)
        all_faces.append(faces + vert_offset)
        vert_offset += len(verts)

    if not all_verts:
        print("All overhang faces degenerate after shrinking — no support.")
        return None

    vertices = np.vstack(all_verts)
    faces = np.vstack(all_faces)

    support = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    support.fix_normals()
    print(f"\nSupport prisms:")
    print(f"  Prisms: {len(all_verts)}")
    print(f"  Vertices: {len(support.vertices)}")
    print(f"  Faces: {len(support.faces)}")
    print(f"  Volume: {support.volume:.2f} mm³")
    print(f"  Watertight: {support.is_watertight}")

    return support


# ── Boolean Operations & Compound Assembly ─────────────────────────────────

def make_compound(model_path, config):
    """
    Full pipeline: load -> detect -> prisms -> subtract -> union -> compound mesh.

    Returns the compound trimesh, or the original model if no support needed.
    """
    # 1. Load model
    print(f"Loading model: {model_path}")
    model = trimesh.load(model_path, force="mesh")
    print(f"  Vertices: {len(model.vertices)}")
    print(f"  Faces: {len(model.faces)}")
    print(f"  Bounds: {model.bounds}")
    print(f"  Volume: {model.volume:.2f} mm³")

    # 2. Detect overhangs
    overhang_mask = detect_overhangs(
        model,
        threshold_angle=config["threshold_angle"],
        floor_z=config["floor_z"],
        min_area=config["min_area"],
    )

    if not overhang_mask.any():
        print("\nNo overhangs detected — returning model as-is.")
        return model, None

    # 3. Create support prisms
    support_raw = create_support_prisms(
        model,
        overhang_mask,
        xy_gap=config["xy_gap"],
        floor_z=config["floor_z"],
    )

    if support_raw is None:
        return model, None

    # 4. Subtract model (with clearance) from support to avoid intersection
    print("\nBoolean: subtracting model from support...")
    try:
        support_clean = trimesh.boolean.difference(
            [support_raw, model], engine="manifold"
        )
        if support_clean is None or support_clean.is_empty:
            print("  Warning: boolean difference produced empty result, using raw support")
            support_clean = support_raw
        else:
            print(f"  Support after subtraction: {len(support_clean.faces)} faces, "
                  f"volume={support_clean.volume:.2f} mm³")
    except Exception as e:
        print(f"  Warning: boolean subtraction failed ({e}), using raw support")
        support_clean = support_raw

    # 5. Union model + support into compound
    print("\nBoolean: union model + support...")
    try:
        compound = trimesh.boolean.union(
            [model, support_clean], engine="manifold"
        )
        print(f"  Compound: {len(compound.vertices)} verts, {len(compound.faces)} faces, "
              f"volume={compound.volume:.2f} mm³")
    except Exception as e:
        print(f"  Warning: boolean union failed ({e}), concatenating meshes")
        compound = trimesh.util.concatenate([model, support_clean])
        print(f"  Concatenated: {len(compound.vertices)} verts, {len(compound.faces)} faces")

    return compound, support_clean


# ── Export ──────────────────────────────────────────────────────────────────

def export_mesh(mesh, output_path):
    """Export mesh as STL or 3MF based on extension. Pure geometry, no printer settings."""
    output_path = str(output_path)
    if output_path.lower().endswith(".3mf"):
        _export_3mf(mesh, output_path)
    else:
        mesh.export(output_path, file_type="stl")
    size_kb = Path(output_path).stat().st_size / 1024
    print(f"\nExported: {output_path} ({size_kb:.1f} KB)")


def _export_3mf(mesh, output_path):
    """
    Write a minimal, standards-compliant 3MF.

    Contains ONLY geometry — no printer profiles, no slicer settings,
    no thumbnails, no OrcaSlicer/BambuStudio metadata.
    Readable by any 3MF-compatible slicer or viewer.
    """
    # Center XY at origin, Z base at 0
    centered = mesh.copy()
    bounds = centered.bounds
    cx = (bounds[0, 0] + bounds[1, 0]) / 2
    cy = (bounds[0, 1] + bounds[1, 1]) / 2
    centered.vertices[:, 0] -= cx
    centered.vertices[:, 1] -= cy
    centered.vertices[:, 2] -= bounds[0, 2]

    # Mesh → 3MF XML
    vert_lines = "\n".join(
        f'     <vertex x="{v[0]:.6f}" y="{v[1]:.6f}" z="{v[2]:.6f}"/>'
        for v in centered.vertices
    )
    tri_lines = "\n".join(
        f'     <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>'
        for f in centered.faces
    )

    model_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US"
       xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <resources>
  <object id="1" type="model">
   <mesh>
    <vertices>
{vert_lines}
    </vertices>
    <triangles>
{tri_lines}
    </triangles>
   </mesh>
  </object>
 </resources>
 <build>
  <item objectid="1"/>
 </build>
</model>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
</Types>'''

    rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0"
  Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>'''

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("3D/3dmodel.model", model_xml)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate support geometry and fuse with model into compound STL."
    )
    parser.add_argument("model", help="Input model STL file")
    parser.add_argument("-o", "--output", default=None,
                        help="Output file (.stl or .3mf). 3MF output is pure geometry,"
                             " no printer settings. (default: <model>_compound.stl)")
    parser.add_argument("-c", "--config", default=None,
                        help="Support config INI file (default: built-in defaults)")
    parser.add_argument("--support-only", action="store_true",
                        help="Export only the support mesh (no model)")
    parser.add_argument("--no-subtract", action="store_true",
                        help="Skip boolean subtraction (faster, may have intersections)")
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Error: {model_path} not found", file=sys.stderr)
        sys.exit(1)

    # Default output name
    if args.output is None:
        args.output = str(model_path.stem) + "_compound.stl"

    # Load config
    config = load_config(args.config)

    # Generate compound
    compound, support = make_compound(str(model_path), config)

    # Export
    if args.support_only:
        if support is not None:
            export_mesh(support, args.output)
        else:
            print("No support generated — nothing to export.")
            sys.exit(1)
    else:
        export_mesh(compound, args.output)

    print("\nDone.")


if __name__ == "__main__":
    main()
