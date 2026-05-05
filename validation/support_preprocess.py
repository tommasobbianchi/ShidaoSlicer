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
import tempfile
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
    "bottom_z_gap": 0.0,       # mm — extra Z clearance between belt floor and support bottom
                               # (0 = support sits on belt; >0 lifts it off the bed for easier detach)
    "side_gap": 0.15,          # mm — lateral gap on vertical walls (Y on belt) for easy removal
    "floor_z": 0.1,            # mm — support floor above Z=0 (default; bottom_z_gap adds on top of this)
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
        "support_threshold_angle":    ("threshold_angle", float),
        "support_object_xy_distance": ("xy_gap",          float),
        "support_top_z_distance":     ("z_gap",           float),
        "support_bottom_z_distance":  ("bottom_z_gap",    float),
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

    # Belt-directional: custom project key, bool (stored as "1" / "0" / true / false).
    # Not in the standard OrcaSlicer schema — ORCA_BELT extension so per-project
    # overrides survive across re-slices without re-specifying CLI flags.
    raw = proj.get("belt_directional_supports")
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if raw is not None:
        s = str(raw).strip().lower()
        if s in ("1", "true", "yes", "on"):
            found["belt_directional"] = True
        elif s in ("0", "false", "no", "off"):
            found["belt_directional"] = False

    # Custom: belt_support_wedge_layers — overrides --wedge-layers CLI default.
    # When set in 3MF project settings, the preprocessor uses this instead of
    # args.wedge_layers (CLI). Lets the GUI sidebar tune solid base height.
    raw = proj.get("belt_support_wedge_layers")
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if raw is not None:
        try:
            found["wedge_layers_override"] = int(raw)
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


def _parse_item_transform(model_xml):
    """Return (R_3x3, translation_xyz) from the first <item transform="..."/>
    element in 3dmodel.model. 3MF uses a row-vector convention with the 12
    numbers laid out as m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32.

    For an identity rotation returns R=I and translation=(tx,ty,tz).
    For a user rotation (e.g. 90° Z via Orca gizmo) returns the actual 3×3
    rotation block — this is what we need to know BEFORE generating supports
    so the keel wedge lands at the right world-corner after Orca re-applies
    the item transform on load. Falls back to identity if no transform is
    found (the preprocessor used to assume this).
    """
    m = re.search(r'<item\s+[^>]*transform="([^"]+)"', model_xml)
    if not m:
        return np.eye(3), np.zeros(3)
    nums = [float(x) for x in m.group(1).split()]
    if len(nums) < 12:
        return np.eye(3), np.zeros(3)
    # rows 0..2 of the 3×3 rotation block
    R = np.array([
        [nums[0], nums[1], nums[2]],
        [nums[3], nums[4], nums[5]],
        [nums[6], nums[7], nums[8]],
    ])
    t = np.array([nums[9], nums[10], nums[11]])
    return R, t


def _load_mesh_from_3mf_local(path_3mf):
    """
    Load the primary model mesh from a 3MF in LOCAL (sub-object) coordinates,
    then apply the <item transform> rotation so the returned mesh is in
    WORLD-rotated space (translation ignored — trafo_centered handles it).

    Why the rotation matters: when a user rotates the object via Orca's gizmo
    (or via MCP object_transform.rotate), Orca stores the rotation in the
    item transform, not in the vertex data. If the preprocessor computed
    keel_gap on unrotated vertices it would place the keel wedge at the
    original corner, which after Orca re-applies the item transform ends up
    somewhere OTHER than the rotated-world keel corner. Gate R11 then blocks
    the gcode because the wedge no longer fills the Y+Z=0.283 first layer.

    By applying the rotation here, downstream keel_gap / wedge geometry is
    computed in the exact world space the slicer will see — and the caller
    is expected to inverse-rotate any generated geometry back to local coords
    before writing the output sub-object (so the 3MF item transform doesn't
    re-apply the rotation a second time).
    """
    with zipfile.ZipFile(path_3mf) as z:
        model_xml = z.read("3D/3dmodel.model").decode()
        try:
            # Multi-sub-object layout: root 3dmodel.model lists <component>
            # tags pointing to Objects/*.model files via the .rels sidecar.
            rels_xml = z.read("3D/_rels/3dmodel.model.rels").decode()
            m = re.search(r'Target="([^"]+\.model)"', rels_xml)
            if not m:
                raise KeyError("rels present but no sub-object")
            sub_path = m.group(1).lstrip("/")
            sub_xml = z.read(sub_path).decode()
        except KeyError:
            # Flat layout (Orca's own "Save As 3MF" output): vertices/triangles
            # live inline in 3D/3dmodel.model, no sub-object files.
            sub_xml = model_xml

    verts = []
    for m in re.finditer(r'vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', sub_xml):
        verts.append([float(m.group(1)), float(m.group(2)), float(m.group(3))])

    faces = []
    for m in re.finditer(r'triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', sub_xml):
        faces.append([int(m.group(1)), int(m.group(2)), int(m.group(3))])

    if not verts or not faces:
        raise ValueError(f"No geometry in sub-object {sub_path}")

    V = np.array(verts, dtype=float)

    # Parse + apply the item transform (rotation AND translation).
    # 3MF row-vector convention: p_world = p_local · M  →  V_world = V @ R + t
    # Orca's "Save As 3MF" stores the plate-centering offset in this
    # translation (e.g. t=(125, 20.35, 17.05)) so the mesh in the sub-object
    # is centered around origin but ends up on the plate after load. Without
    # applying it here, keel_gap / overhang detection / floor_z would all run
    # in centered-origin space — producing supports the size of the bounding
    # box. We apply R+t and later inverse-transform (R⁻¹, −t) on export.
    R, t_item = _parse_item_transform(model_xml)

    # Plater::export_3mf with SaveStrategy::SplitModel splits the user's
    # placement across two transforms in tmp_in:
    #   <item transform="...">           — instance.transformation (placement)
    #   model_settings.config <matrix>   — m_transformation (mesh-original frame)
    # The mesh sub-file stores vertices CENTERED around origin. To work in
    # WORLD coords we must apply BOTH transforms (centered → user-mesh frame
    # via part-matrix, then → world via item).
    # BUT for the inverse-translate on export (`_to_local`) we only want to
    # subtract the ITEM translation — not the part-matrix one — because
    # dst.volume[0].mesh in Plater is in the user-mesh frame (= world minus
    # item.translation), and dst.add_volume copies mesh + m_transformation
    # both. Support local must match dst.volume[0].mesh frame to avoid the
    # belt-zyt slicer hang.
    t_part = np.zeros(3)
    try:
        with zipfile.ZipFile(path_3mf) as z:
            if "Metadata/model_settings.config" in z.namelist():
                ms_xml = z.read("Metadata/model_settings.config").decode()
                m_pm = re.search(
                    r'<part\s+id="1"[^>]*>.*?<metadata\s+key="matrix"\s+value="([^"]+)"',
                    ms_xml, re.DOTALL)
                if m_pm:
                    pm_nums = [float(x) for x in m_pm.group(1).split()]
                    if len(pm_nums) >= 16:
                        t_part = np.array([pm_nums[3], pm_nums[7], pm_nums[11]])
    except Exception:
        pass

    t_total = t_item + t_part
    V = V @ R + t_total
    notes = []
    if not np.allclose(R, np.eye(3), atol=1e-6):
        notes.append(f"R=\n{R}")
    if not np.allclose(t_item, 0, atol=1e-6):
        notes.append(f"item.t={t_item}")
    if not np.allclose(t_part, 0, atol=1e-6):
        notes.append(f"part.t={t_part}")
    rot_note = " (transforms applied: " + "; ".join(notes) + ")" if notes else ""
    # Stash the ITEM translation only — the part-matrix translation lives in
    # the user-mesh frame and is preserved separately by Plater on import.
    t = t_item

    mesh = trimesh.Trimesh(
        vertices=V,
        faces=np.array(faces, dtype=np.int64),
        process=True,
    )
    mesh.metadata["item_rotation"] = R     # stash for later inverse-rotate on export
    mesh.metadata["item_translation"] = t  # stash for later inverse-translate on export
    print(f"Loaded 3MF local mesh: {len(mesh.vertices)} verts, "
          f"X{mesh.bounds[:,0]} Y{mesh.bounds[:,1]} Z{mesh.bounds[:,2]}{rot_note}")
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


