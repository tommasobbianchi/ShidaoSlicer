# AgentForge Task: T06 G-code Emission Integration

## Status

- ✅ Unit tests passing (9/9)
- ✅ GCodeEmitter module complete and tested
- 🔧 Need integration into GCode.cpp

## Task

Integrate GCodeEmitter into main G-code generation pipeline.

## Files to Modify

### 1. GCode.hpp (add member)

```cpp
// After line 32, with other includes:
#include "BeltPrinter/GCodeEmitter.hpp"

// In private members section (~line 640):
std::unique_ptr<BeltPrinter::GCodeEmitter> m_belt_emitter;
bool m_belt_emitter_enabled = false;
```

### 2. GCode.cpp - Initialize (in \_do_export, ~line 2340)

```cpp
// After belt contact classification setup:
if (print.config().belt_printer.value) {
    // Get belt profile from first object
    const PrintObject* first_obj = print.objects().front();
    if (first_obj && first_obj->belt_machine_profile()) {
        auto settings = BeltPrinter::EmissionSettings();
        settings.include_comments = true;
        settings.coordinate_precision = 3;

        m_belt_emitter = std::make_unique<BeltPrinter::GCodeEmitter>(
            *first_obj->belt_machine_profile(), settings);
        m_belt_emitter_enabled = true;

        BOOST_LOG_TRIVIAL(info) << "Belt G-code emitter initialized";
    }
}
```

### 3. GCode.cpp - Add Metadata Header (~line 2600, in preamble())

```cpp
// Near end of preamble() function, before return:
if (m_belt_emitter_enabled) {
    gcode += m_belt_emitter->emit_profile_metadata();
}
```

### 4. GCode.cpp - Add Safe Ejection (~line 3200, in \_do_export finale)

```cpp
// At very end of G-code generation, before file close:
if (m_belt_emitter_enabled) {
    file.write(m_belt_emitter->emit_safe_ejection());
}
```

## Build & Test

```bash
cd build && ninja -j4 orca-slicer
build/src/Debug/orca-slicer tests/fixtures/belt_test_tower.stl \
  --load-settings tests/fixtures/belt_raft_config.json\;tests/fixtures/belt_process.json\;tests/fixtures/belt_filament.json \
  --slice 0 --export-3mf /tmp/t06_test.3mf

# Verify metadata in G-code
grep "Belt Printer Profile Metadata" /tmp/t06_test.3mf
grep "Safe Belt Ejection" /tmp/t06_test.3mf
```

## Expected Result

- Build succeeds
- G-code contains belt printer metadata header
- G-code ends with safe ejection sequence
- No errors or warnings

## Notes

- All changes gated by `m_belt_emitter_enabled` check
- GCodeEmitter API fully tested (9/9 unit tests pass)
- No changes to existing non-belt code paths
