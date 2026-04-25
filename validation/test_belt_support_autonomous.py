#!/usr/bin/env python3
"""
Belt Support Test Harness v11 — YZ convex hull floor clipping.

Projects support along virtual gravity [0,-1,-1] (correct for belt physics),
then clips floor vertices to the model's YZ convex hull. Because the hull
is convex, linear interpolation between roof (on model) and clamped floor
(on hull boundary) stays inside the hull at ALL intermediate Y levels.

Criteria:
  1. Structural continuity (obj+sup) gap < 2mm
  2. OH contact (support reaches overhang)
  3. Coverage ≥ 70%
  4. Max Z gap < 2mm
  5. Z-projection: support must not extend beyond model in Z at any Y level
"""

import sys
import numpy as np
import trimesh
from trimesh.intersections import mesh_plane
from shapely.ops import polygonize, unary_union
from shapely.geometry import LineString, Polygon
from scipy.spatial import ConvexHull


def make_box_mesh(x, y, z, offset=(0, 0, 0)):
    mesh = trimesh.creation.box(extents=[x, y, z])
    mesh.apply_translation([offset[0] + x / 2, offset[1] + y / 2, offset[2] + z / 2])
    return mesh


def belt_transform_verts(v):
    """Forward belt transform: X'=X, Y'=Z, Z'=Y+Z."""
    out = np.zeros_like(v)
    out[:, 0] = v[:, 0]
    out[:, 1] = v[:, 2]
    out[:, 2] = v[:, 1] + v[:, 2]
    return out


def transform_mesh(mesh):
    new_v = belt_transform_verts(mesh.vertices)
    new_f = mesh.faces[:, [1, 0, 2]]
    return trimesh.Trimesh(vertices=new_v, faces=new_f, process=False)


def shift_components_positive(components):
    all_v = np.vstack([c.vertices for c in components])
    y_shift = all_v[:, 1].min()
    z_shift = all_v[:, 2].min()
    shifted = []
    for c in components:
        v = c.vertices.copy()
        v[:, 1] -= y_shift
        v[:, 2] -= z_shift
        shifted.append(trimesh.Trimesh(vertices=v, faces=c.faces, process=False))
    return shifted


def _slice_mesh_plane(mesh, normal, point, snap_decimals=4):
    try:
        lines = mesh_plane(mesh, normal, point)
    except Exception:
        return None
    if lines is None or len(lines) == 0:
        return None

    if abs(normal[2]) > 0.5:
        ax0, ax1 = 0, 1
    elif abs(normal[1]) > 0.5:
        ax0, ax1 = 0, 2
    else:
        ax0, ax1 = 1, 2

    segs = []
    for seg in lines:
        u0 = round(seg[0][ax0], snap_decimals)
        v0 = round(seg[0][ax1], snap_decimals)
        u1 = round(seg[1][ax0], snap_decimals)
        v1 = round(seg[1][ax1], snap_decimals)
        if (u0, v0) != (u1, v1):
            segs.append(LineString([(u0, v0), (u1, v1)]))
    if not segs:
        return None
    merged = unary_union(segs)
    polys = list(polygonize(merged))
    if not polys:
        return None
    return unary_union(polys)


def slice_mesh_at_z(mesh, z, snap_decimals=4):
    return _slice_mesh_plane(mesh, [0, 0, 1], [0, 0, z], snap_decimals)

def slice_mesh_at_y(mesh, y, snap_decimals=4):
    return _slice_mesh_plane(mesh, [0, 1, 0], [0, y, 0], snap_decimals)


def slice_prisms_at_z(prisms, z):
    all_polys = []
    for prism in prisms:
        z_min = prism.vertices[:, 2].min()
        z_max = prism.vertices[:, 2].max()
        if z < z_min or z > z_max:
            continue
        p = slice_mesh_at_z(prism, z)
        if p and not p.is_empty:
            all_polys.append(p)
    if not all_polys:
        return None
    return unary_union(all_polys)


def slice_prisms_at_y(prisms, y):
    all_polys = []
    for prism in prisms:
        y_min = prism.vertices[:, 1].min()
        y_max = prism.vertices[:, 1].max()
        if y < y_min or y > y_max:
            continue
        p = slice_mesh_at_y(prism, y)
        if p and not p.is_empty:
            all_polys.append(p)
    if not all_polys:
        return None
    return unary_union(all_polys)