def _overhang_regions(mesh, mask):
    """Group mask-true faces into connected components via face adjacency.

    Yields lists of face indices, one per connected region.
    """
    from scipy.sparse import lil_matrix
    from scipy.sparse.csgraph import connected_components

    cand_idx = np.where(mask)[0]
    if len(cand_idx) == 0:
        return
    idx_map = {fi: i for i, fi in enumerate(cand_idx)}
    adj = lil_matrix((len(cand_idx), len(cand_idx)), dtype=bool)
    for a, b in mesh.face_adjacency:
        if a in idx_map and b in idx_map:
            i, j = idx_map[a], idx_map[b]
            adj[i, j] = True
            adj[j, i] = True
    n_comp, labels = connected_components(adj, directed=False)
    for c in range(n_comp):
        yield cand_idx[labels == c]


def filter_belt_directional(mesh, overhang_mask,
                            xy_radius=2.0, z_tolerance=0.8, dz_lead=0.4):
    """
    Belt-printer directional filter: remove overhang regions already supported
    by earlier-printed material that the belt carries into position.

    Physics. Belt print order = virt_Z = Y + Z. Smaller virt_Z prints first;
    the belt then advances that material in +Y. Between time t₀ and t₁ the
    belt advance in world Y equals (virt_Z₁ − virt_Z₀), so a roof face deposited
    at (X_v, Y_v, Z_v) at time virt_Z_v ends up at (X_v, Y_v + Δ, Z_v) at the
    later time virt_Z_v + Δ. X and Z do NOT change — only Y slides. So an
    overhang at world (X_o, Y_o, Z_o) is self-supported by a prior roof iff
    that roof exists at the SAME X, SAME Z, with any smaller virt_Z — the belt
    slides it under.

    Algorithm (per connected overhang region R):
      1. virt_Z_R = min(Y + Z) over R. Z_R_min = min Z.
      2. X_c = area-weighted X of region face centers.
      3. Candidate prior = non-overhang faces with:
            - face-normal.Z > 0.1  (upward-facing "roof")
            - face-center virt_Z < virt_Z_R − dz_lead (strictly earlier).
      4. Keep candidates with |face-center X − X_c| ≤ xy_radius AND
         |face-center Z − Z_R_min| ≤ z_tolerance.
      5. If ≥1 qualifies, the belt slides it under R → drop R from mask.

    Pure (mesh, mask) → mask. Can only REMOVE supports, never add.
    """
    if not overhang_mask.any():
        return overhang_mask

    centers = mesh.triangles_center  # (F, 3)
    normals = mesh.face_normals      # (F, 3)
    areas   = mesh.area_faces        # (F,)
    virt_z_face = centers[:, 1] + centers[:, 2]

    # Non-overhang roof faces — potential belt-delivered support surfaces.
    is_roof = (normals[:, 2] > 0.1) & (~overhang_mask)
    if not is_roof.any():
        return overhang_mask

    result_mask = overhang_mask.copy()
    kept = 0
    dropped = 0
    for region_faces in _overhang_regions(mesh, overhang_mask):
        region_verts_idx = np.unique(mesh.faces[region_faces].flatten())
        region_verts = mesh.vertices[region_verts_idx]
        virt_z_R = float((region_verts[:, 1] + region_verts[:, 2]).min())
        Z_R_min = float(region_verts[:, 2].min())

        tri_c = centers[region_faces]
        tri_a = areas[region_faces]
        total_area = tri_a.sum()
        if total_area <= 0.0:
            kept += len(region_faces)
            continue
        X_c = float((tri_c[:, 0] * tri_a).sum() / total_area)

        prior = is_roof & (virt_z_face < virt_z_R - dz_lead)
        if not prior.any():
            kept += len(region_faces)
            continue
        cand = centers[prior]
        x_ok = np.abs(cand[:, 0] - X_c) <= xy_radius
        z_ok = np.abs(cand[:, 2] - Z_R_min) <= z_tolerance
        if (x_ok & z_ok).any():
            result_mask[region_faces] = False
            dropped += len(region_faces)
        else:
            kept += len(region_faces)

    print(f"\nBelt-directional filter:")
    print(f"  xy_radius={xy_radius}mm z_tolerance={z_tolerance}mm dz_lead={dz_lead}mm")
    print(f"  Faces kept (still need support): {kept}")
    print(f"  Faces dropped (belt self-supported): {dropped}")
    return result_mask


def create_support_box(mesh, mask, xy_gap=0.35, z_gap=0.15, floor_z=0.1):
    """
    Build solid support boxes under overhang regions.

    For each connected overhang region, produces one axis-aligned box covering
    its XY footprint, from floor_z up to just below that region's lowest vertex.
    XY shrunk by xy_gap on each side for clearance from the model.

    Per-region boxes (vs a single global box) prevent one degenerate region
    — e.g. a chamfered edge right at Z_min — from collapsing the entire support.

    Multiple boxes are returned as a single multi-body Trimesh; downstream
    boolean ops (manifold engine) handle disconnected components.

    Returns trimesh.Trimesh or None if no valid region.
    """
    if not mask.any():
        print("No overhang faces — no support needed.")
        return None

    boxes = []
    skipped_degenerate_z = 0
    skipped_small_xy = 0

    for region_faces in _overhang_regions(mesh, mask):
        vs = mesh.vertices[mesh.faces[region_faces]].reshape(-1, 3)
        x_min = vs[:, 0].min() + xy_gap
        x_max = vs[:, 0].max() - xy_gap
        y_min = vs[:, 1].min() + xy_gap
        y_max = vs[:, 1].max() - xy_gap
        z_top = vs[:, 2].min() - z_gap
        z_bot = floor_z

        if z_top <= z_bot:
            skipped_degenerate_z += 1
            continue
        if x_max <= x_min or y_max <= y_min:
            skipped_small_xy += 1
            continue

        cx = (x_min + x_max) / 2
        cy = (y_min + y_max) / 2
        cz = (z_bot + z_top) / 2
        boxes.append(trimesh.creation.box(
            extents=[x_max - x_min, y_max - y_min, z_top - z_bot],
            transform=trimesh.transformations.translation_matrix([cx, cy, cz])
        ))

    if not boxes:
        print(f"  Warning: no valid support regions "
              f"({skipped_degenerate_z} degenerate Z, {skipped_small_xy} too small XY) — skipped.")
        return None

    support = boxes[0] if len(boxes) == 1 else trimesh.util.concatenate(boxes)

    print(f"\nSupport boxes (local space): {len(boxes)} region(s)")
    if skipped_degenerate_z or skipped_small_xy:
        print(f"  Skipped: {skipped_degenerate_z} degenerate Z (near floor), "
              f"{skipped_small_xy} too small XY")
    bb = support.bounds
    print(f"  Overall bounds: X[{bb[0,0]:.2f},{bb[1,0]:.2f}] "
          f"Y[{bb[0,1]:.2f},{bb[1,1]:.2f}] Z[{bb[0,2]:.2f},{bb[1,2]:.2f}]")
    print(f"  Total volume: {support.volume:.2f} mm³")
    _log_components(support, "after create_support_box")
    return support


