# Prompt 2: Math Extraction & Validation

**Goal:** Extract the exact belt printer transform logic from Cura belt plugin and Kiri:Moto to VALIDATE our proposed Shear Logic.

## 1. Cura Belt Plugin Extraction

Analyze `deps_ref/BeltPrinterSlicing` files (found in Recon):

- `BeltPrinterSlicing/ThirdParty/win/trimesh/creation.py` (check transforms)
- `BeltPrinterSlicing/ProcessSlicedLayersJob.py` (check post-processing)

**Task:**

1.  Identify gravity direction (usually +Y in rotated frame).
2.  Extract the rotation matrix used (is it exactly 45° X-axis?).
3.  Check for "Infinity Z" handling (how G-code coordinates are emitted).

## 2. Kiri:Moto Extraction

Analyze `deps_ref/grid-apps/src/kiri/run/worker.js` (and search for `belt.slope` or `tan`).

**Task:**

1.  Confirm if they use `Rotation` or `Shear`.
2.  Extract the bounding box clipping logic (how do they decide `fitsOnBed`?).

## 3. Deliverable: Math Spec Update

Update `docs/architecture/01_SHEAR_TRANSFORM_LOGIC.md` (or create `02_MATH_VALIDATION.md` if diff is large) with:

- Confirmed Forward Transform (Model -> Slice).
- Confirmed Inverse Transform (Slice -> G-code).
- Confirmed Bed Boundary Equation (U >= ...).

**Outcome:** A certified mathematical model ready for C++ implementation.
