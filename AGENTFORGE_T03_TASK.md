# AgentForge Task: T03 Directional Supports Integration

## Status

- ✅ Unit tests passing (7/7)
- ✅ DirectionalSupports module complete and tested
- 🔧 Need integration into SupportMaterial.cpp

## Task

Integrate DirectionalSupports to skip backward-facing overhangs (self-supporting).

## Files to Modify

### 1. Support/SupportMaterial.cpp - Add Include

```cpp
// Near top with other includes:
#include "BeltPrinter/DirectionalSupports.hpp"
```

### 2. Support/SupportMaterial.cpp - Classify Overhangs (~line 1450, in detect_overhangs or similar)

```cpp
// After identifying overhang surfaces, before generating support:
if (object.print()->config().belt_printer.value) {
    using namespace BeltPrinter;

    // Get belt profile
    auto* belt_profile = object.belt_machine_profile();
    if (belt_profile) {
        auto settings = DirectionalSupports::SupportSettings::from_profile(*belt_profile);

        // Classify each overhang surface
        for (auto& surface : overhang_surfaces) {
            // Get surface normal (from layer normal or compute)
            Vec3d normal = /* extract from surface */;

            auto dep = DirectionalSupports::classify_dependency(normal, settings);

            if (dep == SupportDependency::BACKWARD) {
                // Backward overhang - self supporting, skip support
                BOOST_LOG_TRIVIAL(info) << "Skipping backward overhang (self-supporting)";
                continue;
            }

            // Generate support for FORWARD and VERTICAL only
        }
    }
}
```

## Key Functions

- `DirectionalSupports::classify_dependency(normal, settings)` → returns `SupportDependency` enum
- `SupportSettings::from_profile(profile)` → creates settings from belt profile
- Returns: `FORWARD` (needs support), `BACKWARD` (skip), `VERTICAL` (needs support)

## Build & Test

```bash
cd build && ninja -j4 orca-slicer

# Test with model that has backward overhangs
build/src/Debug/orca-slicer tests/fixtures/belt_test_tower.stl \
  --load-settings tests/fixtures/belt_raft_config.json\;tests/fixtures/belt_process.json\;tests/fixtures/belt_filament.json \
  --slice 0 --export-3mf /tmp/t03_test.3mf

# Check G-code for reduced support
grep "support" /tmp/t03_test.3mf | wc -l  # Should be less than before
```

## Expected Result

- Build succeeds
- Backward-facing overhangs generate no support
- Forward/vertical overhangs still get support
- Log shows "Skipping backward overhang" messages

## Notes

- Integration point: wherever overhang surfaces are identified for support
- May be in `detect_overhangs()` or similar function
- Look for loops over surfaces/regions that decide support placement
- All logic gated by `belt_printer.value` check
