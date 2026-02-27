#!/usr/bin/env python3
"""
Comprehensive test suite for support_preprocess.py
Generates 20 overhang models and validates the pre-processor on each.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh


TEST_DIR = Path(tempfile.mkdtemp(prefix="support_test_"))
SCRIPT = Path(__file__).parent / "support_preprocess.py"
CONFIG = Path(__file__).parent / "support.ini"

PASS = 0
FAIL = 0
RESULTS = []


def make_model(name, mesh_or_meshes):
    """Save mesh to STL and return path."""
    if isinstance(mesh_or_meshes, list):
        mesh = trimesh.boolean.union(mesh_or_meshes, engine="manifold")
    else:
        mesh = mesh_or_meshes
    path = TEST_DIR / f"{name}.stl"
    mesh.export(str(path))
    return path, mesh


def run_preprocess(stl_path, name):
    """Run support_preprocess.py and return (success, compound_path, output)."""
    out_path = TEST_DIR / f"{name}_compound.stl"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(stl_path), "-c", str(CONFIG), "-o", str(out_path)],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode == 0, out_path, result.stdout + result.stderr


def validate_compound(original_path, compound_path, name, expect_support):
    """Validate compound mesh properties."""
    global PASS, FAIL
    issues = []

    orig = trimesh.load(str(original_path), force="mesh")
    if not compound_path.exists():
        issues.append("compound file not created")
        FAIL += 1
        RESULTS.append((name, "FAIL", issues))
        return

    comp = trimesh.load(str(compound_path), force="mesh")

    # Volume check: compound should be >= original
    if comp.volume < orig.volume * 0.99:
        issues.append(f"compound volume ({comp.volume:.1f}) < original ({orig.volume:.1f})")

    if expect_support:
        # With support, compound should be larger than original
        if comp.volume <= orig.volume * 1.001:
            issues.append(f"expected support but compound volume ({comp.volume:.1f}) ≈ original ({orig.volume:.1f})")
    else:
        # No support expected, compound ≈ original
        if comp.volume > orig.volume * 1.1:
            issues.append(f"unexpected support: compound ({comp.volume:.1f}) >> original ({orig.volume:.1f})")

    # Bounds: compound Z min should be near 0 (or floor_z)
    if comp.bounds[0][2] < -0.01:
        issues.append(f"compound has negative Z: {comp.bounds[0][2]:.3f}")

    if issues:
        FAIL += 1
        RESULTS.append((name, "FAIL", issues))
    else:
        PASS += 1
        vol_ratio = comp.volume / orig.volume if orig.volume > 0 else 0
        RESULTS.append((name, "PASS", [f"vol ratio: {vol_ratio:.2f}"]))


def test_model(name, mesh_or_meshes, expect_support=True):
    """End-to-end: create model, run preprocessor, validate."""
    try:
        stl_path, _ = make_model(name, mesh_or_meshes)
        ok, comp_path, output = run_preprocess(stl_path, name)
        if not ok:
            global FAIL
            FAIL += 1
            RESULTS.append((name, "FAIL", [f"preprocessor returned error:\n{output[-200:]}"]))
            return
        validate_compound(stl_path, comp_path, name, expect_support)
    except Exception as e:
        FAIL += 1
        RESULTS.append((name, "FAIL", [f"exception: {e}"]))


def T(pos):
    """Translation matrix helper."""
    return trimesh.transformations.translation_matrix(pos)


# ── Model Generators ───────────────────────────────────────────────────────

def gen_01_inverted_L():
    """Classic L-shape: pillar + horizontal overhang."""
    pillar = trimesh.primitives.Box(extents=[5, 5, 15], transform=T([2.5, 2.5, 7.5]))
    overhang = trimesh.primitives.Box(extents=[10, 5, 5], transform=T([5, 2.5, 17.5]))
    return [pillar, overhang]


def gen_02_T_shape():
    """T-shape: central pillar with overhangs on both sides."""
    pillar = trimesh.primitives.Box(extents=[5, 5, 20], transform=T([10, 2.5, 10]))
    left = trimesh.primitives.Box(extents=[7, 5, 3], transform=T([3.5, 2.5, 18.5]))
    right = trimesh.primitives.Box(extents=[7, 5, 3], transform=T([16.5, 2.5, 18.5]))
    return [pillar, left, right]


def gen_03_bridge():
    """Two pillars with a bridge between them."""
    left = trimesh.primitives.Box(extents=[5, 5, 15], transform=T([2.5, 2.5, 7.5]))
    right = trimesh.primitives.Box(extents=[5, 5, 15], transform=T([22.5, 2.5, 7.5]))
    bridge = trimesh.primitives.Box(extents=[25, 5, 3], transform=T([12.5, 2.5, 16.5]))
    return [left, right, bridge]


def gen_04_cantilever():
    """Wall with a thin shelf extending outward."""
    wall = trimesh.primitives.Box(extents=[2, 20, 20], transform=T([1, 10, 10]))
    shelf = trimesh.primitives.Box(extents=[15, 20, 2], transform=T([9.5, 10, 15]))
    return [wall, shelf]


def gen_05_overhang_60deg():
    """Inverted stepped overhang: wider at top, creating overhangs."""
    base = trimesh.primitives.Box(extents=[10, 10, 5], transform=T([10, 5, 2.5]))
    step1 = trimesh.primitives.Box(extents=[15, 10, 5], transform=T([10, 5, 7.5]))
    step2 = trimesh.primitives.Box(extents=[20, 10, 5], transform=T([10, 5, 12.5]))
    return [base, step1, step2]


def gen_06_floating_cube():
    """Cube on a thin pillar — large overhang all around."""
    pillar = trimesh.primitives.Box(extents=[3, 3, 10], transform=T([10, 10, 5]))
    cube = trimesh.primitives.Box(extents=[15, 15, 5], transform=T([10, 10, 12.5]))
    return [pillar, cube]


def gen_07_arch():
    """Approximated arch: two pillars with angled blocks forming an arch."""
    left = trimesh.primitives.Box(extents=[5, 5, 15], transform=T([2.5, 2.5, 7.5]))
    right = trimesh.primitives.Box(extents=[5, 5, 15], transform=T([17.5, 2.5, 7.5]))
    cap = trimesh.primitives.Box(extents=[20, 5, 4], transform=T([10, 2.5, 17]))
    return [left, right, cap]


def gen_08_mushroom():
    """Cylinder on a thin stem — overhang cap."""
    stem = trimesh.primitives.Cylinder(radius=2, height=15,
                                        transform=T([10, 10, 7.5]))
    cap = trimesh.primitives.Cylinder(radius=10, height=3,
                                       transform=T([10, 10, 16.5]))
    return [stem, cap]


def gen_09_simple_cube():
    """Plain cube sitting on build plate — NO overhangs expected."""
    return trimesh.primitives.Box(extents=[10, 10, 10], transform=T([5, 5, 5]))


def gen_10_tall_pillar():
    """Tall thin pillar — NO overhangs (vertical walls only)."""
    return trimesh.primitives.Box(extents=[5, 5, 50], transform=T([2.5, 2.5, 25]))


def gen_11_double_cantilever():
    """Two cantilevers at different heights."""
    pillar = trimesh.primitives.Box(extents=[5, 5, 30], transform=T([2.5, 2.5, 15]))
    shelf1 = trimesh.primitives.Box(extents=[12, 5, 2], transform=T([8.5, 2.5, 11]))
    shelf2 = trimesh.primitives.Box(extents=[12, 5, 2], transform=T([8.5, 2.5, 24]))
    return [pillar, shelf1, shelf2]


def gen_12_cross():
    """Cross/plus shape with overhangs in 4 directions."""
    center = trimesh.primitives.Box(extents=[5, 5, 20], transform=T([10, 10, 10]))
    arm_x1 = trimesh.primitives.Box(extents=[7, 5, 3], transform=T([3.5, 10, 18.5]))
    arm_x2 = trimesh.primitives.Box(extents=[7, 5, 3], transform=T([16.5, 10, 18.5]))
    arm_y1 = trimesh.primitives.Box(extents=[5, 7, 3], transform=T([10, 3.5, 18.5]))
    arm_y2 = trimesh.primitives.Box(extents=[5, 7, 3], transform=T([10, 16.5, 18.5]))
    return [center, arm_x1, arm_x2, arm_y1, arm_y2]


def gen_13_spiral_steps():
    """Stacking offset boxes creating spiral overhangs."""
    meshes = []
    for i in range(5):
        x = 5 + i * 3
        y = 5 + i * 2
        z = i * 5 + 2.5
        meshes.append(trimesh.primitives.Box(extents=[10, 10, 5], transform=T([x, y, z])))
    return meshes


def gen_14_Y_shape():
    """Y shape: pillar splits into two angled branches at top."""
    pillar = trimesh.primitives.Box(extents=[6, 6, 15], transform=T([10, 10, 7.5]))
    branch_l = trimesh.primitives.Box(extents=[10, 6, 4], transform=T([5, 10, 17]))
    branch_r = trimesh.primitives.Box(extents=[10, 6, 4], transform=T([15, 10, 17]))
    return [pillar, branch_l, branch_r]


def gen_15_flat_roof():
    """Four pillars with a large flat roof — maximum overhang area."""
    p1 = trimesh.primitives.Box(extents=[3, 3, 15], transform=T([3, 3, 7.5]))
    p2 = trimesh.primitives.Box(extents=[3, 3, 15], transform=T([27, 3, 7.5]))
    p3 = trimesh.primitives.Box(extents=[3, 3, 15], transform=T([3, 27, 7.5]))
    p4 = trimesh.primitives.Box(extents=[3, 3, 15], transform=T([27, 27, 7.5]))
    roof = trimesh.primitives.Box(extents=[30, 30, 3], transform=T([15, 15, 16.5]))
    return [p1, p2, p3, p4, roof]


def gen_16_upside_down_pyramid():
    """Inverted pyramid — overhangs on all 4 slanting sides."""
    base = trimesh.primitives.Box(extents=[5, 5, 10], transform=T([10, 10, 5]))
    top = trimesh.primitives.Box(extents=[20, 20, 5], transform=T([10, 10, 12.5]))
    return [base, top]


def gen_17_hook():
    """Hook shape: vertical + horizontal + downward curve."""
    vert = trimesh.primitives.Box(extents=[4, 4, 20], transform=T([2, 2, 10]))
    horiz = trimesh.primitives.Box(extents=[12, 4, 4], transform=T([8, 2, 18]))
    tip = trimesh.primitives.Box(extents=[4, 4, 8], transform=T([12, 2, 14]))
    return [vert, horiz, tip]


def gen_18_stacked_overhangs():
    """Multiple overhangs at different Z levels."""
    base = trimesh.primitives.Box(extents=[8, 8, 5], transform=T([4, 4, 2.5]))
    oh1 = trimesh.primitives.Box(extents=[14, 8, 3], transform=T([7, 4, 6.5]))
    narrow = trimesh.primitives.Box(extents=[6, 8, 4], transform=T([3, 4, 10]))
    oh2 = trimesh.primitives.Box(extents=[16, 8, 3], transform=T([8, 4, 13.5]))
    return [base, oh1, narrow, oh2]


def gen_19_thin_bridge_long():
    """Very long thin bridge — stress test for many support prisms."""
    left = trimesh.primitives.Box(extents=[5, 5, 10], transform=T([2.5, 2.5, 5]))
    right = trimesh.primitives.Box(extents=[5, 5, 10], transform=T([47.5, 2.5, 5]))
    bridge = trimesh.primitives.Box(extents=[50, 5, 2], transform=T([25, 2.5, 11]))
    return [left, right, bridge]


def gen_20_sphere_on_pillar():
    """Sphere on a thin pillar — curved overhangs in all directions."""
    pillar = trimesh.primitives.Box(extents=[4, 4, 12], transform=T([10, 10, 6]))
    sphere = trimesh.primitives.Sphere(radius=8, center=[10, 10, 20])
    return [pillar, sphere]


# ── Main Test Runner ───────────────────────────────────────────────────────

def main():
    print(f"Test output directory: {TEST_DIR}\n")
    print("=" * 70)

    tests = [
        ("01_inverted_L",        gen_01_inverted_L(),        True),
        ("02_T_shape",           gen_02_T_shape(),           True),
        ("03_bridge",            gen_03_bridge(),            True),
        ("04_cantilever",        gen_04_cantilever(),        True),
        ("05_overhang_60deg",    gen_05_overhang_60deg(),    True),
        ("06_floating_cube",     gen_06_floating_cube(),     True),
        ("07_arch",              gen_07_arch(),              True),
        ("08_mushroom",          gen_08_mushroom(),          True),
        ("09_simple_cube",       gen_09_simple_cube(),       False),
        ("10_tall_pillar",       gen_10_tall_pillar(),       False),
        ("11_double_cantilever", gen_11_double_cantilever(), True),
        ("12_cross",             gen_12_cross(),             True),
        ("13_spiral_steps",      gen_13_spiral_steps(),      True),
        ("14_Y_shape",           gen_14_Y_shape(),           True),
        ("15_flat_roof",         gen_15_flat_roof(),         True),
        ("16_inverted_pyramid",  gen_16_upside_down_pyramid(), True),
        ("17_hook",              gen_17_hook(),              True),
        ("18_stacked_overhangs", gen_18_stacked_overhangs(), True),
        ("19_thin_bridge_long",  gen_19_thin_bridge_long(),  True),
        ("20_sphere_on_pillar",  gen_20_sphere_on_pillar(),  True),
    ]

    for name, mesh_data, expect_support in tests:
        print(f"\n{'─' * 70}")
        print(f"TEST: {name} (expect_support={expect_support})")
        print(f"{'─' * 70}")
        test_model(name, mesh_data, expect_support)

    # Summary
    print(f"\n{'=' * 70}")
    print(f"RESULTS: {PASS} PASS, {FAIL} FAIL out of {len(tests)}")
    print(f"{'=' * 70}")
    for name, status, details in RESULTS:
        detail_str = "; ".join(details)
        print(f"  [{status}] {name}: {detail_str}")

    print(f"\nTest files in: {TEST_DIR}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
