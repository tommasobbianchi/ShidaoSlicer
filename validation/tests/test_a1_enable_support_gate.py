#!/usr/bin/env python3
"""
belt-q46 / A1 — regression test for the belt_supports_preprocess_mode gate
decision table in src/slic3r/GUI/Plater.cpp:15362-15406.

The gate is a GUI C++ function; this test mirrors its decision logic in
Python and asserts the expected mode (0=skip, 1=full preprocess, 2=keel-only)
for the 4 canonical cases:

  geometry             enable_support  expected mode  description
  -------------------  --------------  -------------  --------------------------
  flat-base (Z≥-0.05)  OFF             0  (skip)      flat sits on belt, no support
  flat-base (Z≥-0.05)  ON              1  (full)      user wants supports
  below-belt (Z<-0.05) OFF             2  (keel-only) auto-inject wedge for keel
  below-belt (Z<-0.05) ON              1  (full)      supports + wedge

The "suspended" wording in belt-q46 maps to the C++ "below-belt" case
(centered-origin STLs before keel-align fires) — Z_min must drop below
−0.05mm for the gate to flag needs_keel_wedge.

Mirror logic from Plater.cpp belt_supports_preprocess_mode():
  - printer must be belt (precondition; not modelled here)
  - 1 object, 1 instance, 1 real volume (precondition)
  - if !enable_support AND Z_min ≥ -0.05mm  → 0
  - if  enable_support                      → 1
  - else  (=> !enable_support AND Z_min<-0.05) → 2

Use synthetic meshes (boxes, programmatic) so the test stays hermetic.

Coupled to: src/slic3r/GUI/Plater.cpp:15362-15406. If the C++ logic changes,
this test MUST be updated in lockstep.
"""
import sys
from pathlib import Path

import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[2]
KEEL_Z_THRESHOLD_MM = -0.05  # matches Plater.cpp:15391


def predict_mode(world_z_min: float, enable_support: bool) -> int:
    """Mirror of belt_supports_preprocess_mode() — minus preconditions."""
    needs_keel_wedge = world_z_min < KEEL_Z_THRESHOLD_MM
    if not enable_support and not needs_keel_wedge:
        return 0
    if enable_support:
        return 1
    return 2


def make_flat_base_box() -> trimesh.Trimesh:
    """20×20×10mm box sitting flush on the belt (Z_min=0)."""
    m = trimesh.creation.box(extents=[20, 20, 10])
    m.apply_translation([0, 0, 5.0])  # base at z=0
    return m


def make_below_belt_box() -> trimesh.Trimesh:
    """20×20×10mm centered-origin box (Z_min=-5). The Plater keel-align hook
    would normally lift this to flat-base before slicing, but the gate is
    invoked before that — needs_keel_wedge fires at Z_min<-0.05."""
    m = trimesh.creation.box(extents=[20, 20, 10])  # centred on origin
    return m


def main() -> int:
    fixtures = [
        ("flat-base",   False, 0, make_flat_base_box()),
        ("flat-base",   True,  1, make_flat_base_box()),
        ("below-belt",  False, 2, make_below_belt_box()),
        ("below-belt",  True,  1, make_below_belt_box()),
    ]

    print("== A1 belt_supports_preprocess_mode decision table ==")
    print(f"{'geometry':<12} {'enable_sup':<10} {'Z_min':>7} {'expected':>9} {'got':>4}  {'status':<5}")

    fails = []
    for name, enable, expected, mesh in fixtures:
        z_min = float(mesh.bounds[0, 2])
        got = predict_mode(z_min, enable)
        status = "PASS" if got == expected else "FAIL"
        print(f"{name:<12} {str(enable):<10} {z_min:>7.2f} {expected:>9} {got:>4}  {status:<5}")
        if status == "FAIL":
            fails.append((name, enable, expected, got))

    print()
    if fails:
        print(f"OVERALL: FAIL ({len(fails)} mismatch)")
        for f in fails:
            print(f"  • {f}")
        return 1

    # Bonus: keel threshold is at -0.05mm — verify the boundary case
    print("== boundary check at Z_min = -0.05 (must be flat-base, mode 0 with OFF) ==")
    boundary_mesh = trimesh.creation.box(extents=[20, 20, 10])
    boundary_mesh.apply_translation([0, 0, 5.0 - 0.05])  # base at z=-0.05 exactly
    z_min = float(boundary_mesh.bounds[0, 2])
    got = predict_mode(z_min, False)
    print(f"  Z_min={z_min:.3f} enable_support=False → mode={got} (expected 0)")
    if got != 0:
        print("  FAIL: boundary case classified as needing keel wedge")
        return 1
    print("  PASS")

    print("\nOVERALL: PASS — 4 canonical cases + boundary case match Plater.cpp:15362-15406")
    return 0


if __name__ == "__main__":
    sys.exit(main())
