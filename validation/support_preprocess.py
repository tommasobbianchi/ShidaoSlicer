#!/usr/bin/env python3
"""
Support Pre-Processor for Belt Printers

Generates support geometry in pure Cartesian XYZ space (no belt awareness).
The belt pipeline (trafo_centered → oblique slice → gcode) receives the geometry
and handles all 45° math. This script must not touch the belt transform pipeline.

Two modes:
  3MF mode (default): adds support as second normal_part volume in the same
                      OrcaSlicer composite object. Brim is disabled at object
                      level (belt keel at Y≈0 provides adhesion without brim).
  STL/compound mode:  fuses model+support into a single compound mesh (legacy).

Usage:
    python3 support_preprocess.py source.3mf -o out.3mf
    python3 support_preprocess.py source.3mf -c support.ini -o out.3mf
    python3 support_preprocess.py model.stl --compound -o compound.stl
"""

import argparse
import configparser
import re
import shutil
import sys
import uuid
import zipfile
from pathlib import Path

import numpy as np
import trimesh


# ── Config ───────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "threshold_angle": 50.0,   # degrees — min overhang angle needing support
    "xy_gap": 0.35,            # mm — XY clearance between support and model sides
    "z_gap": 0.15,             # mm — Z clearance between support top and model bottom
    "side_gap": 0.15,          # mm — lateral gap on vertical walls (Y on belt) for easy removal
    "floor_z": 0.1,            # mm — support floor above Z=0
    "min_area": 1.0,           # mm² — skip tiny overhang regions
}


def read_3mf_support_settings(path_3mf):
    """
    Read OrcaSlicer support settings from a 3MF project_settings.config.

    Maps OrcaSlicer JSON keys → preprocessor config keys:
      support_threshold_angle   → threshold_angle
      support_object_xy_distance → xy_gap
      support_top_z_distance    → z_gap

    Returns a dict with only the keys that were found (no defaults injected).
    """
    import json

    try:
        with zipfile.ZipFile(path_3mf) as z:
            if "Metadata/project_settings.config" not in z.namelist():
                return {}
            raw = z.read("Metadata/project_settings.config").decode()
        proj = json.loads(raw)
    except Exception as e:
        print(f"  Warning: could not read 3MF project settings ({e})")
        return {}

    mapping = {
        "support_threshold_angle":   ("threshold_angle", float),
        "support_object_xy_distance": ("xy_gap",          float),
        "support_top_z_distance":    ("z_gap",            float),
    }

    found = {}
    for orca_key, (cfg_key, cast) in mapping.items():
        val = proj.get(orca_key)
        if val is None:
            continue
        # OrcaSlicer stores array values as lists — take first element
        if isinstance(val, list):
            val = val[0]
        try:
            found[cfg_key] = cast(val)
        except (ValueError, TypeError):
            pass

    return found


def load_config(config_path=None, base_overrides=None):
    """
    Load support parameters.

    Priority (lowest → highest):
      1. DEFAULT_CONFIG hardcoded defaults
      2. base_overrides (e.g. values read from the 3MF project settings)
      3. INI file at config_path (explicit --config argument)
    """
    cfg = dict(DEFAULT_CONFIG)

    if base_overrides:
        cfg.update(base_overrides)
        print("Config from 3MF project settings:")
        for k, v in base_overrides.items():
            print(f"  {k} = {v}  (from 3MF)")

    if config_path and Path(config_path).exists():
        parser = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
        parser.read(config_path)
        if "support" in parser:
            for key in list(cfg.keys()):
                if key in parser["support"]:
                    cfg[key] = float(parser["support"][key])
        print(f"Config overrides from {config_path}:")
        if "support" in parser:
            for key in list(cfg.keys()):
                if key in parser["support"]:
                    print(f"  {key} = {cfg[key]}  (from INI)")
    elif not base_overrides:
        print("Using default config")

    print("Effective config:")
    for k, v in cfg.items():
        print(f"  {k} = {v}")
    return cfg


# ── Mesh Loading ─────────────────────────────────────────────────────────────

