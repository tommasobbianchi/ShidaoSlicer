#!/usr/bin/env python3
"""
belt_support_3d.py — Generate belt support as a 3D mesh using trimesh.

1. Load model in MODEL space
2. Analyze overhangs using belt gravity vector
3. Create a monoblock support solid filling from belt surface to overhangs
4. Subtract model (with gap)
5. Slice the support solid at each virtual-Z layer
6. Export support mesh for visualization / validation

Usage:
    python3 validation/belt_support_3d.py model.stl [--export support.stl] [--verbose]
"""

import trimesh
import numpy as np
import sys
import os


def load_model(path):
    """Load model mesh. Handles STL and extracts from 3MF."""
    if path.endswith(".3mf"):
        # Extract STL from 3MF
        import zipfile
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith(".model") or name.endswith(".stl"):
                    # Try to find the model file
                    pass
            # trimesh can load 3MF directly
            scene = trimesh.load(path)
            if isinstance(scene, trimesh.Scene):
                # Combine all geometries
                meshes = list(scene.geometry.values())
                if meshes:
                    return trimesh.util.concatenate(meshes)
            return scene
    return trimesh.load(path, force='mesh')


def analyze_belt_overhangs(mesh, belt_angle_deg=45):
    """
    Find overhang faces relative to belt gravity.

    Belt gravity in model space: [0, -sin(θ), -cos(θ)]
    (gravity pulls toward belt surface, which is at Y*sin(θ) + Z*cos(θ) = 0)

    A face is overhang if its normal opposes gravity (faces downward in belt frame).
    """
    theta = np.radians(belt_angle_deg)
    # Belt gravity in model space: objects fall toward the belt
    # Belt normal is [0, sin(θ), cos(θ)], gravity is opposite
    belt_gravity = np.array([0, -np.sin(theta), -np.cos(theta)])

    # Face normals dot belt_gravity: positive = face looks "down" (overhang)
    dots = mesh.face_normals.dot(belt_gravity)

    # Overhang faces: normal has significant component along gravity
    overhang_threshold = 0.3  # cos(~72°) — moderate overhang
    overhang_mask = dots > overhang_threshold

    # Keel faces: face is parallel to belt surface (strong overhang)
    keel_mask = dots > 0.9

    return {
        "belt_gravity": belt_gravity,
        "overhang_faces": np.where(overhang_mask)[0],
        "keel_faces": np.where(keel_mask)[0],
        "n_overhang": int(overhang_mask.sum()),
        "n_keel": int(keel_mask.sum()),
        "dot_products": dots,
    }