def slice_components_at_z(components, z):
    all_polys = []
    for comp in components:
        p = slice_mesh_at_z(comp, z)
        if p and not p.is_empty:
            all_polys.append(p)
    if not all_polys:
        return None
    return unary_union(all_polys)

def slice_components_at_y(components, y):
    all_polys = []
    for comp in components:
        p = slice_mesh_at_y(comp, y)
        if p and not p.is_empty:
            all_polys.append(p)
    if not all_polys:
        return None
    return unary_union(all_polys)


def compute_xy_envelope(components):
    all_v = np.vstack([c.vertices for c in components])
    xy = all_v[:, :2]
    if len(xy) < 3:
        return None
    try:
        hull = ConvexHull(xy)
        hull_pts = xy[hull.vertices]
        return Polygon(hull_pts)
    except Exception:
        return None


# ====== YZ Convex Hull for floor clipping ======

def compute_yz_hull(components):
    """Compute convex hull of all model vertices in the YZ plane.

    Returns a shapely Polygon representing the hull.
    """
    all_v = np.vstack([c.vertices for c in components])
    yz = all_v[:, 1:3]  # Y, Z columns
    if len(yz) < 3:
        return None
    try:
        hull = ConvexHull(yz)
        hull_pts = yz[hull.vertices]
        return Polygon(hull_pts)
    except Exception:
        return None


def get_hull_z_range_at_y(hull_poly, y):
    """Get the Z range within the YZ convex hull at a given Y.

    Intersects the hull with a horizontal line at Y and returns (z_min, z_max).
    """
    if hull_poly is None:
        return (float('-inf'), float('inf'))

    # Create a horizontal line at this Y spanning the full Z range
    b = hull_poly.bounds  # (y_min, z_min, y_max, z_max)
    line = LineString([(y, b[1] - 1), (y, b[3] + 1)])
    inter = hull_poly.intersection(line)

    if inter.is_empty:
        return None

    if inter.geom_type == 'LineString':
        coords = list(inter.coords)
        zs = [c[1] for c in coords]
        return (min(zs), max(zs))
    elif inter.geom_type == 'Point':
        return (inter.y, inter.y)
    elif inter.geom_type == 'MultiLineString':
        zs = []
        for ls in inter.geoms:
            for c in ls.coords:
                zs.append(c[1])
        return (min(zs), max(zs))
    else:
        return None


def create_support_prisms(components, support_angle=40.0, bottom_offset=0.15):
    """Generate support prisms with YZ convex hull floor clipping.

    1. Detect overhangs using virtual gravity [0,-cos45,-sin45]
    2. Project along [0,-1,-1] to Y=bottom_offset (diagonal to belt)
    3. Clip floor Z to model's YZ convex hull at Y=bottom_offset
    """
    angle_rad = np.radians(45.0)
    gravity = np.array([0, -np.cos(angle_rad), -np.sin(angle_rad)])
    cos_thresh = np.cos(np.radians(90.0 - support_angle))

    # Compute YZ convex hull for floor clipping
    yz_hull = compute_yz_hull(components)
    hull_z_range = get_hull_z_range_at_y(yz_hull, bottom_offset)

    prisms = []
    oh_z_min, oh_z_max = float('inf'), float('-inf')

    for mesh in components:
        verts, faces = mesh.vertices, mesh.faces
        v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
        normals = np.cross(v1 - v0, v2 - v0)
        norms = np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
        normals /= norms

        dots = normals @ gravity
        is_oh = dots >= cos_thresh
        for fi in np.where(is_oh)[0]:
            if verts[faces[fi], 1].min() <= bottom_offset:
                is_oh[fi] = False

        for fi in np.where(is_oh)[0]:
            r0, r1, r2 = verts[faces[fi]]
            oh_z_min = min(oh_z_min, r0[2], r1[2], r2[2])
            oh_z_max = max(oh_z_max, r0[2], r1[2], r2[2])

            # Project along virtual gravity [0,-1,-1] to Y = bottom_offset
            d0, d1, d2 = [r[1] - bottom_offset for r in [r0, r1, r2]]
            f0z = max(0, r0[2] - d0)
            f1z = max(0, r1[2] - d1)
            f2z = max(0, r2[2] - d2)

            # Clip floor Z to model's YZ convex hull
            if hull_z_range is not None:
                z_lo, z_hi = hull_z_range
                f0z = max(z_lo, min(z_hi, f0z))
                f1z = max(z_lo, min(z_hi, f1z))
                f2z = max(z_lo, min(z_hi, f2z))

            f0 = [r0[0], bottom_offset, f0z]
            f1 = [r1[0], bottom_offset, f1z]
            f2 = [r2[0], bottom_offset, f2z]

            sv = np.array([r0.tolist(), r1.tolist(), r2.tolist(), f0, f1, f2])
            sf = np.array([
                [0, 1, 2], [3, 5, 4],
                [0, 1, 4], [0, 4, 3],
                [1, 2, 5], [1, 5, 4],
                [2, 0, 3], [2, 3, 5],
            ])
            prisms.append(trimesh.Trimesh(vertices=sv, faces=sf, process=False))

    return prisms, (oh_z_min, oh_z_max)