def load_mesh_local(model_path):
    """
    Load model mesh in LOCAL coordinate space.

    For 3MF: reads the sub-object file directly, bypassing the item transform.
    The item transform is preserved in the output 3MF untouched.
    For STL: loads directly (already local space).
    """
    path = str(model_path)
    if path.lower().endswith(".3mf"):
        return _load_mesh_from_3mf_local(path)
    mesh = trimesh.load(path, force="mesh")
    print(f"Loaded STL: {len(mesh.vertices)} verts, "
          f"X{mesh.bounds[:,0]} Y{mesh.bounds[:,1]} Z{mesh.bounds[:,2]}")
    return mesh


def _load_mesh_from_3mf_local(path_3mf):
    """
    Load the primary model mesh from a 3MF in LOCAL (sub-object) coordinates.

    Reads the sub-object .model file referenced in 3D/_rels/3dmodel.model.rels,
    bypassing the item transform so support geometry is generated in the same
    local coordinate system and gets the same transform on export.
    """
    with zipfile.ZipFile(path_3mf) as z:
        rels_xml = z.read("3D/_rels/3dmodel.model.rels").decode()
        m = re.search(r'Target="([^"]+\.model)"', rels_xml)
        if not m:
            raise ValueError(f"No sub-object .model found in rels of {path_3mf}")
        sub_path = m.group(1).lstrip("/")
        sub_xml = z.read(sub_path).decode()

    verts = []
    for m in re.finditer(r'vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', sub_xml):
        verts.append([float(m.group(1)), float(m.group(2)), float(m.group(3))])

    faces = []
    for m in re.finditer(r'triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', sub_xml):
        faces.append([int(m.group(1)), int(m.group(2)), int(m.group(3))])

    if not verts or not faces:
        raise ValueError(f"No geometry in sub-object {sub_path}")

    mesh = trimesh.Trimesh(
        vertices=np.array(verts, dtype=float),
        faces=np.array(faces, dtype=np.int64),
        process=True,
    )
    print(f"Loaded 3MF local mesh: {len(mesh.vertices)} verts, "
          f"X{mesh.bounds[:,0]} Y{mesh.bounds[:,1]} Z{mesh.bounds[:,2]}")
    return mesh


# ── Overhang Detection ────────────────────────────────────────────────────────

def detect_overhangs(mesh, threshold_angle=50.0, floor_z=0.1, min_area=1.0):
    """
    Standard Cartesian overhang detection.

    A face needs support if:
      1. Normal points downward: normal · [0,0,-1] >= cos(90 - threshold)
      2. Lowest vertex is above floor_z (face is not resting on the build plate)
      3. Its connected overhang region has total area >= min_area

    Connected-component area filter handles tessellated curved surfaces where
    individual faces are small but the region as a whole needs support.

    Returns boolean mask over mesh.faces.
    """
    gravity = np.array([0.0, 0.0, -1.0])
    cos_thresh = np.cos(np.radians(90.0 - threshold_angle))

    normals = mesh.face_normals
    dots = normals @ gravity  # positive = face points downward

    face_verts = mesh.vertices[mesh.faces]  # (N, 3, 3)
    min_zs = face_verts[:, :, 2].min(axis=1)

    candidate = (dots >= cos_thresh) & (min_zs > floor_z)

    if min_area > 0 and candidate.any():
        mask = _filter_by_region_area(mesh, candidate, min_area)
    else:
        mask = candidate

    print(f"\nOverhang detection:")
    print(f"  Total faces: {len(mesh.faces)}")
    print(f"  Candidate faces (angle+height): {candidate.sum()}")
    print(f"  After region area filter (>= {min_area} mm²): {mask.sum()}")
    print(f"  Threshold: {threshold_angle}°, floor_z: {floor_z} mm")
    return mask