# ── Tree-shaped supports (A4 v1, opt-in via --tree) ──────────────────────────

def _rect_frustum(x_c, y_c, z_bot, z_top,
                  w_bot, h_bot, w_top, h_top):
    """Build a rectangular frustum centered at (x_c, y_c).

    Bottom face = `w_bot × h_bot` rectangle at z=z_bot.
    Top face    = `w_top × h_top` rectangle at z=z_top.
    Returns trimesh.Trimesh (12 triangles, 8 vertices, watertight).

    Purpose: leaf cluster of a tree-support — connects the small trunk top
    cross-section to the wider contact-polygon at the overhang underside.
    """
    wb, hb = w_bot * 0.5, h_bot * 0.5
    wt, ht = w_top * 0.5, h_top * 0.5
    verts = np.array([
        [x_c - wb, y_c - hb, z_bot],  # 0 bottom -X-Y
        [x_c + wb, y_c - hb, z_bot],  # 1 bottom +X-Y
        [x_c + wb, y_c + hb, z_bot],  # 2 bottom +X+Y
        [x_c - wb, y_c + hb, z_bot],  # 3 bottom -X+Y
        [x_c - wt, y_c - ht, z_top],  # 4 top    -X-Y
        [x_c + wt, y_c - ht, z_top],  # 5 top    +X-Y
        [x_c + wt, y_c + ht, z_top],  # 6 top    +X+Y
        [x_c - wt, y_c + ht, z_top],  # 7 top    -X+Y
    ], dtype=float)
    faces = np.array([
        [0, 2, 1], [0, 3, 2],   # bottom (normal -Z)
        [4, 5, 6], [4, 6, 7],   # top    (normal +Z)
        [0, 1, 5], [0, 5, 4],   # -Y side
        [1, 2, 6], [1, 6, 5],   # +X side
        [2, 3, 7], [2, 7, 6],   # +Y side
        [3, 0, 4], [3, 4, 7],   # -X side
    ], dtype=np.int64)
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    m.fix_normals()
    return m


def _xy_merge_groups(region_xy_centroids, merge_radius):
    """Union-find: group regions whose XY centroids are within merge_radius.

    Pure list operation — no mesh data needed.
    Returns list[list[int]] (each sublist = indices of regions in that group).
    """
    n = len(region_xy_centroids)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    r2 = merge_radius * merge_radius
    for i in range(n):
        xi, yi = region_xy_centroids[i]
        for j in range(i + 1, n):
            xj, yj = region_xy_centroids[j]
            dx, dy = xi - xj, yi - yj
            if dx * dx + dy * dy < r2:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[ra] = rb

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def create_support_tree(mesh, mask,
                        trunk_w=4.0, merge_radius=2.0,
                        leaf_shrink=0.7, trunk_clearance=1.0,
                        xy_gap=0.35, z_gap=0.15, floor_z=0.1,
                        debug_export_path=None):
    """
    Build tree-shaped support volumes under overhang regions (A4, v1).

    Geometry per merged group of regions:
      - Trunk: vertical box (W×W cross-section) at the group's area-weighted
        XY centroid, from floor_z to z_top - trunk_clearance.
      - Leaf cluster: single frustum tapering from trunk top up to the
        contact-polygon bbox * leaf_shrink, at z = z_top - z_gap. One leaf
        per group covers all that group's contact areas.

    XY-merge: groups regions whose XY centroids are within `merge_radius` of
    each other. The merged trunk uses the group's combined area-weighted XY
    centroid; the leaf bbox covers all contact polygons in the group.

    All operations live in MODEL-SPACE (XY = belt surface, Z = perpendicular
    to belt). The downstream pipeline (subtract from model, wedge split,
    3MF emit, Orca rectilinear infill) is identical to box-column flow.

    Returns trimesh.Trimesh or None if no valid region.
    """
    if not mask.any():
        print("No overhang faces — no support needed.")
        return None

    # ── Pass 1: per-region descriptors ───────────────────────────────────
    centers = mesh.triangles_center
    areas   = mesh.area_faces
    regions = []
    skipped_degenerate_z = 0
    for region_faces in _overhang_regions(mesh, mask):
        vs = mesh.vertices[mesh.faces[region_faces]].reshape(-1, 3)
        z_top_raw = vs[:, 2].min()
        z_top_for_leaf = z_top_raw - z_gap
        z_trunk_top    = z_top_for_leaf - trunk_clearance
        if z_trunk_top <= floor_z:
            skipped_degenerate_z += 1
            continue

        tri_c = centers[region_faces]
        tri_a = areas[region_faces]
        total_area = float(tri_a.sum())
        if total_area <= 0.0:
            continue
        x_c = float((tri_c[:, 0] * tri_a).sum() / total_area)
        y_c = float((tri_c[:, 1] * tri_a).sum() / total_area)

        # Contact-polygon bbox, shrunk by xy_gap for clearance from model.
        x_lo = float(vs[:, 0].min()) + xy_gap
        x_hi = float(vs[:, 0].max()) - xy_gap
        y_lo = float(vs[:, 1].min()) + xy_gap
        y_hi = float(vs[:, 1].max()) - xy_gap

        regions.append({
            "xy_c": (x_c, y_c),
            "xy_bbox": (x_lo, x_hi, y_lo, y_hi),  # may be inverted for tiny regions
            "z_top_for_leaf": z_top_for_leaf,
            "z_trunk_top":    z_trunk_top,
            "area": total_area,
        })

    if not regions:
        print(f"  Tree: no valid regions ({skipped_degenerate_z} degenerate Z) — skipped.")
        return None

    # ── Pass 2: XY-merge ─────────────────────────────────────────────────
    if merge_radius > 0.0:
        groups_idx = _xy_merge_groups([r["xy_c"] for r in regions], merge_radius)
    else:
        groups_idx = [[i] for i in range(len(regions))]

    # ── Pass 3: build mesh per group ─────────────────────────────────────
    parts = []
    n_with_leaf = 0
    n_trunk_only = 0
    for grp in groups_idx:
        # Combined descriptors for the group.
        total_area = sum(regions[i]["area"] for i in grp)
        x_c = sum(regions[i]["xy_c"][0] * regions[i]["area"] for i in grp) / total_area
        y_c = sum(regions[i]["xy_c"][1] * regions[i]["area"] for i in grp) / total_area
        # Leaf bbox = union of all regions' shrunk contact bboxes.
        x_lo = min(regions[i]["xy_bbox"][0] for i in grp)
        x_hi = max(regions[i]["xy_bbox"][1] for i in grp)
        y_lo = min(regions[i]["xy_bbox"][2] for i in grp)
        y_hi = max(regions[i]["xy_bbox"][3] for i in grp)
        # Z: take the highest leaf top in the group; trunk_top likewise. The
        # group's trunk reaches up to whichever region is highest.
        z_top_leaf  = max(regions[i]["z_top_for_leaf"] for i in grp)
        z_trunk_top = max(regions[i]["z_trunk_top"]    for i in grp)

        # Leaf top dimensions: contact bbox * leaf_shrink, recentered on (x_c, y_c).
        bbox_w = max(0.0, x_hi - x_lo)
        bbox_h = max(0.0, y_hi - y_lo)
        leaf_w = bbox_w * leaf_shrink
        leaf_h = bbox_h * leaf_shrink

        # Trunk cross-section: trunk_w × trunk_w, recentered on (x_c, y_c).
        # Add a leaf only if it strictly widens trunk in at least one axis.
        add_leaf = (leaf_w > trunk_w) or (leaf_h > trunk_w)

        if add_leaf:
            trunk_h = z_trunk_top - floor_z
            trunk_cz = (floor_z + z_trunk_top) * 0.5
            parts.append(trimesh.creation.box(
                extents=[trunk_w, trunk_w, trunk_h],
                transform=trimesh.transformations.translation_matrix([x_c, y_c, trunk_cz]),
            ))
            # Frustum: bottom matches trunk top, top matches leaf bbox (clamped to ≥ trunk_w).
            top_w = max(leaf_w, trunk_w)
            top_h = max(leaf_h, trunk_w)
            parts.append(_rect_frustum(
                x_c, y_c, z_trunk_top, z_top_leaf,
                trunk_w, trunk_w, top_w, top_h,
            ))
            n_with_leaf += 1
        else:
            # Trunk-only: extend the trunk all the way up to z_top_leaf.
            full_h = z_top_leaf - floor_z
            full_cz = (floor_z + z_top_leaf) * 0.5
            parts.append(trimesh.creation.box(
                extents=[trunk_w, trunk_w, full_h],
                transform=trimesh.transformations.translation_matrix([x_c, y_c, full_cz]),
            ))
            n_trunk_only += 1

    if not parts:
        print("  Tree: no parts produced — skipped.")
        return None

    support = parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)

    print(f"\nSupport tree (local space): {len(groups_idx)} group(s) "
          f"from {len(regions)} region(s)")
    print(f"  trunk-only: {n_trunk_only}, trunk+leaf: {n_with_leaf}")
    if skipped_degenerate_z:
        print(f"  Skipped: {skipped_degenerate_z} degenerate Z (overhang too close to floor)")
    bb = support.bounds
    print(f"  Overall bounds: X[{bb[0,0]:.2f},{bb[1,0]:.2f}] "
          f"Y[{bb[0,1]:.2f},{bb[1,1]:.2f}] Z[{bb[0,2]:.2f},{bb[1,2]:.2f}]")
    print(f"  Total volume: {support.volume:.2f} mm³")
    _log_components(support, "after create_support_tree")

    if debug_export_path:
        try:
            support.export(debug_export_path, file_type="stl")
            print(f"  [debug] Tree mesh exported pre-subtract: {debug_export_path}")
        except Exception as e:
            print(f"  [debug] Tree export failed: {e}")

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


