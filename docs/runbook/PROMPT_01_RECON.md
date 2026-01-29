# Prompt 1: Repo Acquisition & "Map the Battlefield"

**Goal:** Implement CR-30 style 45° belt printer kinematics in OrcaSlicer (C++), by extracting belt slicing transform logic from (A) Kiri:Moto and (B) Cura belt plugin.

## 1. Repo Acquisition

Clone the reference implementations locally for analysis:

- **Kiri:Moto**: Clone `https://github.com/GridSpace/grid-apps`
- **Cura Belt Plugin**: Clone `https://github.com/BirthT/BeltPrinterSlicing`

## 2. OrcaSlicer Reconnaissance

Confirm the existence of these critical files in the current OrcaSlicer codebase (adjusting for potential renames):

- `src/libslic3r/PrintConfig.cpp` (Configuration)
- `src/libslic3r/Model.cpp` (Placement/Transform)
- `src/libslic3r/PrintObject.cpp` (Slicing Pipeline)
- `src/libslic3r/GCode.cpp` (Emission)
- `src/libslic3r/GCode/WipeTower2.cpp` (Wipe Tower)
- _Search also for_: `SupportMaterial.cpp` and Brim/Skew logic.

## 3. Deliverable: "File Map" Report

Produce a Markdown report (`docs/architecture/01_FILE_MAP.md`) containing:

1.  **Verified Orca Paths**: Exact paths for placement, slicing, support, brim, gcode emission.
2.  **Kiri/Cura Findings**: Where (file/function) the belt logic lives in the external repos.
3.  **Recommended Injection Points**: Minimal set of Orca files to modify to support the Shear Logic (from `01_SHEAR_TRANSFORM_LOGIC.md`).

**DO NOT CHANGE CODE YET.** Discovery only.