def _filter_by_region_area(mesh, candidate_mask, min_area):
    """Keep only overhang faces in connected regions with total area >= min_area."""
    from scipy.sparse import lil_matrix
    from scipy.sparse.csgraph import connected_components

    candidate_indices = np.where(candidate_mask)[0]
    n = len(candidate_indices)
    if n == 0:
        return candidate_mask

    idx_map = {fi: i for i, fi in enumerate(candidate_indices)}
    adj = lil_matrix((n, n), dtype=bool)

    for a, b in mesh.face_adjacency:
        if a in idx_map and b in idx_map:
            i, j = idx_map[a], idx_map[b]
            adj[i, j] = True
            adj[j, i] = True

    n_components, labels = connected_components(adj, directed=False)

    areas = mesh.area_faces
    result_mask = np.copy(candidate_mask)
    for comp in range(n_components):
        comp_faces = candidate_indices[labels == comp]
        if areas[comp_faces].sum() < min_area:
            result_mask[comp_faces] = False

    return result_mask


# ── Support Box Generation ────────────────────────────────────────────────────

# ── Top Surface Modifier ──────────────────────────────────────────────────────

def detect_top_faces(mesh, min_area=1.0, angle_tol=5.0):
    """
    Detect upward-facing horizontal faces at or near the model's Z_max.

    In belt printing, OrcaSlicer's top-shell algorithm works in Z_virt space
    (Z_virt = Y + Z). For a horizontal face at Z=Z_top, the top shells are
    generated only at the stern end (high Y) where Z_virt is maximum. The bow
    end gets no top shells → visible 45° boundary.

    Fix: add a modifier mesh covering the top face region. The modifier forces
    100% solid infill in that region, making the entire top surface solid without
    using top-shell layers (which cause Y > Z → Z_machine < 0 → crash).

    Returns boolean mask over mesh.faces.
    """
    up = np.array([0.0, 0.0, 1.0])
    cos_thresh = np.cos(np.radians(angle_tol))

    dots = mesh.face_normals @ up          # positive = face points upward
    face_verts = mesh.vertices[mesh.faces]
    max_zs = face_verts[:, :, 2].max(axis=1)

    z_model_max = float(mesh.bounds[1, 2])

    # Faces nearly horizontal and within 10% of model height from the top
    candidate = (dots >= cos_thresh) & (max_zs >= z_model_max * 0.9)

    if min_area > 0 and candidate.any():
        mask = _filter_by_region_area(mesh, candidate, min_area)
    else:
        mask = candidate

    print(f"\nTop face detection:")
    print(f"  Z_model_max: {z_model_max:.3f} mm")
    print(f"  Candidate faces: {candidate.sum()}")
    print(f"  After region area filter (>= {min_area} mm²): {mask.sum()}")
    return mask


def create_top_cap(mesh, mask, cap_thickness=2.0):
    """
    Create a solid cap volume covering the XY footprint of top horizontal faces.

    The cap is a thin box (normal_part, not modifier) at Z ∈ [Z_top-cap_thickness, Z_top].
    It is sliced as real geometry with 100% solid infill, wall_loops=0, no shells.

    Belt safety analysis:
      Model local Y ∈ [Y_min, Y_max] → world Y ∈ [Y_min+offset, Y_max+offset] (item transform).
      For any belt layer at Z_virt_n, cap extrusion moves have Y_gcode = Z_virt_n - Z_world
      where Z_world ∈ [Z_top-cap_thickness, Z_top].
      Maximum Y_gcode at layer Z_virt_n = Z_virt_n - (Z_top - cap_thickness).
      Since cap_thickness ≥ 0 and Z_top > 0: max Y_gcode < Z_virt_n = Z_gcode → SAFE.

    DON'T use subtype="modifier" — modifier forces OrcaSlicer to recalculate solid regions
    for the entire object at those layers, generating extrusion paths at large Y values
    (up to Y_world_max + Z_world_max) that exceed Z_gcode → Z_machine < 0 → crash.

    Returns trimesh.Trimesh cap box in LOCAL coordinates, or None.
    """
    if not mask.any():
        return None

    top_verts = mesh.vertices[mesh.faces[np.where(mask)[0]]].reshape(-1, 3)
    x_min = top_verts[:, 0].min()
    x_max = top_verts[:, 0].max()
    y_min = top_verts[:, 1].min()
    y_max = top_verts[:, 1].max()
    z_top = top_verts[:, 2].max()
    z_bot = z_top - cap_thickness

    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    cz = (z_bot + z_top) / 2

    cap = trimesh.creation.box(
        extents=[x_max - x_min, y_max - y_min, z_top - z_bot],
        transform=trimesh.transformations.translation_matrix([cx, cy, cz])
    )

    print(f"\nTop cap box (local space, normal_part):")
    print(f"  X: [{x_min:.3f}, {x_max:.3f}]")
    print(f"  Y: [{y_min:.3f}, {y_max:.3f}]")
    print(f"  Z: [{z_bot:.3f}, {z_top:.3f}]  (thickness={cap_thickness}mm)")
    print(f"  Belt Z_virt coverage: [{z_bot + y_min:.2f}, {z_top + y_max:.2f}]")
    print(f"  Safety: max Y_gcode at any layer < Z_gcode (Z_machine stays positive)")
    return cap