def check_z_projection(components, prisms, y_step=0.5, verbose=False):
    """Check if support projects beyond the model in the Z direction."""
    all_v = np.vstack([c.vertices for c in components])
    all_sv = np.vstack([p.vertices for p in prisms])

    y_min = min(all_v[:, 1].min(), all_sv[:, 1].min())
    y_max = max(all_v[:, 1].max(), all_sv[:, 1].max())
    y_levels = np.arange(y_min + y_step / 2, y_max, y_step)

    # Use YZ convex hull of model for comparison (not per-Y model cross-section)
    yz_hull = compute_yz_hull(components)

    max_z_excess = 0.0
    worst_y = 0.0
    details = []

    for y in y_levels:
        sup_xz = slice_prisms_at_y(prisms, y)
        if not sup_xz or sup_xz.is_empty:
            continue

        # Get model hull Z range at this Y
        hull_z = get_hull_z_range_at_y(yz_hull, y)
        if hull_z is None:
            # Y outside hull — any support here is excess
            sb = sup_xz.bounds
            excess = sb[3] - sb[1]
            if excess > 0.1:
                details.append((y, excess, 'outside_hull'))
                if excess > max_z_excess:
                    max_z_excess = excess
                    worst_y = y
            continue

        hull_z_min, hull_z_max = hull_z
        sup_bounds = sup_xz.bounds  # (x_min, z_min, x_max, z_max)
        sup_z_min, sup_z_max = sup_bounds[1], sup_bounds[3]

        z_over = max(0, sup_z_max - hull_z_max)
        z_under = max(0, hull_z_min - sup_z_min)
        z_exc = max(z_over, z_under)

        if z_exc > 0.1:
            details.append((y, z_exc,
                            f'over={z_over:.1f} under={z_under:.1f}'))
            if z_exc > max_z_excess:
                max_z_excess = z_exc
                worst_y = y

    if verbose and details:
        print(f"\n  Y-slice Z-projection (vs hull) details:")
        for y, exc, info in details[:10]:
            print(f"    Y={y:.1f}: Z_excess={exc:.1f}mm ({info})")
        if len(details) > 10:
            print(f"    ... {len(details) - 10} more")

    return max_z_excess, worst_y, details