# ── Keel Gap Detection & Wedge Generation ────────────────────────────────────

def compute_keel_gap(mesh):
    """Return the minimum (Y+Z)_shifted across all mesh vertices.

    After slicer's trafo_centered shifts the mesh to Y_min=0, Z_min=0, the first
    oblique layer at virtual Z=layer_height×√2 intersects the diagonal plane
    Y+Z=0.283. If all vertices have Y+Z > 0.283, that layer is empty, Orca's
    m_belt_z_base jumps to the next layer, Z_gcode is zeroed at first print,
    and z_mach = Z − Y/√2 becomes negative → gate R11 FAIL (nozzle below belt).

    Large value (> 0.283) = keel gap → needs a keel wedge to fill layer 1.
    Value near 0 = mesh already touches keel corner (typical keel-first STL).
    """
    v = mesh.vertices
    y_min = float(v[:, 1].min())
    z_min = float(v[:, 2].min())
    return float(((v[:, 1] - y_min) + (v[:, 2] - z_min)).min())


def create_keel_wedge(mesh, height=2.83, x_margin=0.0):
    """Build a triangular-prism wedge that fills the mesh's keel corner.

    In local coords (before trafo_centered shift), the keel corner is at
    (X_any, Y_min, Z_min). The wedge occupies:
      - X: [X_min - x_margin, X_max + x_margin]  (spans mesh X extent)
      - Y: [Y_min, Y_min + height]               (one leg)
      - Z: [Z_min, Z_min + height]               (other leg)
      - Hypotenuse: Y+Z = Y_min + Z_min + height  (slanted face facing +Y+Z)

    When sliced on a 45° belt printer, this wedge guarantees non-empty slices
    in the first ⌊height / (layer_height·√2)⌋ virtual layers near the keel.
    The `height` matches `split_support_wedge`'s default (10 × 0.2 × √2 ≈ 2.83).
    """
    xmi = float(mesh.bounds[0, 0]) - x_margin
    xma = float(mesh.bounds[1, 0]) + x_margin
    ymi = float(mesh.bounds[0, 1])
    zmi = float(mesh.bounds[0, 2])
    V = np.array([
        [xmi, ymi,          zmi         ],  # 0: back-bottom
        [xma, ymi,          zmi         ],  # 1: front-bottom
        [xma, ymi + height, zmi         ],  # 2: front-ymax-bot
        [xmi, ymi + height, zmi         ],  # 3: back-ymax-bot
        [xma, ymi,          zmi + height],  # 4: front-bot-zmax
        [xmi, ymi,          zmi + height],  # 5: back-bot-zmax
    ])
    # Face winding chosen for outward normals (trimesh CCW = outward).
    F = np.array([
        [0, 2, 1], [0, 3, 2],        # -Z bottom (4 quad → 2 tri)
        [0, 1, 4], [0, 4, 5],        # -Y back
        [3, 5, 4], [3, 4, 2],        # hypotenuse (+Y+Z slant)
        [0, 5, 3],                   # -X side
        [1, 2, 4],                   # +X side
    ])
    return trimesh.Trimesh(vertices=V, faces=F, process=True)


# ── Support Wedge Split ───────────────────────────────────────────────────────

def split_support_wedge(support_local, wedge_height):
    """
    Split support_local into a solid base wedge (bottom) and main body (rest).

    wedge_height: Z height in local space for the base (≈ N_layers * layer_height * √2).

    Returns (support_wedge, support_main).
      - support_wedge: bottom portion with 100% infill → roots support to the belt.
      - support_main:  rest with sparse infill.

    If the support is shorter than wedge_height, the whole support becomes the
    wedge and support_main is None.
    """
    z_bot = float(support_local.bounds[0, 2])
    z_top = float(support_local.bounds[1, 2])
    z_split = z_bot + wedge_height

    _log_components(support_local, "split_support_wedge input (support_local)")

    if z_split >= z_top - 0.1:
        print(f"\nSupport wedge: entire support within wedge height ({z_bot:.2f}→{z_top:.2f}), "
              f"all solid infill.")
        _log_components(support_local, "split_support_wedge → wedge (all)")
        return support_local, None

    # Bounding box for the wedge region (same XY as support)
    cx = (support_local.bounds[0, 0] + support_local.bounds[1, 0]) / 2
    cy = (support_local.bounds[0, 1] + support_local.bounds[1, 1]) / 2
    dx = support_local.bounds[1, 0] - support_local.bounds[0, 0] + 2.0  # wider than support
    dy = support_local.bounds[1, 1] - support_local.bounds[0, 1] + 2.0
    wedge_dz = z_split - z_bot

    wedge_clip_box = trimesh.creation.box(
        extents=[dx, dy, wedge_dz + 0.01],
        transform=trimesh.transformations.translation_matrix(
            [cx, cy, z_bot + wedge_dz / 2]
        )
    )

    try:
        support_wedge = trimesh.boolean.intersection(
            [support_local, wedge_clip_box], engine="manifold"
        )
        support_main = trimesh.boolean.difference(
            [support_local, wedge_clip_box], engine="manifold"
        )
    except Exception as e:
        print(f"  Warning: wedge boolean failed ({e}) — no wedge split, using solid infill for whole support")
        return support_local, None

    if support_wedge is None or support_wedge.is_empty:
        print("  Warning: wedge intersection empty — no wedge base")
        _log_components(support_local, "split_support_wedge → main only (wedge empty)")
        return None, support_local

    if support_main is None or support_main.is_empty:
        print("  Note: support entirely within wedge height → all solid infill")
        _log_components(support_wedge, "split_support_wedge → wedge only (main empty)")
        return support_wedge, None

    print(f"\nSupport wedge split:")
    print(f"  Wedge (solid base):  Z[{z_bot:.2f}, {z_split:.2f}] = {wedge_dz:.2f}mm  "
          f"vol={support_wedge.volume:.1f}mm³")
    print(f"  Main (sparse):       Z[{z_split:.2f}, {z_top:.2f}]  "
          f"vol={support_main.volume:.1f}mm³")
    _log_components(support_wedge, "split_support_wedge → wedge")
    _log_components(support_main, "split_support_wedge → main")
    return support_wedge, support_main