def create_support_box(mesh, mask, xy_gap=0.35, z_gap=0.15, floor_z=0.1):
    """
    Build a solid support box from overhang faces down to the build plate.

    Produces one axis-aligned box covering the XY footprint of all overhang
    faces, from floor_z up to just below the lowest overhang vertex.
    XY shrunk by xy_gap on each side for clearance from the model.

    The model is subtracted afterwards to remove any overlap with the model body.
    This gives clean, discrete geometry: the slicer receives a proper solid.

    Returns trimesh.Trimesh or None if no support needed.
    """
    overhang_indices = np.where(mask)[0]
    if len(overhang_indices) == 0:
        print("No overhang faces — no support needed.")
        return None

    overhang_verts = mesh.vertices[mesh.faces[overhang_indices]].reshape(-1, 3)

    x_min = overhang_verts[:, 0].min() + xy_gap
    x_max = overhang_verts[:, 0].max() - xy_gap
    y_min = overhang_verts[:, 1].min() + xy_gap
    y_max = overhang_verts[:, 1].max() - xy_gap
    z_top = overhang_verts[:, 2].min() - z_gap    # Z clearance below overhang
    z_bot = floor_z

    if z_top <= z_bot:
        print(f"  Warning: overhang at Z={z_top+z_gap:.2f} too close to floor — skipped.")
        return None
    if x_max <= x_min or y_max <= y_min:
        print("  Warning: overhang too small after XY gap — skipped.")
        return None

    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    cz = (z_bot + z_top) / 2
    support = trimesh.creation.box(
        extents=[x_max - x_min, y_max - y_min, z_top - z_bot],
        transform=trimesh.transformations.translation_matrix([cx, cy, cz])
    )

    print(f"\nSupport box (local space):")
    print(f"  X: [{x_min:.3f}, {x_max:.3f}]  (xy_gap={xy_gap}mm)")
    print(f"  Y: [{y_min:.3f}, {y_max:.3f}]  (xy_gap={xy_gap}mm)")
    print(f"  Z: [{z_bot:.3f}, {z_top:.3f}]  (z_gap={z_gap}mm, overhang at Z={z_top+z_gap:.3f})")
    print(f"  Volume: {support.volume:.2f} mm³  Watertight: {support.is_watertight}")
    return support


# ── Legacy Prism Generation (for STL compound mode) ──────────────────────────

def shrink_triangle(verts, gap):
    """Shrink a triangle toward its centroid by `gap` mm."""
    centroid = verts.mean(axis=0)
    directions = centroid - verts
    lengths = np.maximum(np.linalg.norm(directions, axis=1, keepdims=True), 1e-10)
    shift = np.minimum(gap, lengths * 0.8)
    return verts + (directions / lengths) * shift


def create_prism(roof_verts, floor_z):
    """Create a watertight triangular prism from a roof triangle down to floor_z."""
    edge1 = roof_verts[1] - roof_verts[0]
    edge2 = roof_verts[2] - roof_verts[0]
    if np.cross(edge1, edge2)[2] < 0:
        roof_verts = roof_verts[[0, 2, 1]]

    floor_verts = roof_verts.copy()
    floor_verts[:, 2] = floor_z
    vertices = np.vstack([roof_verts, floor_verts])
    faces = np.array([
        [0, 1, 2], [5, 4, 3],
        [0, 1, 4], [0, 4, 3],
        [1, 2, 5], [1, 5, 4],
        [2, 0, 3], [2, 3, 5],
    ], dtype=np.int64)
    return vertices, faces


