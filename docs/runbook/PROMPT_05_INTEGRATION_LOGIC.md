# Prompt 5: Core Integration (Placement & GCode)

**Goal:** Integrate the Belt Transformations into the Placement logic (Model) and G-Code Generation logic.

## 1. Helper Function

In `src/libslic3r/PrintConfig.cpp` (or similar), ensure we can easily query `printer_is_belt` and `belt_angle` from `PrintConfig` or `GCodeConfig`. (Done in Prompt 3).

## 2. Model Placement (Forward Transform)

**Target File:** `src/libslic3r/Model.cpp` or `ModelInstance` logic.

**Task:**

- Locate where the Model Instance transformation is calculated.
- If `print_config.printer_is_belt` is true, chain the `BeltTransform::make_forward_transform(angle)` matrix _after_ the user's rotation/scaling.
- **Effect:** The object appears on the angled belt in the 3D view (if visualization supports it), but more importantly, the Slicer receives the geometry rotated by -45 degrees (so Z layers become vertical slices).
- **Verify:** The "Down" surface of the model should align with the Belt Plane.

## 3. G-Code Generation (Inverse Transform)

**Target File:** `src/libslic3r/GCode.cpp`

**Task:**

- Identify the main loop where layers are processed and paths are generated (e.g., `GCode::process_layer`, `GCode::do_export`).
- Identify where coordinate points (`Point` or `Vec3d`) are passed to the `GCodeWriter` (functions like `travel_to`, `extrude_to`).
- Inject the Inverse Transformation:
  ```cpp
  if (is_belt) {
      // Map Virtual Point (x, y, z_layer) -> Machine Point (X, Y_belt, Z_head)
      Vec3d machine_pt = BeltTransform::inverse_transform_point(virtual_pt, angle);
      // Use machine_pt for G-code output
  }
  ```
- **Crucial:** Ensure this applies to ALL moves (travel, extrusion, wipe, etc.).
- **Warning:** `Z` in GCode.cpp usually comes from `layer->slice_z` or `z_layer`. `X/Y` come from the paths.

## 4. Deliverable

- Modified `Model.cpp` (or relevant placement logic).
- Modified `GCode.cpp` (with transformation hooks).
