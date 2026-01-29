# Calibration Tests Adaptation for Belt Printing

This report details the technical implementation and rationale behind the adaptations made to Orca Slicer's calibration suite for belt-style 3D printers (Infinite-Z).

## 1. The Challenge
Belt printers slice models at an angle (typically 45°) relative to the build plate. This poses two significant challenges for standard calibration tests:
1.  **Geometric Instability**: Standard calibration models (like Temp Towers or Flow Rate boxes) would be sliced diagonally, leaving only a thin line of contact with the belt on the first layer, leading to detachment.
2.  **Kinematic Complexity**: In "True Oblique Slicing", every layer contains segments that are in direct contact with the belt. Standard slicer logic only applies "Initial Layer" settings to the very first slice (Z=0 in slice space), which is insufficient for belt adhesion.

## 2. Geometric Adaptations
To solve the stability issue, we implemented a dynamic mesh adaptation in `CalibUtils.cpp`.

### Model Rotation
Calibration models are automatically rotated by the `belt_angle` around the X-axis. This aligns the intended "bottom" of the test with the angled belt surface.

### The Stabilizing Wedge
For every calibration model, we now generate a **Triangular Prism (Wedge)** that is appended to the base.
- **Function**: It provides a large, flat contact area with the belt.
- **Dimensions**: The wedge width matches the model width, and its height is calculated to transition from the belt surface to the start of the actual calibration geometry.

## 3. Adhesion-Aware Toolpaths
We modified the G-code generation pipeline in `GCode.cpp` to ensure that segments touching the belt are printed with optimal settings, regardless of which "layer" they belong to.

### `is_on_belt_bed` Logic
Modified the `GCode` class to include a robust check:
```cpp
bool GCode::is_on_belt_bed(const Point& p) {
    if (!m_config.belt_printer) return false;
    // Transform slice-space point to machine-space
    // A point is on the bed if its machine Y-coordinate is near 0
}
```

### Speed & Temperature
When `is_on_belt_bed` returns true:
- **Speed**: The slicer overrides the current feature speed with `initial_layer_speed`.
- **Temperature**: (Planned refinement) Ensures the nozzle maintains initial layer temperature for these segments to maximize fusion with the belt.

## 4. Test Case Specifics

| Test Type | Adaptation | Benefit |
| :--- | :--- | :--- |
| **Flow Rate** | Rotated boxes + Wedge | Boxes stay attached; flow is measured on the 45° face. |
| **Temp Tower** | Rotated tower + Wedge | Prevents the tower from toppling during high-Z moves. |
| **Pressure Advance** | Linear projection | Lines are projected onto the belt surface (Machine Y=0). |
| **VFA / Retraction** | Rotated cylinders + Wedge | Ensures vertical features are tested along the belt's motion axis. |

## 5. Summary of Modified Files
- `CalibUtils.cpp` / `CalibUtils.hpp`: Added `adapt_model_for_belt` and integrated it into all `calib_*` functions.
- `GCode.cpp` / `GCode.hpp`: Implemented `is_on_belt_bed` and speed override logic.
- `calib.cpp`: Refined manual G-code generation for PA lines to account for belt transforms.

## 6. Verification Status
- **Geometric Correctness**: Verified via code audit of the `TriangleMesh` operations.
- **Build Status**: All changes are compiled and included in the latest `orca-slicer` binary.
- **Remaining**: Visual verification of the wedge structure in the GUI slice preview.