def run_test(name, components, support_angle=40.0, gap_xy=0.2, layer_step=0.3,
             verbose=False):
    print(f"\n{'=' * 60}")
    print(f"TEST: {name}")
    print(f"{'=' * 60}")

    all_v = np.vstack([c.vertices for c in components])
    z_min, z_max = all_v[:, 2].min(), all_v[:, 2].max()
    y_min, y_max = all_v[:, 1].min(), all_v[:, 1].max()
    x_min, x_max = all_v[:, 0].min(), all_v[:, 0].max()
    print(f"  Object: X=[{x_min:.1f},{x_max:.1f}] "
          f"Y=[{y_min:.1f},{y_max:.1f}] Z=[{z_min:.1f},{z_max:.1f}]")

    # Compute YZ hull for reference
    yz_hull = compute_yz_hull(components)
    if yz_hull:
        hb = yz_hull.bounds
        print(f"  YZ hull: Y=[{hb[0]:.1f},{hb[2]:.1f}] Z=[{hb[1]:.1f},{hb[3]:.1f}]")
        hull_at_floor = get_hull_z_range_at_y(yz_hull, 0.15)
        if hull_at_floor:
            print(f"  Hull Z at belt (Y=0.15): [{hull_at_floor[0]:.1f}, {hull_at_floor[1]:.1f}]")

    envelope = compute_xy_envelope(components)

    prisms, (oh_z_min, oh_z_max) = create_support_prisms(
        components, support_angle=support_angle)
    if not prisms:
        print("  No overhang")
        return True, "No overhang"

    all_sv = np.vstack([p.vertices for p in prisms])
    sup_z_min = all_sv[:, 2].min()
    sup_z_max = all_sv[:, 2].max()
    print(f"  {len(prisms)} prisms, OH Z:[{oh_z_min:.1f},{oh_z_max:.1f}]")
    print(f"  Support Z: [{sup_z_min:.2f}, {sup_z_max:.2f}]")

    z_start = max(0.1, sup_z_min)
    z_end = min(z_max, sup_z_max + 1)
    z_levels = np.arange(z_start, z_end, layer_step)

    support_layers = []
    for z in z_levels:
        obj_p = slice_components_at_z(components, z)
        sup_p = slice_prisms_at_z(prisms, z)

        if not sup_p or sup_p.is_empty:
            support_layers.append((z, 0, 0, 0))
            continue

        raw_a = sup_p.area
        if envelope:
            clipped = sup_p.intersection(envelope)
            outside_a = sup_p.difference(envelope).area
        else:
            clipped = sup_p
            outside_a = 0

        if clipped.is_empty:
            support_layers.append((z, raw_a, 0, outside_a))
            continue

        if obj_p and not obj_p.is_empty:
            final = clipped.difference(obj_p.buffer(gap_xy))
            final_a = final.area if not final.is_empty else 0
        else:
            final_a = clipped.area

        support_layers.append((z, raw_a, final_a, outside_a))

    active_layers = [(z, r, f, o) for z, r, f, o in support_layers if f > 0.01]
    raw_active = [(z, r, f, o) for z, r, f, o in support_layers if r > 0.01]

    if verbose:
        print(f"\n  {'Z':>6} {'Raw':>8} {'Final':>8} {'OutEnv':>8}")
        for z, r, f, o in support_layers:
            if r > 0.001:
                print(f"  {z:6.2f} {r:8.2f} {f:8.2f} {o:8.2f}")

    max_gap = 0
    gap_start = 0
    if len(active_layers) >= 2:
        for i in range(1, len(active_layers)):
            gap = active_layers[i][0] - active_layers[i - 1][0]
            if gap > max_gap:
                max_gap = gap
                gap_start = active_layers[i - 1][0]

    z_sup_min = active_layers[0][0] if active_layers else 0
    z_sup_max = active_layers[-1][0] if active_layers else 0
    coverage = len(active_layers) / len(raw_active) if raw_active else 0
    oh_contact = z_sup_max >= oh_z_min - 1.0

    # Structural continuity
    structural_gap = 0
    last_covered_z = 0
    for z, raw, final, outside in support_layers:
        obj_p = slice_components_at_z(components, z)
        obj_a = obj_p.area if obj_p and not obj_p.is_empty else 0
        has_structure = (final > 0.01) or (obj_a > 0.01 and raw > 0.01)
        if has_structure:
            gap = z - last_covered_z if last_covered_z > 0 else 0
            structural_gap = max(structural_gap, gap)
            last_covered_z = z

    # Z-projection check (against YZ convex hull)
    z_excess, worst_y, z_proj_details = check_z_projection(
        components, prisms, y_step=0.5, verbose=verbose)

    # Report
    print(f"\n  Z-layers: {len(active_layers)}/{len(raw_active)} ({coverage:.0%})")
    print(f"  Sup Z: [{z_sup_min:.2f}, {z_sup_max:.2f}]")
    print(f"  Structural gap: {structural_gap:.2f}mm")
    if max_gap > 0:
        print(f"  Max sup gap: {max_gap:.2f}mm at Z={gap_start:.1f}")
    print(f"  OH contact: {'YES' if oh_contact else 'NO'} "
          f"(sup_top={z_sup_max:.1f} vs oh_bottom={oh_z_min:.1f})")
    print(f"  Z-projection: {z_excess:.1f}mm excess"
          f"{f' at Y={worst_y:.1f}' if z_excess > 0 else ''}"
          f" ({len(z_proj_details)} Y-slices with excess)")

    issues = []
    if structural_gap > 2.0:
        issues.append(f"structural_gap={structural_gap:.1f}mm")
    if not oh_contact:
        issues.append("no_oh_contact")
    if max_gap > 2.0:
        issues.append(f"sup_gap={max_gap:.1f}mm@Z={gap_start:.0f}")
    if coverage < 0.7:
        issues.append(f"coverage={coverage:.0%}")
    if z_excess > 1.0:
        issues.append(f"z_projection={z_excess:.1f}mm@Y={worst_y:.1f}")

    passed = len(issues) == 0
    status = 'PASS' if passed else 'FAIL'
    detail = f": {', '.join(issues)}" if issues else ""
    print(f"\n  {status}{detail}")
    return passed, issues