def create_support_prisms(mesh, mask, xy_gap=0.35, floor_z=0.1):
    """Build triangular prisms under each overhang face (legacy STL mode)."""
    overhang_indices = np.where(mask)[0]
    if len(overhang_indices) == 0:
        print("No overhang faces — no support needed.")
        return None

    all_verts, all_faces, vert_offset = [], [], 0
    for fi in overhang_indices:
        roof = shrink_triangle(mesh.vertices[mesh.faces[fi]], xy_gap)
        e1, e2 = roof[1] - roof[0], roof[2] - roof[0]
        if 0.5 * np.linalg.norm(np.cross(e1, e2)) < 0.01:
            continue
        verts, faces = create_prism(roof, floor_z)
        all_verts.append(verts)
        all_faces.append(faces + vert_offset)
        vert_offset += len(verts)

    if not all_verts:
        print("All overhang faces degenerate after shrinking — no support.")
        return None

    support = trimesh.Trimesh(
        vertices=np.vstack(all_verts),
        faces=np.vstack(all_faces),
        process=True,
    )
    support.fix_normals()
    print(f"\nSupport prisms: {len(all_verts)} prisms, "
          f"{len(support.faces)} faces, volume={support.volume:.2f} mm³")
    return support


# ── Boolean Helpers ───────────────────────────────────────────────────────────

def _make_solid(mesh):
    """
    Return a single watertight solid.

    If the mesh consists of multiple separate watertight bodies joined at faces
    (e.g. multi-body CAD model), unions them so boolean difference works.
    """
    if mesh.is_watertight:
        return mesh
    bodies = mesh.split()
    if len(bodies) == 1:
        return bodies[0]
    if all(b.is_watertight for b in bodies):
        print(f"  Model: {len(bodies)} separate watertight bodies — unioning...")
        solid = trimesh.boolean.union(bodies, engine="manifold")
        print(f"  Unified: watertight={solid.is_watertight}, volume={solid.volume:.1f} mm³")
        return solid
    print(f"  Warning: {len(bodies)} bodies, not all watertight — using as-is")
    return mesh


def _expand_mesh_xy(mesh, offset):
    """
    Expand mesh vertices outward in XY by offset mm (Z unchanged).

    Used to widen the model footprint before boolean subtraction, creating a
    lateral gap between support walls and the model. On the belt printer the
    lateral support walls grow in Y (belt Z), so this gap makes removal easier.

    Only vertices with a meaningful XY component in their vertex normal are
    moved — vertices on purely horizontal faces (top/bottom) are skipped so
    Z bounds stay exact.

    Returns a new Trimesh with expanded vertices.
    """
    if offset <= 0:
        return mesh

    # Vertex normals, project to XY plane
    normals = mesh.vertex_normals.copy()
    xy_normals = normals.copy()
    xy_normals[:, 2] = 0.0

    magnitudes = np.linalg.norm(xy_normals, axis=1)   # shape (N,)
    has_xy = magnitudes > 1e-6

    xy_unit = np.zeros_like(xy_normals)
    xy_unit[has_xy] = xy_normals[has_xy] / magnitudes[has_xy, np.newaxis]

    new_vertices = mesh.vertices.copy()
    new_vertices[has_xy, :2] += xy_unit[has_xy, :2] * offset

    expanded = trimesh.Trimesh(
        vertices=new_vertices,
        faces=mesh.faces.copy(),
        process=False,
    )
    n_moved = int(has_xy.sum())
    print(f"  Model expanded in XY by {offset}mm ({n_moved}/{len(mesh.vertices)} vertices)")
    return expanded


