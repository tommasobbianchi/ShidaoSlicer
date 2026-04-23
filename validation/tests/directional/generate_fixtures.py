#!/usr/bin/env python3
"""
Synthetic fixtures for the belt-directional filter unit tests.

Belt physics (same convention as support_preprocess.py):
  X = belt width, Y = along-belt print direction (+Y = print forward),
  Z = vertical from belt, virt_Z = Y + Z is the print-order axis.
  Material deposited at earlier virt_Z is carried forward in +Y by the
  belt, so at the moment a later-virt_Z layer is printed, the prior
  material has slid under the nozzle if X and Z align.

The filter's predicate per overhang region: "is there a NON-overhang
face (roof) at the same X and same Z, with strictly earlier virt_Z?".
The fixtures below are designed so each overhang is ONE connected
region (create_support_box generates ONE box per region) and the
expected outcome is known for each.

Fixtures:
  1. forward_shadow.stl  — base cube + upper cube stepped in +Y.
     Upper overhang region has a roof (base top) at same X,Z with
     smaller virt_Z → DROPPED by directional.
  2. backward_gap.stl    — mirror: upper cube stepped in -Y. No roof
     at smaller virt_Z aligned with the upper bottom → KEPT.
  3. mixed.stl           — base + TWO upper cubes (one +Y, one -Y).
     Two disjoint overhang regions. Directional drops +Y, keeps -Y.
     Proves the filter is selective, not all-or-nothing.
"""
from pathlib import Path
import numpy as np
import trimesh

OUT = Path(__file__).parent


def box(center, size):
    return trimesh.primitives.Box(
        extents=size,
        transform=trimesh.transformations.translation_matrix(center))


def save(mesh, name):
    path = OUT / f"{name}.stl"
    mesh.export(path)
    print(f"wrote {path} — V={len(mesh.vertices)} F={len(mesh.faces)} "
          f"bbox={mesh.bounds.tolist()}")


def forward_shadow():
    # Base at Y=[-5,5], Z=[0,10]. Upper at Y=[5,15], Z=[10,20].
    # Upper bottom face: centroid X=0, Z=10, virt_Z_R = 5+10 = 15.
    # Base top face center: (0, 0, 10), virt_Z = 10.
    # |X|=0<=2, |Z-10|=0<=0.8, 10 < 15 − 0.4 → DROPPED.
    return trimesh.util.concatenate([
        box((0.0, 0.0, 5.0), (10.0, 10.0, 10.0)),
        box((0.0, 10.0, 15.0), (10.0, 10.0, 10.0)),
    ])


def backward_gap():
    # Upper at Y=[-15,-5], Z=[10,20]. virt_Z_R = -15+10 = -5.
    # Base top face center virt_Z = 10 NOT < -5.4 → no prior roof → KEPT.
    return trimesh.util.concatenate([
        box((0.0, 0.0, 5.0), (10.0, 10.0, 10.0)),
        box((0.0, -10.0, 15.0), (10.0, 10.0, 10.0)),
    ])


def mixed():
    # Two overhang regions, one dropped + one kept.
    return trimesh.util.concatenate([
        box((0.0, 0.0, 5.0), (10.0, 10.0, 10.0)),
        box((0.0, 10.0, 15.0), (10.0, 10.0, 10.0)),
        box((0.0, -10.0, 15.0), (10.0, 10.0, 10.0)),
    ])


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    save(forward_shadow(), "forward_shadow")
    save(backward_gap(),   "backward_gap")
    save(mixed(),          "mixed")