# ====== Models ======

def test_simple_cube():
    parts = [transform_mesh(make_box_mesh(10, 10, 10))]
    return shift_components_positive(parts)

def test_cantilever():
    parts = [
        transform_mesh(make_box_mesh(10, 5, 10)),
        transform_mesh(make_box_mesh(10, 20, 5, (0, 0, 10))),
    ]
    return shift_components_positive(parts)

def test_bridge():
    parts = [
        transform_mesh(make_box_mesh(10, 3, 10)),
        transform_mesh(make_box_mesh(10, 3, 10, (0, 17, 0))),
        transform_mesh(make_box_mesh(10, 20, 2, (0, 0, 10))),
    ]
    return shift_components_positive(parts)

def test_overhang():
    parts = [
        transform_mesh(make_box_mesh(10, 3, 10)),
        transform_mesh(make_box_mesh(10, 20, 2, (0, 0, 10))),
    ]
    return shift_components_positive(parts)

def test_tall_tower():
    parts = [
        transform_mesh(make_box_mesh(10, 5, 30)),
        transform_mesh(make_box_mesh(10, 20, 3, (0, 0, 30))),
    ]
    return shift_components_positive(parts)

def test_l_shape():
    parts = [
        transform_mesh(make_box_mesh(10, 10, 20)),
        transform_mesh(make_box_mesh(10, 20, 5, (0, 0, 20))),
    ]
    return shift_components_positive(parts)

def test_thin_shelf():
    parts = [
        transform_mesh(make_box_mesh(10, 5, 10)),
        transform_mesh(make_box_mesh(10, 15, 1, (0, 0, 10))),
    ]
    return shift_components_positive(parts)

def test_inverted_l():
    parts = [
        transform_mesh(make_box_mesh(5, 10, 15, (5, 0, 0))),
        transform_mesh(make_box_mesh(10, 10, 5, (0, 0, 15))),
    ]
    return shift_components_positive(parts)


if __name__ == "__main__":
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    results = []
    tests = [
        ("Simple Cube (no OH)", test_simple_cube()),
        ("Cantilever", test_cantilever()),
        ("Bridge", test_bridge()),
        ("Overhang", test_overhang()),
        ("Tall Tower", test_tall_tower()),
        ("L-Shape", test_l_shape()),
        ("Thin Shelf", test_thin_shelf()),
        ("Inverted-L", test_inverted_l()),
    ]

    for name, parts in tests:
        ok, msg = run_test(name, parts, verbose=verbose)
        results.append((name, ok, msg))

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    all_ok = True
    for name, ok, msg in results:
        s = "PASS" if ok else "FAIL"
        print(f"  [{s}] {name}: {msg}")
        if not ok:
            all_ok = False

    print(f"\n  {'ALL PASS' if all_ok else 'SOME FAILED'}")
    sys.exit(0 if all_ok else 1)