def _subtract_model(support_raw, model, side_gap=0.0):
    """
    Subtract model from support box to remove overlap, return clean support.

    side_gap: expand model in XY by this amount before subtraction, creating
    a lateral clearance gap on vertical support walls for easier removal.
    """
    print("\nBoolean: subtracting model from support...")
    model_solid = _make_solid(model)
    if side_gap > 0:
        model_solid = _expand_mesh_xy(model_solid, side_gap)
    try:
        result = trimesh.boolean.difference([support_raw, model_solid], engine="manifold")
        if result is None or result.is_empty:
            print("  Warning: boolean difference empty — using raw support box")
            return support_raw
        print(f"  Support after subtraction: {len(result.faces)} faces, "
              f"volume={result.volume:.2f} mm³")
        print(f"  Bounds: X{result.bounds[:,0]} Y{result.bounds[:,1]} Z{result.bounds[:,2]}")
        return result
    except Exception as e:
        print(f"  Warning: boolean subtraction failed ({e}) — using raw support box")
        return support_raw


# ── 3MF Two-Volume Export ─────────────────────────────────────────────────────

def _mesh_to_xml_body(mesh, object_id):
    """Render a trimesh as the XML body of a 3MF object element."""
    vert_lines = "\n".join(
        f'     <vertex x="{v[0]:.6f}" y="{v[1]:.6f}" z="{v[2]:.6f}"/>'
        for v in mesh.vertices
    )
    tri_lines = "\n".join(
        f'     <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>'
        for f in mesh.faces
    )
    return f''' <object id="{object_id}" type="model">
  <mesh>
   <vertices>
{vert_lines}
   </vertices>
   <triangles>
{tri_lines}
   </triangles>
  </mesh>
 </object>'''


