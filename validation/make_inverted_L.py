#!/usr/bin/env python3
"""Generate an inverted-L STL for belt printer support testing.

The inverted L has:
- A vertical leg (right side): 5mm wide, 20mm tall, 10mm deep
- A horizontal shelf (top): 10mm wide, 5mm tall, 10mm deep

The shelf overhangs to the left, requiring support underneath.

    ┌──────────┐
    │  shelf   │  z=15..20, x=0..10
    │          │
    └────┐     │
         │ leg │  z=0..15, x=5..10
         │     │
         └─────┘

In belt printing (45° keel-first), the support under the shelf should
follow gravity = (0, -1, -1) in virtual space, NOT be perpendicular
to slicing planes.
"""

import numpy as np
from stl import mesh

def make_box(x0, y0, z0, x1, y1, z1):
    """Create a box mesh from two corners."""
    vertices = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],  # bottom
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],  # top
    ])
    # 12 triangles (2 per face)
    faces = np.array([
        [0,3,1], [1,3,2],  # bottom
        [4,5,7], [5,6,7],  # top
        [0,1,5], [0,5,4],  # front
        [2,3,7], [2,7,6],  # back
        [0,4,7], [0,7,3],  # left
        [1,2,6], [1,6,5],  # right
    ])
    m = mesh.Mesh(np.zeros(12, dtype=mesh.Mesh.dtype))
    for i, f in enumerate(faces):
        for j in range(3):
            m.vectors[i][j] = vertices[f[j]]
    return m

def make_inverted_L():
    """Create inverted-L shape."""
    # Vertical leg: x=[5,10], y=[0,10], z=[0,15]
    leg = make_box(5, 0, 0, 10, 10, 15)
    # Horizontal shelf: x=[0,10], y=[0,10], z=[15,20]
    shelf = make_box(0, 0, 15, 10, 10, 20)
    # Combine
    combined = mesh.Mesh(np.concatenate([leg.data, shelf.data]))
    return combined

if __name__ == '__main__':
    import sys
    outpath = sys.argv[1] if len(sys.argv) > 1 else '/home/user/projects/ORCA_BELT/validation/test_models/inverted_L.stl'
    m = make_inverted_L()
    m.save(outpath)
    print(f"Saved inverted-L to {outpath}")
    print(f"  Leg:   x=[5,10] y=[0,10] z=[0,15]")
    print(f"  Shelf: x=[0,10] y=[0,10] z=[15,20]")
    print(f"  Overhang: x=[0,5] under shelf at z=15")