def create_support_monoblock(mesh, overhang_info, belt_angle_deg=45, gap_mm=0.5):
    """
    Create a 3D support monoblock in MODEL space.

    Strategy:
    1. Find the bounding box of overhang faces
    2. Create a solid from the belt surface up to the overhang region
    3. Boolean subtract the model (expanded by gap)

    The support solid is a prism that fills the void between
    the belt surface and the arm's underside.
    """
    theta = np.radians(belt_angle_deg)
    belt_gravity = overhang_info["belt_gravity"]
    overhang_faces = overhang_info["overhang_faces"]

    if len(overhang_faces) == 0:
        print("  No overhang faces found!")
        return None

    # Get overhang face vertices
    overhang_triangles = mesh.faces[overhang_faces]
    overhang_vertices = mesh.vertices[overhang_triangles.flatten()]

    # Bounding box of overhang region
    oh_min = overhang_vertices.min(axis=0)
    oh_max = overhang_vertices.max(axis=0)

    print(f"  Overhang region:")
    print(f"    X: [{oh_min[0]:.2f}, {oh_max[0]:.2f}]")
    print(f"    Y: [{oh_min[1]:.2f}, {oh_max[1]:.2f}]")
    print(f"    Z: [{oh_min[2]:.2f}, {oh_max[2]:.2f}]")

    # Model bounds
    m_min = mesh.bounds[0]
    m_max = mesh.bounds[1]
    print(f"  Model bounds:")
    print(f"    X: [{m_min[0]:.2f}, {m_max[0]:.2f}]")
    print(f"    Y: [{m_min[1]:.2f}, {m_max[1]:.2f}]")
    print(f"    Z: [{m_min[2]:.2f}, {m_max[2]:.2f}]")

    # Belt surface plane in model space: Y*sin(θ) + Z*cos(θ) = 0
    # Support needs to fill from this plane up to the overhang region.
    #
    # For a 45° belt: belt plane is Y + Z = 0 (after normalization).
    # The model sits above this plane (Y + Z > 0).
    #
    # The support volume fills from the belt plane to the overhang faces,
    # projected along the belt gravity direction.

    # Simple approach: create a box from belt surface to overhang max,
    # then subtract the model.

    # In virtual space (after forward transform [0,1;1,1]):
    #   Y_virt = Z_model
    #   Z_virt = Y_model + Z_model
    # Belt surface is at Z_virt = 0, i.e., Y_model + Z_model = 0
    # Support fills from Y_virt = 0 to Y_virt = overhang_max
    # at each Z_virt level.

    # But we work in MODEL space. The support solid needs to:
    # - Start at the belt surface (Y + Z = 0 plane)
    # - Extend up to the overhang region
    # - Span the full X range

    # Create support as a triangular prism in model space.
    # Cross-section in Y-Z plane: triangle from belt to overhang.

    # The arm's overhang underside is approximately at:
    #   Z_arm_bottom = oh_min[2]  (lowest Z of overhang faces)
    #   Y range of arm: [oh_min[1], oh_max[1]]

    # Support needs to fill the space between belt and arm.
    # In model space, this is a wedge shape:
    #   At Y = oh_min[1] (near model): support goes from Z=0 to Z=oh_min[2]
    #   At Y = oh_max[1] (far from model): support goes from Z=0 to Z=oh_min[2]
    #   Actually, the arm is at constant Z range, so it's simpler.

    # Simplest correct approach: create a BOX that covers:
    #   X: [model_min_x, model_max_x]
    #   Y: [model_min_y, overhang_max_y]
    #   Z: [0, overhang_max_z]
    # Then subtract the model.

    # But this doesn't account for the belt's 45° angle.
    # The belt surface is at Y + Z = 0, not Z = 0.

    # For belt printing, the "floor" is the belt plane.
    # Support must reach from the overhang down to this plane.

    # Create a box in virtual space, then inverse-transform to model space.
    # Virtual space box: X=[m_min_x, m_max_x], Y=[0, oh_Y_max_virt], Z=[0, max_Z_virt]
    # Then transform to model space.

    # Actually, let's just create the support solid directly.
    # The support fills from Y_virt=0 (belt) to the bottom of the overhang.

    # Transform overhang bounds to virtual space:
    # Y_virt = Z_model, Z_virt = Y_model + Z_model
    oh_Y_virt_min = oh_min[2]  # Z_model
    oh_Y_virt_max = oh_max[2]
    oh_Z_virt_min = oh_min[1] + oh_min[2]  # Y_model + Z_model
    oh_Z_virt_max = oh_max[1] + oh_max[2]

    print(f"\n  Overhang in virtual space:")
    print(f"    Y_virt: [{oh_Y_virt_min:.2f}, {oh_Y_virt_max:.2f}]")
    print(f"    Z_virt: [{oh_Z_virt_min:.2f}, {oh_Z_virt_max:.2f}]")

    # Model in virtual space:
    m_Y_virt_min = m_min[2]
    m_Y_virt_max = m_max[2]
    m_Z_virt_min = m_min[1] + m_min[2]
    m_Z_virt_max = m_max[1] + m_max[2]

    print(f"  Model in virtual space:")
    print(f"    Y_virt: [{m_Y_virt_min:.2f}, {m_Y_virt_max:.2f}]")
    print(f"    Z_virt: [{m_Z_virt_min:.2f}, {m_Z_virt_max:.2f}]")

    # Support solid in VIRTUAL space:
    # A box from Y_virt=0 (belt) to Y_virt=oh_Y_virt_max (arm top)
    # spanning Z_virt = [m_Z_virt_min, m_Z_virt_max] and X = [m_min_x, m_max_x]

    margin = 0.1  # small margin
    box_min = np.array([m_min[0] - margin, 0.0, m_Z_virt_min])
    box_max = np.array([m_max[0] + margin, oh_Y_virt_max + margin, m_Z_virt_max + margin])

    support_box_virt = trimesh.creation.box(
        extents=box_max - box_min,
        transform=trimesh.transformations.translation_matrix((box_min + box_max) / 2)
    )

    print(f"\n  Support box (virtual space):")
    print(f"    X: [{box_min[0]:.2f}, {box_max[0]:.2f}]")
    print(f"    Y_virt: [{box_min[1]:.2f}, {box_max[1]:.2f}]")
    print(f"    Z_virt: [{box_min[2]:.2f}, {box_max[2]:.2f}]")

    # Transform model to virtual space for boolean subtraction
    # Forward transform: X'=X, Y'=Z, Z'=Y+Z
    model_virt_vertices = np.column_stack([
        mesh.vertices[:, 0],      # X' = X
        mesh.vertices[:, 2],      # Y' = Z
        mesh.vertices[:, 1] + mesh.vertices[:, 2],  # Z' = Y + Z
    ])
    model_virt = trimesh.Trimesh(vertices=model_virt_vertices, faces=mesh.faces.copy())

    # Expand model by gap for clearance
    # Simple approach: just use the model as-is with gap handled later
    # For proper gap, we'd need to offset the mesh, which is complex.
    # Instead, we'll shrink the support box slightly or handle gap in slicing.

    print(f"\n  Boolean: support_box - model...")
    try:
        support_solid = support_box_virt.difference(model_virt)
        if support_solid is None or support_solid.is_empty:
            print("  Boolean result is empty!")
            return None
        print(f"  Support solid: {len(support_solid.vertices)} vertices, "
              f"{len(support_solid.faces)} faces")
        print(f"  Volume: {support_solid.volume:.2f} mm³")
    except Exception as e:
        print(f"  Boolean failed: {e}")
        print("  Falling back to support box without model subtraction")
        support_solid = support_box_virt

    return support_solid