def export_3mf_two_volumes(source_3mf, support_local, output_path,
                           infill_density="10%"):
    """
    Embed support into source_3mf and patch print settings for belt safety.

    Volumes in the output composite object:
      - Part 1 (model):   normal walls + infill; top_shell_layers from original 3MF
      - Part 2 (support): wall_loops=0, no shells, sparse infill, top_shell_layers=0

    All volumes share the same item transform → same belt pipeline.

    project_settings patched:
      - brim=no_brim          (prevents large Y in first layer → crash)
      - enable_support=0      (we provide explicit support geometry)
    """
    SUPPORT_OBJ_ID = 3
    SUPPORT_OBJ_FILE = "3D/Objects/support_part.model"
    SUPPORT_REL_ID = "rel-support"

    with zipfile.ZipFile(source_3mf) as zin:
        files = {name: zin.read(name) for name in zin.namelist()}

    # ── 1. Parse 3dmodel.model: find composite object id ─────────────────
    model_xml = files["3D/3dmodel.model"].decode()
    m = re.search(r'<object\s+id="(\d+)"[^>]*>\s*<components>', model_xml)
    if not m:
        raise ValueError("No composite object with <components> in 3dmodel.model")
    composite_id = int(m.group(1))

    # ── 2. Inject support component ───────────────────────────────────────
    support_component = (
        f'    <component p:path="/{SUPPORT_OBJ_FILE}" '
        f'objectid="{SUPPORT_OBJ_ID}" '
        f'p:UUID="{uuid.uuid4()}" '
        f'transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
    )
    model_xml = model_xml.replace(
        "</components>",
        f"{support_component}\n   </components>",
    )
    files["3D/3dmodel.model"] = model_xml.encode()

    # ── 3. Create support sub-object file ─────────────────────────────────
    def _make_sub_model(mesh, obj_id):
        body = _mesh_to_xml_body(mesh, obj_id)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US"\n'
            '  xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"\n'
            '  xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">\n'
            ' <resources>\n'
            f'{body}\n'
            ' </resources>\n'
            '</model>'
        )

    files[SUPPORT_OBJ_FILE] = _make_sub_model(support_local, SUPPORT_OBJ_ID).encode()

    # ── 4. Update rels ────────────────────────────────────────────────────
    rels_xml = files["3D/_rels/3dmodel.model.rels"].decode()
    new_rel = (
        f' <Relationship Target="/{SUPPORT_OBJ_FILE}" '
        f'Id="{SUPPORT_REL_ID}" '
        f'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    )
    rels_xml = rels_xml.replace("</Relationships>",
                                f"{new_rel}\n</Relationships>")
    files["3D/_rels/3dmodel.model.rels"] = rels_xml.encode()

    # ── 5. Update model_settings.config ──────────────────────────────────
    settings_xml = files["Metadata/model_settings.config"].decode()

    inf_str = str(infill_density).rstrip("%") + "%"

    support_part_xml = (
        f'    <part id="{SUPPORT_OBJ_ID}" subtype="normal_part">\n'
        f'      <metadata key="name" value="support"/>\n'
        f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
        f'      <metadata key="wall_loops" value="0"/>\n'
        f'      <metadata key="top_shell_layers" value="0"/>\n'
        f'      <metadata key="bottom_shell_layers" value="0"/>\n'
        f'      <metadata key="sparse_infill_density" value="{inf_str}"/>\n'
        f'      <metadata key="enable_support" value="0"/>\n'
        f'      <mesh_stat edges_fixed="0" degenerate_facets="0" '
        f'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
        f'    </part>'
    )

    obj_open_pat = f'<object id="{composite_id}">'
    obj_open_idx = settings_xml.find(obj_open_pat)
    if obj_open_idx == -1:
        raise ValueError(f'<object id="{composite_id}"> not found in model_settings.config')

    close_idx = settings_xml.find("</object>", obj_open_idx)
    if close_idx == -1:
        raise ValueError("</object> not found in model_settings.config")
    settings_xml = (
        settings_xml[:close_idx]
        + support_part_xml + "\n  "
        + settings_xml[close_idx:]
    )
    files["Metadata/model_settings.config"] = settings_xml.encode()

    # ── 5b. Patch project_settings.config ────────────────────────────────
    # brim=no_brim: belt keel at Y≈0 provides adhesion; brim would extend Y_gcode
    #   across the full footprint in first layer → dangerous large Y values.
    # enable_support=0: support geometry is provided explicitly as a mesh volume.
    # NOTE: top_shell_layers is NOT overridden — preserve original value from 3MF.
    #   A high top_shell_layers (e.g. 36) causes top shell infill at high Y_virt layers
    #   (pillar tops at Y_virt≈25-30mm, Y_gcode=35-42mm). These generate z_mach positions
    #   inconsistent with belt physical position → Z motor stalls → nozzle crash (v21/v22).

    if "Metadata/project_settings.config" in files:
        proj_cfg = files["Metadata/project_settings.config"].decode()
        proj_cfg = re.sub(
            r'"brim_type"\s*:\s*"[^"]*"', '"brim_type": "no_brim"', proj_cfg
        )
        proj_cfg = re.sub(
            r'"brim_width"\s*:\s*"[^"]*"', '"brim_width": "0"', proj_cfg
        )
        proj_cfg = re.sub(
            r'"enable_support"\s*:\s*"[^"]*"', '"enable_support": "0"', proj_cfg
        )

        files["Metadata/project_settings.config"] = proj_cfg.encode()
        print(f"  project_settings.config: brim=no_brim, enable_support=0")

    # ── 6. Write output zip ───────────────────────────────────────────────
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in files.items():
            zout.writestr(name, data)

    print(f"\n2-volume 3MF written: {output_path}")
    print(f"  Object id={composite_id}: model(1) + support({SUPPORT_OBJ_ID})")
    print(f"  Support: X{support_local.bounds[:,0]} Y{support_local.bounds[:,1]} "
          f"Z{support_local.bounds[:,2]}  infill={inf_str}")


# ── Legacy STL Compound Export ────────────────────────────────────────────────

def make_compound_stl(model_path, config):
    """
    Full pipeline for STL compound mode: load → detect → prisms → subtract → union.
    Returns (compound_mesh, support_mesh).
    """
    print(f"Loading model: {model_path}")
    model = trimesh.load(model_path, force="mesh")
    print(f"  Vertices: {len(model.vertices)}, Faces: {len(model.faces)}, "
          f"Volume: {model.volume:.2f} mm³")

    overhang_mask = detect_overhangs(
        model,
        threshold_angle=config["threshold_angle"],
        floor_z=config["floor_z"],
        min_area=config["min_area"],
    )

    if not overhang_mask.any():
        print("\nNo overhangs detected — returning model as-is.")
        return model, None

    support_raw = create_support_prisms(
        model, overhang_mask,
        xy_gap=config["xy_gap"],
        floor_z=config["floor_z"],
    )
    if support_raw is None:
        return model, None

    support_clean = _subtract_model(support_raw, model, side_gap=config.get("side_gap", 0.0))

    print("\nBoolean: union model + support...")
    try:
        compound = trimesh.boolean.union([model, support_clean], engine="manifold")
        print(f"  Compound: {len(compound.vertices)} verts, "
              f"{len(compound.faces)} faces, volume={compound.volume:.2f} mm³")
    except Exception as e:
        print(f"  Warning: union failed ({e}) — concatenating meshes")
        compound = trimesh.util.concatenate([model, support_clean])

    return compound, support_clean


def export_mesh(mesh, output_path):
    """Export mesh as STL."""
    mesh.export(str(output_path), file_type="stl")
    size_kb = Path(output_path).stat().st_size / 1024
    print(f"\nExported: {output_path} ({size_kb:.1f} KB)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Belt printer support pre-processor: generates support geometry "
                    "in XYZ space and embeds it as a second volume in the 3MF."
    )
    parser.add_argument("model", help="Source .3mf file (or .stl with --compound)")
    parser.add_argument("-o", "--output", default=None,
                        help="Output path (default: <model>_supported.3mf)")
    parser.add_argument("-c", "--config", default=None,
                        help="Support config INI file")
    parser.add_argument("--infill", default="10%",
                        help="Support infill density (default: 10%%)")
    parser.add_argument("--support-only", action="store_true",
                        help="Export only the support mesh as STL (debug)")
    parser.add_argument("--compound", action="store_true",
                        help="Legacy STL mode: fuse model+support into compound mesh")
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Error: {model_path} not found", file=sys.stderr)
        sys.exit(1)

    if args.output is None:
        args.output = str(model_path.stem) + ("_compound.stl" if args.compound
                                               else "_supported.3mf")

    # Read support settings from the 3MF first (if available), then let
    # the explicit --config INI file override them.
    base_overrides = {}
    if model_path.suffix.lower() == ".3mf":
        base_overrides = read_3mf_support_settings(str(model_path))

    config = load_config(args.config, base_overrides=base_overrides)

    # ── Legacy STL compound mode ───────────────────────────────────────────
    if args.compound:
        compound, support = make_compound_stl(str(model_path), config)
        export_mesh(support if args.support_only and support else compound,
                    args.output)
        print("\nDone.")
        return

    # ── 3MF two-volume mode ────────────────────────────────────────────────
    if model_path.suffix.lower() != ".3mf":
        print("Error: two-volume mode requires a .3mf source.", file=sys.stderr)
        print("Use --compound for STL input.", file=sys.stderr)
        sys.exit(1)

    # Load model in LOCAL space for overhang detection and boolean ops
    model_local = load_mesh_local(str(model_path))

    overhang_mask = detect_overhangs(
        model_local,
        threshold_angle=config["threshold_angle"],
        floor_z=config["floor_z"],
        min_area=config["min_area"],
    )

    if not overhang_mask.any():
        print("\nNo overhangs detected — copying source 3MF unchanged.")
        shutil.copy2(str(model_path), args.output)
        print(f"Copied: {args.output}")
        print("\nDone.")
        return

    support_raw = create_support_box(
        model_local, overhang_mask,
        xy_gap=config["xy_gap"],
        z_gap=config["z_gap"],
        floor_z=config["floor_z"],
    )

    if support_raw is None:
        shutil.copy2(str(model_path), args.output)
        print("\nDone.")
        return

    if args.support_only:
        out_stl = args.output.replace(".3mf", "_support.stl")
        support_raw.export(out_stl, file_type="stl")
        print(f"\nSupport mesh exported: {out_stl}")
        print("\nDone.")
        return

    support_local = _subtract_model(support_raw, model_local,
                                    side_gap=config["side_gap"])

    export_3mf_two_volumes(
        source_3mf=str(model_path),
        support_local=support_local,
        output_path=args.output,
        infill_density=args.infill,
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
