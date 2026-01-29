# Prompt 4: Coordinate Transform Core

**Goal:** Implement the mathematical core for Belt printing transformations (Virtual Upright strategy) in OrcaSlicer.

## 1. Create New Files

- `src/libslic3r/BeltTransform.hpp`
- `src/libslic3r/BeltTransform.cpp`

## 2. Requirements

Implement a class `BeltTransform` with static methods:

1.  `Transform3d make_forward_transform(float angle_degrees)`:
    - Returns an Eigen Transform3d representing rotation by `-angle` around X (usually -45°).
    - This maps Model Space -> Virtual Slicing Space.

2.  `Vec3d inverse_transform_point(const Vec3d& virtual_pt, float angle_degrees)`:
    - Maps Virtual point (x, u, v) back to Machine point (X, Y, Z).
    - Formula (from Math Cert):
      $$ Y = v / \cos(\theta) $$
      $$ Z = u - v \cdot \tan(\theta) $$ (where u is Virtual Y, v is Virtual Z)

3.  `Transform3d make_inverse_transform(float angle_degrees)`:
    - Returns the 4x4 matrix for the above operation (Affine Shear).
    - Note: This might be non-rigid (shear), so use `Affine3d` if needed, but `Transform3d` usually handles affines.

## 3. Integration Plan

This class will be used later by `Model.cpp` (Forward) and `GCode.cpp` (Inverse).

## 4. Deliverable

- Completed `BeltTransform` class.
- Unit test or small verification main() to confirm $T \cdot T^{-1} \approx I$.
