# File Map Report: Belt Implementation

**Generated:** 2026-01-29
**Status:** Discovery Complete

## 1. OrcaSlicer Target Files (Verified)

These are the canonical files in OrcaSlicer where the belt logic must be injected.

| Responsibility      | File Path                                   | Class / Function (Target)                       |
| :------------------ | :------------------------------------------ | :---------------------------------------------- |
| **Placement**       | `src/libslic3r/Model.cpp`                   | `ModelInstance::transform_polygon`, `arrange()` |
| **Configuration**   | `src/libslic3r/PrintConfig.cpp`             | `DynamicPrintConfig`                            |
| **Slicing Core**    | `src/libslic3r/PrintObject.cpp`             | `PrintObject::slice()`, `make_perimeters()`     |
| **G-Code Emission** | `src/libslic3r/GCode.cpp`                   | `GCode::do_export()`, `GCodeWriter::write()`    |
| **Supports**        | `src/libslic3r/Support/SupportMaterial.cpp` | `generate_support_material()`                   |
| **Brims**           | `src/libslic3r/Brim.cpp`                    | `make_brim()`                                   |
| **Wipe Tower**      | `src/libslic3r/GCode/WipeTower2.cpp`        | `WipeTower::tool_change()`                      |

## 2. Reference Implementation Findings

### A. Kiri:Moto (GridSpace)

**Location:** `deps_ref/grid-apps/src/kiri/run/worker.js`
**Logic:**

- **Pre-Rotate:** "belt mode rotate widgets 45 degrees on X axis before slicing".
- **Concept:** Simplifies the slicing engine by presenting it with already-rotated geometry, effectively slicing "flat" relative to the belt plane.
- **Adhesion:** Uses `proc.beltAnchor` and `firstLayerBeltLead` for lead-in logic.

### B. Cura Belt Plugin (BirthT/BeltPrinterSlicing)

**Location:** `deps_ref/BeltPrinterSlicing/*.py`
**Logic:**

- **Patching:** Heavy patching of Cura's action pipeline (`PatchedCuraActions.py`, `ProcessSlicedLayersJob.py`).
- **Post-Process:** Seems to rely significantly on transforming coordinates _after_ slicing or intercepting the slice job setup.
- **Build Volume:** Modifies bounds via `BuildVolumePatches.py`.

## 3. Architecture Decision for Orca

Based on the Kiri:Moto finding (Pre-Rotate), we will adopt the **Virtual Upright Slicing** strategy for Orca:

1.  **Transform**: Create a `BeltTransform` utility (Prompt 6).
2.  **Pre-Process**: Transform Model Instances to "Virtual Upright" space (V) before slicing.
3.  **Slice**: Run standard Orca slicing on V (constant Z planes).
4.  **Post-Process**: Transform toolpaths back to Machine space (P) during G-code emission.

## 4. Next Step

Execute **Prompt 2**: Extract exact math from Cura/Kiri references.
