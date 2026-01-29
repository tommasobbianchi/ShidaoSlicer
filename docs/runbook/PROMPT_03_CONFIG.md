# Prompt 3: Configuration Plumbing

**Goal:** Implement belt-printer configuration options in OrcaSlicer core (`libslic3r`).

## 1. Target Files

- `src/libslic3r/PrintConfig.cpp`
- `src/libslic3r/PrintConfig.hpp`

## 2. Tasks

1.  **Define Options**: Add the following configuration keys to `PrintConfigDef`:
    - `printer_is_belt` (bool, default false)
    - `belt_angle` (float, default 45.0, range 0-90)
    - `belt_wall_enabled` (bool, optional for future)
2.  **Expose**: Ensure these options are accessible via `DynamicPrintConfig` and serialized in presets.
3.  **Sanity Check**: Verify the code compiles and these options can be queried.

## 3. Deliverable

- Code modification to `PrintConfig.cpp/hpp`.
- Verification that `print_config.opt_bool("printer_is_belt")` works.