# ── Boolean Helpers ───────────────────────────────────────────────────────────

def _log_components(mesh, label):
    """Debug: enumerate connected components with bounds + volume.

    Used to trace where individual support prisms (P0, P1, …) are lost
    across boolean ops (subtract, wedge split). A prism that exists in the
    `support_raw` body but vanishes after a boolean step is dropped here.
    """
    if mesh is None:
        print(f"  [{label}] <None>")
        return
    try:
        is_empty = bool(getattr(mesh, "is_empty", False))
    except Exception:
        is_empty = False
    if is_empty:
        print(f"  [{label}] <empty>")
        return
    try:
        comps = mesh.split(only_watertight=False)
    except Exception as e:
        print(f"  [{label}] split failed ({e}) — single body "
              f"faces={len(mesh.faces)} vol={mesh.volume:.2f}")
        return
    print(f"  [{label}] {len(comps)} component(s):")
    for i, c in enumerate(comps):
        b = c.bounds
        try:
            vol = c.volume
        except Exception:
            vol = float("nan")
        print(f"    P{i}: X=[{b[0,0]:+.2f},{b[1,0]:+.2f}] "
              f"Y=[{b[0,1]:+.2f},{b[1,1]:+.2f}] "
              f"Z=[{b[0,2]:+.2f},{b[1,2]:+.2f}] "
              f"vol={vol:.2f}")


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
    _log_components(support_raw, "before _subtract_model (support_raw)")
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
        _log_components(result, "after _subtract_model (support_clean)")
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
                           infill_density="25%", support_wedge_local=None):
    """
    Embed support into source_3mf and patch print settings for belt safety.

    Volumes in the output composite object:
      - Part 1 (model):        normal walls + infill
      - Part 3 (support):      wall_loops=0, no shells, sparse infill
      - Part 4 (support wedge, optional): 100% solid infill, no walls/shells
                               → roots support to belt, easy to detach

    All volumes share the same item transform → same belt pipeline.

    project_settings patched:
      - brim=no_brim          (prevents large Y in first layer → crash)
      - enable_support=0      (we provide explicit support geometry)
    """
    SUPPORT_OBJ_ID = 3
    SUPPORT_OBJ_FILE = "3D/Objects/support_part.model"
    SUPPORT_REL_ID = "rel-support"
    WEDGE_OBJ_ID = 4
    WEDGE_OBJ_FILE = "3D/Objects/support_wedge.model"
    WEDGE_REL_ID = "rel-support-wedge"

    with zipfile.ZipFile(source_3mf) as zin:
        files = {name: zin.read(name) for name in zin.namelist()}

    # ── 0. Normalize inline/flat → multi-sub-object ──────────────────────
    # Orca's "Save As 3MF" produces either:
    #   (a) a single inline <object id=N type="model"><mesh></object> with a
    #       <build><item objectid=N/>, OR
    #   (b) an inline-composite: one <object id=A><mesh></object> plus one
    #       <object id=B><components><component objectid="A"/></components>
    #       </object> (no p:path attributes — everything lives in the root
    #       3dmodel.model file).
    # The downstream support workflow expects multi-sub-object layout
    # (components carry p:path pointing at 3D/Objects/*.model). Convert both
    # (a) and (b) in place.
    model_xml = files["3D/3dmodel.model"].decode()
    already_multi = ("p:path=" in model_xml) and ("3D/_rels/3dmodel.model.rels" in files)
    if not already_multi:
        # Find the inline mesh-bearing object.
        m_inline = re.search(
            r'<object\s+id="(\d+)"[^>]*type="model"[^>]*>\s*(<mesh>.*?</mesh>)\s*</object>',
            model_xml, re.DOTALL)
        if not m_inline:
            raise ValueError("3dmodel.model has no inline <mesh> to extract")
        mesh_obj_id = int(m_inline.group(1))
        mesh_xml = m_inline.group(2)

        # Is there already a composite <object id=N><components></object>?
        m_comp = re.search(
            r'<object\s+id="(\d+)"[^>]*>\s*<components>.*?</components>\s*</object>',
            model_xml, re.DOTALL)
        if m_comp:
            composite_id_new = int(m_comp.group(1))
        else:
            composite_id_new = max(mesh_obj_id + 1, 2)

        sub_obj_id = 1                                 # fresh id inside sub-file
        sub_path = "3D/Objects/model_1.model"
        sub_uuid = str(uuid.uuid4())
        comp_uuid = str(uuid.uuid4())

        sub_model_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US"\n'
            '  xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"\n'
            '  xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">\n'
            ' <resources>\n'
            f' <object id="{sub_obj_id}" type="model">\n'
            f'  {mesh_xml}\n'
            f' </object>\n'
            ' </resources>\n'
            '</model>'
        )
        files[sub_path] = sub_model_xml.encode()

        # Rewrite: drop the inline mesh object AND any existing composite, then
        # insert a single new composite that references the sub-object via p:path.
        model_xml = re.sub(
            r'<object\s+id="\d+"[^>]*type="model"[^>]*>\s*<mesh>.*?</mesh>\s*</object>\s*',
            "", model_xml, count=1, flags=re.DOTALL)
        if m_comp:
            model_xml = re.sub(
                r'<object\s+id="\d+"[^>]*>\s*<components>.*?</components>\s*</object>\s*',
                "", model_xml, count=1, flags=re.DOTALL)

        composite_block = (
            f'  <object id="{composite_id_new}" p:UUID="{comp_uuid}" type="model">\n'
            f'   <components>\n'
            f'    <component p:path="/{sub_path}" objectid="{sub_obj_id}" '
            f'p:UUID="{sub_uuid}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
            f'   </components>\n'
            f'  </object>\n'
        )
        model_xml = re.sub(r'(</resources>)', composite_block + r' \1',
                           model_xml, count=1)

        # Point <build><item> to the composite id (may already be correct if (b)).
        model_xml = re.sub(
            r'(<item\s+objectid=")\d+(")', rf'\g<1>{composite_id_new}\g<2>',
            model_xml, count=1)

        # Ensure the production namespace is declared on <model>.
        if 'xmlns:p=' not in model_xml:
            model_xml = model_xml.replace(
                'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"',
                'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"\n'
                ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"',
                1)
        files["3D/3dmodel.model"] = model_xml.encode()

        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            f' <Relationship Target="/{sub_path}" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            '</Relationships>'
        )
        files["3D/_rels/3dmodel.model.rels"] = rels_xml.encode()

        # model_settings.config: keep <object id=composite_id_new> intact; if it
        # references the mesh-bearing id, rewrite to the new composite id.
        if "Metadata/model_settings.config" in files:
            ms = files["Metadata/model_settings.config"].decode()
            ms = re.sub(rf'<object\s+id="{mesh_obj_id}"(?=[\s>])',
                        f'<object id="{composite_id_new}"', ms, count=1)
            ms = re.sub(
                rf'(<metadata\s+key="object_id"\s+value=")'
                rf'{mesh_obj_id}(")',
                rf'\g<1>{composite_id_new}\g<2>', ms)
            files["Metadata/model_settings.config"] = ms.encode()

        print(f"  Inline/flat → multi-sub-object: extracted mesh to {sub_path}, "
              f"composite id={composite_id_new}")

    # ── 1. Parse 3dmodel.model: find composite object id ─────────────────
    model_xml = files["3D/3dmodel.model"].decode()
    m = re.search(r'<object\s+id="(\d+)"[^>]*>\s*<components>', model_xml)
    if not m:
        raise ValueError("No composite object with <components> in 3dmodel.model")
    composite_id = int(m.group(1))

    # ── 2. Inject support component(s) ────────────────────────────────────
    support_component = (
        f'    <component p:path="/{SUPPORT_OBJ_FILE}" '
        f'objectid="{SUPPORT_OBJ_ID}" '
        f'p:UUID="{uuid.uuid4()}" '
        f'transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
    )
    extra_components = support_component
    if support_wedge_local is not None:
        wedge_component = (
            f'    <component p:path="/{WEDGE_OBJ_FILE}" '
            f'objectid="{WEDGE_OBJ_ID}" '
            f'p:UUID="{uuid.uuid4()}" '
            f'transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
        )
        extra_components += f"\n   {wedge_component}"
    model_xml = model_xml.replace(
        "</components>",
        f"{extra_components}\n   </components>",
    )
    files["3D/3dmodel.model"] = model_xml.encode()

    # ── 3. Create support sub-object file(s) ──────────────────────────────
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
    if support_wedge_local is not None:
        files[WEDGE_OBJ_FILE] = _make_sub_model(support_wedge_local, WEDGE_OBJ_ID).encode()

    # ── 4. Update rels ────────────────────────────────────────────────────
    rels_xml = files["3D/_rels/3dmodel.model.rels"].decode()
    new_rels = (
        f' <Relationship Target="/{SUPPORT_OBJ_FILE}" '
        f'Id="{SUPPORT_REL_ID}" '
        f'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    )
    if support_wedge_local is not None:
        new_rels += (
            f'\n <Relationship Target="/{WEDGE_OBJ_FILE}" '
            f'Id="{WEDGE_REL_ID}" '
            f'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        )
    rels_xml = rels_xml.replace("</Relationships>",
                                f"{new_rels}\n</Relationships>")
    files["3D/_rels/3dmodel.model.rels"] = rels_xml.encode()

    # ── 5. Update model_settings.config ──────────────────────────────────
    settings_xml = files["Metadata/model_settings.config"].decode()

    inf_str = str(infill_density).rstrip("%") + "%"

    # rectilinear = single-direction lines per layer, alternating 90° between
    # adjacent layers. On the 45° oblique slice this maps to physically
    # crossed lines (1 layer = 1 belt sweep) → still rigid, but uses ~⅓ less
    # material than grid (which lays both directions every layer) and detaches
    # more cleanly from the model underside. Gyroid is FORBIDDEN here: it
    # touches the prior layer at only two sinusoid nodes per period, which
    # delaminates mid-print on belt geometry — HW failure 2026-04-23.
    support_part_xml = (
        f'    <part id="{SUPPORT_OBJ_ID}" subtype="normal_part">\n'
        f'      <metadata key="name" value="support"/>\n'
        f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
        f'      <metadata key="wall_loops" value="0"/>\n'
        f'      <metadata key="top_shell_layers" value="0"/>\n'
        f'      <metadata key="bottom_shell_layers" value="0"/>\n'
        f'      <metadata key="sparse_infill_density" value="{inf_str}"/>\n'
        f'      <metadata key="sparse_infill_pattern" value="rectilinear"/>\n'
        f'      <metadata key="enable_support" value="0"/>\n'
        f'      <mesh_stat edges_fixed="0" degenerate_facets="0" '
        f'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
        f'    </part>'
    )

    wedge_part_xml = ""
    if support_wedge_local is not None:
        wedge_part_xml = (
            f'\n    <part id="{WEDGE_OBJ_ID}" subtype="normal_part">\n'
            f'      <metadata key="name" value="support_wedge"/>\n'
            f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            f'      <metadata key="wall_loops" value="0"/>\n'
            f'      <metadata key="top_shell_layers" value="0"/>\n'
            f'      <metadata key="bottom_shell_layers" value="0"/>\n'
            f'      <metadata key="sparse_infill_density" value="100%"/>\n'
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
        + support_part_xml + wedge_part_xml + "\n  "
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

    n_parts = 3 if support_wedge_local is not None else 2
    print(f"\n{n_parts}-part 3MF written: {output_path}")
    print(f"  Object id={composite_id}: model(1) + support({SUPPORT_OBJ_ID})"
          + (f" + wedge({WEDGE_OBJ_ID})" if support_wedge_local is not None else ""))
    print(f"  Support (sparse {inf_str}): Z{support_local.bounds[:,2]}")
    if support_wedge_local is not None:
        print(f"  Wedge (solid 100%):        Z{support_wedge_local.bounds[:,2]}")


# ── STL → Orca multi-sub-object 3MF template ────────────────────────────────

def stl_to_orca_3mf_template(stl_path, out_3mf_path, object_name=None):
    """
    Build a minimal OrcaSlicer 3MF from an STL in the multi-sub-object format
    that export_3mf_two_volumes() consumes. The resulting 3MF has:
      - A composite object (id=2) with a single <component> referring to a
        sub-object .model file (id=1) that carries the mesh.
      - Metadata/model_settings.config listing the composite object with one
        <part id=1>.
      - Metadata/project_settings.config as an empty JSON shell (values get
        patched later by export_3mf_two_volumes).
      - All rels + [Content_Types] boilerplate.

    This bridges MCP/Orca's simple inline 3MF format (export) to the
    preprocessor's expected multi-sub-object layout — without requiring the
    user to manually re-export through a different path.
    """
    mesh = trimesh.load(str(stl_path), force="mesh")
    name = object_name or Path(stl_path).stem
    sub_file = f"3D/Objects/{name}_1.model"
    sub_obj_id = 1
    comp_obj_id = 2
    comp_uuid = str(uuid.uuid4())
    sub_uuid = str(uuid.uuid4())
    item_uuid = str(uuid.uuid4())
    build_uuid = str(uuid.uuid4())

    root_model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US"
 xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
 xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"
 xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
 requiredextensions="p">
 <metadata name="Application">ORCA_BELT support_preprocess.py</metadata>
 <resources>
  <object id="{comp_obj_id}" p:UUID="{comp_uuid}" type="model">
   <components>
    <component p:path="/{sub_file}" objectid="{sub_obj_id}" p:UUID="{sub_uuid}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>
   </components>
  </object>
 </resources>
 <build p:UUID="{build_uuid}">
  <item objectid="{comp_obj_id}" p:UUID="{item_uuid}" transform="1 0 0 0 1 0 0 0 1 0 0 0" printable="1"/>
 </build>
</model>'''

    sub_body = _mesh_to_xml_body(mesh, sub_obj_id)
    sub_model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US"
  xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
  xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">
 <resources>
{sub_body}
 </resources>
</model>'''

    rels_root = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>'''

    rels_model = f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/{sub_file}" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
 <Default Extension="config" ContentType="application/vnd.ms-package.text-plain-utf8"/>
 <Default Extension="json" ContentType="application/vnd.ms-package.text-plain-utf8"/>
</Types>'''

    # Minimal settings: composite object with 1 part for the model mesh.
    model_settings = f'''<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="{comp_obj_id}">
    <metadata key="name" value="{name}"/>
    <metadata key="extruder" value="1"/>
    <part id="{sub_obj_id}" subtype="normal_part">
      <metadata key="name" value="{name}"/>
      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>
      <mesh_stat edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>
    </part>
  </object>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value=""/>
    <metadata key="locked" value="false"/>
    <model_instance>
      <metadata key="object_id" value="{comp_obj_id}"/>
      <metadata key="instance_id" value="0"/>
    </model_instance>
  </plate>
</config>'''

    # Empty-ish JSON shell: export_3mf_two_volumes will patch brim/enable_support
    # via regex if these keys already exist. If the user later wants to impose a
    # real belt preset, they re-slice inside Orca which rewrites this file.
    project_settings = '{"brim_type":"no_brim","brim_width":"0","enable_support":"0"}'

    Path(out_3mf_path).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_3mf_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels_root)
        z.writestr("3D/3dmodel.model", root_model)
        z.writestr("3D/_rels/3dmodel.model.rels", rels_model)
        z.writestr(sub_file, sub_model)
        z.writestr("Metadata/model_settings.config", model_settings)
        z.writestr("Metadata/project_settings.config", project_settings)
    print(f"wrote template 3MF: {out_3mf_path} "
          f"({len(mesh.vertices)} verts, {len(mesh.faces)} faces)")
    return out_3mf_path


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

    # ORCA_BELT: apply belt-directional filter if the config says so. The
    # compound (STL) path plumbs the flag via the config dict — callers (e.g.
    # the test harness) can pass belt_directional=True in their overrides.
    if config.get("belt_directional") and overhang_mask.any():
        overhang_mask = filter_belt_directional(
            model, overhang_mask,
            xy_radius=float(config.get("belt_directional_radius", 2.0)),
            z_tolerance=float(config.get("belt_directional_ztol", 0.8)),
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
    parser.add_argument("--infill", default="15%",
                        help="Support infill density (default: 15%% — light, "
                             "easy detach. Pair with rectilinear pattern; "
                             "wedge stays at 100%% for keel adhesion)")
    parser.add_argument("--wedge-layers", type=int, default=10,
                        help="Solid-infill wedge base: N virtual layers (default: 10, "
                             "≈2.8mm at 0.2mm layer / 45°). Set 0 to disable.")
    parser.add_argument("--support-only", action="store_true",
                        help="Export only the support mesh as STL (debug)")
    parser.add_argument("--compound", action="store_true",
                        help="Legacy STL mode: fuse model+support into compound mesh")
    parser.add_argument("--belt-directional", action="store_true",
                        help="Belt printers only: drop support columns for overhangs that "
                             "are already self-supported by earlier-printed material carried "
                             "forward by the belt. Default OFF (opt-in, surgical). Can also "
                             "be enabled via 3MF project setting belt_directional_supports.")
    parser.add_argument("--belt-directional-radius", type=float, default=2.0,
                        help="XY proximity (mm) for belt-directional filter (default 2.0)")
    parser.add_argument("--belt-directional-ztol", type=float, default=0.8,
                        help="Z reach tolerance (mm) for belt-directional filter (default 0.8, "
                             "≈2× layer height)")
    parser.add_argument("--no-supports", action="store_true",
                        help="Skip overhang-support generation (only emit keel "
                             "wedge if keel gap is detected). Used by the GUI "
                             "auto-inject hook when the user toggles supports OFF "
                             "but the mesh still needs the keel-wedge fix.")
    # ── A4 v1 tree supports (opt-in, additive — box columns remain default) ──
    parser.add_argument("--tree", action="store_true",
                        help="Use tree-shaped supports (trunk + leaf cluster per "
                             "merged region group) instead of axis-aligned box "
                             "columns. Opt-in; default is box columns. Tunable via "
                             "--tree-* flags below.")
    parser.add_argument("--tree-trunk-w", type=float, default=4.0,
                        help="Tree trunk cross-section (mm, default 4.0). Trunk is "
                             "always W×W square.")
    parser.add_argument("--tree-merge-radius", type=float, default=2.0,
                        help="Merge two trunks into one if their XY centroids are "
                             "within this distance (mm, default 2.0). Set 0 to "
                             "disable merging.")
    parser.add_argument("--tree-leaf-shrink", type=float, default=0.7,
                        help="Leaf top width as a fraction of contact-polygon bbox "
                             "(default 0.7). Leaf is added only if it strictly "
                             "widens the trunk in at least one axis.")
    parser.add_argument("--tree-trunk-clearance", type=float, default=1.0,
                        help="Z-gap (mm) between trunk top and the leaf-bottom; the "
                             "leaf frustum spans this height (default 1.0).")
    parser.add_argument("--tree-debug-export", default=None,
                        help="If set, export the raw tree mesh to this path (.stl) "
                             "BEFORE the model boolean subtract — useful for "
                             "inspecting trunk/leaf geometry in MeshLab/trimesh.")
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

    # Plumb the CLI belt-directional flags into the config dict so both
    # make_compound_stl() (STL path) and the 3MF path see the same settings.
    # CLI args override 3MF project settings (base_overrides merged earlier).
    if args.belt_directional:
        config["belt_directional"] = True
    config["belt_directional_radius"] = args.belt_directional_radius
    config["belt_directional_ztol"] = args.belt_directional_ztol

    # ── Legacy STL compound mode ───────────────────────────────────────────
    if args.compound:
        compound, support = make_compound_stl(str(model_path), config)
        export_mesh(support if args.support_only and support else compound,
                    args.output)
        print("\nDone.")
        return

    # ── 3MF two-volume mode ────────────────────────────────────────────────
    # If the input is an STL, bridge it into the multi-sub-object 3MF format
    # this path expects (lets us ship a proper multi-part 3MF with per-part
    # settings — e.g. sparse_infill_pattern=grid for the support volume).
    if model_path.suffix.lower() == ".stl":
        bridged = Path(tempfile.gettempdir()) / (model_path.stem + "_bridged.3mf")
        stl_to_orca_3mf_template(str(model_path), str(bridged))
        model_path = bridged
    elif model_path.suffix.lower() != ".3mf":
        print("Error: two-volume mode requires a .3mf or .stl source.", file=sys.stderr)
        sys.exit(1)

    # Load model. NOTE: for 3MF, load_mesh_local now applies any non-identity
    # rotation from <item transform> so the returned mesh is in WORLD-rotated
    # space. All downstream geometry (overhang detection, support columns,
    # keel wedge) therefore also lives in WORLD-rotated space. Just before
    # writing the output 3MF we inverse-rotate the generated geometry back to
    # local coords — the 3MF's own <item transform> (copied from source_3mf)
    # will re-apply the rotation at load time, putting everything back into
    # the correct world position.
    model_local = load_mesh_local(str(model_path))
    item_R = model_local.metadata.get("item_rotation") \
             if hasattr(model_local, "metadata") else None
    item_t = model_local.metadata.get("item_translation") \
             if hasattr(model_local, "metadata") else None
    if item_R is None:
        item_R = np.eye(3)
    if item_t is None:
        item_t = np.zeros(3)
    has_rotation = not np.allclose(item_R, np.eye(3), atol=1e-6)
    has_translation = not np.allclose(item_t, 0, atol=1e-6)

    def _to_local(mesh):
        """Inverse-transform a world-space mesh back to 3MF local coords.

        p_world = p_local · R + t  →  p_local = (p_world − t) · R⁻¹
        """
        if mesh is None or (not has_rotation and not has_translation):
            return mesh
        m = mesh.copy()
        v = m.vertices - item_t if has_translation else m.vertices
        if has_rotation:
            v = v @ item_R.T  # R orthogonal, R.T == R⁻¹
        m.vertices = v
        return m

    # Adjust floor_z to the actual model bottom in local space.
    # DEFAULT_CONFIG floor_z=0.1 assumes Z_min=0. For models with Z_min≠0
    # (e.g. centered models with Z_min=-10), floor_z must be Z_min + 0.1
    # so the support column starts at the belt surface, not mid-model.
    z_min_local = float(model_local.bounds[0, 2])
    # bottom_z_gap (read from 3MF support_bottom_z_distance) lifts the support
    # floor off the bed. Default 0 = support sits on belt as before. >0 leaves
    # an air gap between belt and support body for easier detach. The wedge
    # (solid base) still bridges from the belt up to the support body floor,
    # so structural anchoring is preserved — only the body↔bed contact area
    # shrinks (driven by wedge layers count, not bottom_z_gap).
    bottom_lift = float(config.get("bottom_z_gap", 0.0))
    auto_floor_z = z_min_local + 0.1 + bottom_lift
    if abs(auto_floor_z - config["floor_z"]) > 0.01:
        print(f"  floor_z adjusted: {config['floor_z']} → {auto_floor_z:.3f} "
              f"(model Z_min={z_min_local:.3f}, bottom_z_gap={bottom_lift:.3f})")
        config["floor_z"] = auto_floor_z

    # Wedge layers: CLI default unless overridden by 3MF custom key.
    wedge_layers_eff = config.get("wedge_layers_override")
    if wedge_layers_eff is None:
        wedge_layers_eff = args.wedge_layers
    else:
        print(f"  wedge_layers: {args.wedge_layers} → {wedge_layers_eff}  (from 3MF belt_support_wedge_layers)")

    # ── Keel-gap detection ─────────────────────────────────────────────────
    # Compute min(Y+Z)_shifted. If > one virtual layer (0.283mm), the first
    # oblique slicing plane misses the mesh → m_belt_z_base gets set too high
    # → gate R11 FAIL. Fix: inject a keel wedge so layer 1 is non-empty.
    keel_gap_mm = compute_keel_gap(model_local)
    keel_wedge_height = (wedge_layers_eff if wedge_layers_eff > 0 else 10) \
                        * 0.2 * (2 ** 0.5)
    # Threshold: use a small numerical margin (not the full virtual-layer step).
    # A mesh with min(Y+Z)_shifted=0 is perfectly keel-first (no wedge needed).
    # Anything greater means the keel corner has no material exactly at it; the
    # first virtual layer's tiny slice may be too thin to produce extrusions.
    # Empirical rot090 case (0.281mm) fell BELOW the 0.283 step but the gate still
    # failed — so the threshold must be tighter than one virtual layer.
    KEEL_GAP_THRESHOLD = 0.05  # mm — within this margin the mesh effectively touches keel
    keel_wedge = None
    if keel_gap_mm > KEEL_GAP_THRESHOLD:
        print(f"\nKeel gap: {keel_gap_mm:.3f}mm > {KEEL_GAP_THRESHOLD:.3f}mm "
              f"(first virtual layer empty) — adding keel wedge.")
        keel_wedge = create_keel_wedge(model_local, height=keel_wedge_height)
        print(f"  Keel wedge: {keel_wedge_height:.2f}mm tall, "
              f"{keel_wedge.volume:.1f}mm³ at "
              f"Y[{model_local.bounds[0,1]:.2f},{model_local.bounds[0,1]+keel_wedge_height:.2f}] "
              f"Z[{model_local.bounds[0,2]:.2f},{model_local.bounds[0,2]+keel_wedge_height:.2f}]")
    else:
        print(f"\nKeel gap: {keel_gap_mm:.3f}mm (mesh contacts keel — no wedge needed).")

    if args.no_supports:
        print("\n--no-supports: skipping overhang detection "
              "(keel wedge will still be emitted if keel gap was detected).")
        overhang_mask = np.zeros(len(model_local.faces), dtype=bool)
    else:
        overhang_mask = detect_overhangs(
            model_local,
            threshold_angle=config["threshold_angle"],
            floor_z=config["floor_z"],
            min_area=config["min_area"],
        )

    # ORCA_BELT: optional belt-directional filter. CLI flag takes precedence;
    # 3MF project setting provides a fallback that survives re-slice. Default OFF.
    belt_directional_on = (
        args.belt_directional
        or bool(config.get("belt_directional", False))
    )
    if belt_directional_on and overhang_mask.any():
        overhang_mask = filter_belt_directional(
            model_local, overhang_mask,
            xy_radius=args.belt_directional_radius,
            z_tolerance=args.belt_directional_ztol,
        )

    if not overhang_mask.any() and keel_wedge is None:
        print("\nNo overhangs and no keel gap — copying source 3MF unchanged.")
        shutil.copy2(str(model_path), args.output)
        print(f"Copied: {args.output}")
        print("\nDone.")
        return

    if not overhang_mask.any() and keel_wedge is not None:
        # Keel-wedge only (no overhangs): emit 3MF with the wedge as the sole
        # solid volume — 100% infill, same pattern as support_wedge.
        print("\nNo overhangs but keel gap present — emitting keel wedge only.")
        export_3mf_two_volumes(
            source_3mf=str(model_path),
            support_local=_to_local(keel_wedge),
            output_path=args.output,
            infill_density="100%",
            support_wedge_local=None,
        )
        print("\nDone.")
        return

    if args.tree:
        support_raw = create_support_tree(
            model_local, overhang_mask,
            trunk_w=args.tree_trunk_w,
            merge_radius=args.tree_merge_radius,
            leaf_shrink=args.tree_leaf_shrink,
            trunk_clearance=args.tree_trunk_clearance,
            xy_gap=config["xy_gap"],
            z_gap=config["z_gap"],
            floor_z=config["floor_z"],
            debug_export_path=args.tree_debug_export,
        )
    else:
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

    # ── Wedge base: solid bottom N layers for belt adhesion ────────────────
    # Honor 3MF belt_support_wedge_layers override (resolved earlier as
    # wedge_layers_eff). 0 disables solid base entirely → minimal bed glue.
    support_wedge = None
    support_main = support_local
    if wedge_layers_eff > 0:
        # Virtual layer height at 45° = layer_height / cos(45°) = layer_height * √2
        # Default layer_height = 0.2mm → virtual = 0.283mm/layer
        wedge_height = wedge_layers_eff * 0.2 * (2 ** 0.5)
        print(f"\nWedge base: {wedge_layers_eff} layers × 0.283mm = {wedge_height:.2f}mm Z height")
        support_wedge, support_main = split_support_wedge(support_local, wedge_height)
        if support_main is None:
            # Entire support is wedge height — use as wedge, no sparse body
            support_wedge = support_local
            support_main = None  # export will use a dummy

    # Merge keel wedge into support_wedge if both exist (both are 100% infill
    # solid geometry rooted at the keel; Orca treats them as one volume).
    if keel_wedge is not None:
        if support_wedge is None:
            support_wedge = keel_wedge
            print(f"\nKeel wedge added as sole wedge volume ({keel_wedge.volume:.1f}mm³).")
        else:
            try:
                merged = trimesh.util.concatenate([support_wedge, keel_wedge])
                print(f"\nKeel wedge merged with support wedge: "
                      f"{support_wedge.volume:.1f}mm³ + {keel_wedge.volume:.1f}mm³ "
                      f"→ {merged.volume:.1f}mm³")
                support_wedge = merged
            except Exception as e:
                print(f"  Warning: wedge concatenation failed ({e}) — keeping support wedge only")

    # If wedge split consumed entire support, pass empty trimesh as support_local
    # (OrcaSlicer needs at least the wedge to be present)
    if support_main is None:
        # Only wedge — export wedge as sparse support (no separate wedge part)
        support_to_export = support_wedge
        wedge_to_export = None
        print("  Note: all support is wedge — exporting as single solid part")
    else:
        support_to_export = support_main
        wedge_to_export = support_wedge

    # Inverse-rotate generated meshes back to 3MF local coords. The item
    # transform in the output 3MF still has the rotation (copied unchanged
    # from source_3mf) and will re-rotate these sub-objects at load time.
    export_3mf_two_volumes(
        source_3mf=str(model_path),
        support_local=_to_local(support_to_export),
        output_path=args.output,
        infill_density=args.infill,
        support_wedge_local=_to_local(wedge_to_export),
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
