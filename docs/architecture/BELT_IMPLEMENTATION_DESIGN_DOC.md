# Belt Printer Implementation Design Doc

**Role:** Senior C++ Engineer (Computational Geometry)
**Target:** OrcaSlicer Native Belt Support (CR-30 style, 45°)

## SECTION 1 — MATHEMATICAL MODEL (EXACT)

**1. Machine/G-code frame:**

- X : belt width axis
- Y : gantry axis (tilted by θ = 45° in the belt/vertical plane)
- Z : belt motion axis (“infinite Z”)

**2. Belt-slicer orthonormal frame:**

- X : belt width axis
- U : belt surface direction (forward along belt)
- V : belt surface normal (“height above belt”)

**Kinematic Mapping:**
U = Z + Y _ sin(θ)
V = Y _ cos(θ)

**Inverse Mapping (Slicer -> G-code):**
Y = V / cos(θ)
Z = U - V \* tan(θ)

For 45°:
Y = V \* √2
Z = U - V

**Invariant:** Slicing must occur on planes of constant V (Layer_k: V = k\*h).

**Clipping Boundary:**
U >= U0 + V \* tan(θ) (Ensures geometry is "above" the belt plane).

## SECTION 2 — PIPELINE BEHAVIOR

**Step 0: Import**

- Load mesh, correct bounds.

**Step 1: Placement**

- Translate so min(V) == 0.
- Add lead-in margin (Belt Anchor).

**Step 2: Adhesion**

- Belt-aware Anchor + Side Brims (offset on V=0).

**Step 3: Supports**

- Generate relative to +V (normal).
- CLIP against platform boundary (U >= U0 + V).

**Step 4: Slicing**

- Slice on constant V planes.
- **Strategy:** Pre-transform mesh to virtual upright space -> Slice -> Post-transform toolpaths.

**Step 5: Toolpaths**

- Standard perimeters/infill in slice plane.

**Step 6: G-code Emission**

- Convert (X,U,V) -> (X,Y,Z).
- Handle Infinite Z logic.

**Step 7: Preview**

- Render tilted bed and toolpaths.

## SECTION 3 — REFERENCE SOURCES

- **Kiri:Moto**: (GridSpace) - Belt mode, slice.z logic.
- **Cura Belt**: (BlackBelt/BirthT) - Rotate & Skew logic.
- **OrcaSlicer**: Upstream target.

## SECTION 4-6 — IMPLEMENTATION PLAN

(See Prompts in docs/runbook/ for discreet steps)
