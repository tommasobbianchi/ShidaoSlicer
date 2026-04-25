#!/usr/bin/env python3
"""
Synthetic fixtures for the tree-supports unit tests (A4 v1).

Each fixture is a T-shape (or pair of T-shapes): a thin pillar holding a
flat plate. The plate's bottom face is the overhang the tree must support.

  X = belt width, Y = along-belt print direction, Z = vertical from belt.

Fixtures + expectations (with default --tree flags unless noted):

  1. single_overhang.stl
        Single T-shape: pillar (2x2x10) under a plate (10x10x1) at Z=[10,11].
        Expected: 1 region, 1 group (no merge possible), 1 trunk + 1 leaf.

  2. multi_far.stl
        Two T-shapes 30 mm apart along X. Each plate produces an overhang
        region; centroids are 30 mm apart so default merge_radius (2 mm)
        leaves them separate.
        Expected: 2 regions, 2 groups, 2 trunks + 2 leaves.

  3. multi_close.stl
        Two T-shapes whose plate XY centroids sit 3.5 mm apart (so they
        do NOT merge at the 2 mm default).
        Run the test with --tree-merge-radius 5 to force union: regions
        get fused into a single trunk + leaf at the average centroid.
        Expected (merge_radius=5): 2 regions, 1 group, 1 trunk + 1 leaf.
"""
from pathlib import Path

import trimesh

OUT = Path(__file__).parent


def box(center, size):
    return trimesh.primitives.Box(
        extents=size,
        transform=trimesh.transformations.translation_matrix(center))


def save(mesh, name):
    path = OUT / f"{name}.stl"
    mesh.export(path)
    print(f"wrote {path} -- V={len(mesh.vertices)} F={len(mesh.faces)} "
          f"bbox={mesh.bounds.tolist()}")


def single_overhang():
    return trimesh.util.concatenate([
        box((0.0, 0.0, 5.0), (2.0, 2.0, 10.0)),     # pillar
        box((0.0, 0.0, 10.5), (10.0, 10.0, 1.0)),   # plate
    ])


def multi_far():
    return trimesh.util.concatenate([
        # Left T-shape, plate centred at X=-15
        box((-15.0, 0.0, 5.0), (2.0, 2.0, 10.0)),
        box((-15.0, 0.0, 10.5), (10.0, 10.0, 1.0)),
        # Right T-shape, plate centred at X=+15
        box((+15.0, 0.0, 5.0), (2.0, 2.0, 10.0)),
        box((+15.0, 0.0, 10.5), (10.0, 10.0, 1.0)),
    ])


def multi_close():
    # Two plates whose XY centroids sit at X=-1.75 and X=+1.75 (distance
    # 3.5 mm). Default merge_radius=2.0 leaves them apart; running with
    # --tree-merge-radius 5 forces them into one trunk + leaf.
    return trimesh.util.concatenate([
        box((-1.75, 0.0, 5.0), (1.0, 1.0, 10.0)),
        box((-1.75, 0.0, 10.5), (2.5, 10.0, 1.0)),
        box((+1.75, 0.0, 5.0), (1.0, 1.0, 10.0)),
        box((+1.75, 0.0, 10.5), (2.5, 10.0, 1.0)),
    ])


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    save(single_overhang(), "single_overhang")
    save(multi_far(),       "multi_far")
    save(multi_close(),     "multi_close")
