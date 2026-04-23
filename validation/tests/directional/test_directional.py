#!/usr/bin/env python3
"""
Unit test harness for the belt-directional support filter.

Runs each fixture through the preprocessor TWICE — once without the filter
(baseline cartesian behaviour) and once with --belt-directional — and counts
the number of connected overhang regions that survive into the support-box
generation stage. Compares against expected values.

No slicer required. No printer required. Pure Python, fast.

Expected behaviour (see validation/tests/directional/generate_fixtures.py
for the geometry rationale):

  fixture          baseline  directional
  forward_shadow     1            0       (upper cube dropped — belt delivers base top)
  backward_gap       1            1       (no prior roof reachable)
  mixed              2            1       (+Y dropped, -Y kept)

Run:
    python3 validation/tests/directional/test_directional.py

Exit 0 on pass, 1 on any mismatch.
"""
from pathlib import Path
import sys

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO / "validation"))

import trimesh
from support_preprocess import (detect_overhangs, _overhang_regions,
                                filter_belt_directional)


EXPECTED = {
    # name           : (baseline_regions, directional_regions)
    "forward_shadow" : (1, 0),
    "backward_gap"   : (1, 1),
    "mixed"          : (2, 1),
}


def count_regions(mesh, mask):
    return sum(1 for _ in _overhang_regions(mesh, mask))


def run(name, expect_base, expect_dir):
    path = HERE / f"{name}.stl"
    if not path.exists():
        print(f"FAIL {name}: fixture STL missing at {path}")
        print(f"  → run: python3 {HERE}/generate_fixtures.py")
        return False

    mesh = trimesh.load(str(path), force="mesh")

    # Baseline — cartesian gravity, no directional filter
    mask_base = detect_overhangs(mesh, 50.0, 0.1, 1.0)
    n_base = count_regions(mesh, mask_base)

    # Directional — same detection, filter applied
    mask_dir = filter_belt_directional(mesh, mask_base.copy())
    n_dir = count_regions(mesh, mask_dir)

    ok_base = (n_base == expect_base)
    ok_dir  = (n_dir  == expect_dir)

    status = "PASS" if (ok_base and ok_dir) else "FAIL"
    print(f"[{status}] {name}: base={n_base} (expect {expect_base})  "
          f"directional={n_dir} (expect {expect_dir})")
    return ok_base and ok_dir


def main():
    print("=" * 60)
    print("Belt-directional filter unit tests")
    print("=" * 60)
    all_ok = True
    for name, (eb, ed) in EXPECTED.items():
        all_ok &= run(name, eb, ed)
        print()
    print("=" * 60)
    if all_ok:
        print("All tests PASS.")
        return 0
    print("Some tests FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