def slice_support(support_mesh, z_levels):
    """Slice the support mesh at given Z_virt levels, return per-layer polygons."""
    if support_mesh is None:
        return {}

    sections = {}
    for z in z_levels:
        try:
            section = support_mesh.section(plane_origin=[0, 0, z],
                                           plane_normal=[0, 0, 1])
            if section is not None:
                # Get 2D path
                path_2d, _ = section.to_planar()
                sections[z] = {
                    "area": float(sum(abs(p.area) for p in path_2d.polygons_full)),
                    "bounds": path_2d.bounds.tolist() if path_2d.bounds is not None else None,
                    "n_polygons": len(path_2d.polygons_full),
                }
        except Exception:
            pass

    return sections


def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") \
                 else "inverted_L.3mf"
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    export_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--export" and i + 1 < len(sys.argv):
            export_path = sys.argv[i + 1]

    model_path = os.path.abspath(model_path)
    print(f"Model: {os.path.basename(model_path)}")

    # Step 1: Load model
    print("\n=== LOADING MODEL ===")
    mesh = load_model(model_path)
    print(f"  Vertices: {len(mesh.vertices)}, Faces: {len(mesh.faces)}")
    print(f"  Watertight: {mesh.is_watertight}")
    print(f"  Bounds: {mesh.bounds[0]} to {mesh.bounds[1]}")

    # Step 2: Analyze overhangs
    print("\n=== OVERHANG ANALYSIS ===")
    oh = analyze_belt_overhangs(mesh, belt_angle_deg=45)
    print(f"  Overhang faces: {oh['n_overhang']} / {len(mesh.faces)}")
    print(f"  Keel faces: {oh['n_keel']}")

    if oh['n_overhang'] == 0:
        print("  No overhangs detected — no support needed.")
        return

    # Step 3: Create support monoblock
    print("\n=== CREATING SUPPORT MONOBLOCK ===")
    support = create_support_monoblock(mesh, oh, belt_angle_deg=45, gap_mm=0.5)

    if support is None:
        print("  Failed to create support.")
        return

    # Step 4: Slice support at virtual Z levels
    print("\n=== SLICING SUPPORT ===")
    # Generate Z levels matching slicer (0.283mm step for belt)
    z_step = 0.2828  # virtual Z step for 0.2mm belt-normal layer height
    z_min = 0.2828
    z_max = support.bounds[1][2] if support.bounds is not None else 30.0
    z_levels = np.arange(z_min, z_max, z_step)

    sections = slice_support(support, z_levels)
    print(f"  Sliced at {len(z_levels)} Z levels, got {len(sections)} non-empty sections")

    if sections:
        z_keys = sorted(sections.keys())
        for z in z_keys[:5]:
            s = sections[z]
            print(f"    Z={z:7.3f}: area={s['area']:8.2f} polys={s['n_polygons']}")
        if len(z_keys) > 10:
            print(f"    ... ({len(z_keys) - 10} more) ...")
        for z in z_keys[-5:]:
            s = sections[z]
            print(f"    Z={z:7.3f}: area={s['area']:8.2f} polys={s['n_polygons']}")

    # Step 5: Export
    if export_path:
        print(f"\n=== EXPORTING ===")
        support.export(export_path)
        print(f"  Saved to {export_path}")
        print(f"  Vertices: {len(support.vertices)}, Faces: {len(support.faces)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
