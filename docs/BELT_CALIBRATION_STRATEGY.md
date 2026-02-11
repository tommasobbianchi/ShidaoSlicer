# Belt Printer Calibration Strategy

Analysis of OrcaSlicer calibration tests and adaptation strategies for 45° belt printers.

---

## Key Challenge: Every Z Movement is a New First Layer

On belt printers, the print surface is a moving belt at 45°. This creates a fundamental difference:

```
Regular Printer:                    Belt Printer:

Layer 3 ═══════                         ╱ Layer 3 (on belt)
Layer 2 ═══════                        ╱ Layer 2 (on belt)
Layer 1 ═══════  First layer          ╱ Layer 1 (on belt)
═══════════════  Heated bed    ═══════╱═══════  Belt (45°)
```

**Critical insight:** On a belt printer, as Y increases (object grows along belt direction), every new "first layer" line must:
1. Stick to the belt surface (not previous layer)
2. Have proper first-layer settings (slower speed, more squish, correct temperature)

This affects calibration tests that rely on Z-height changes to vary parameters.

---

## Calibration Test Analysis

### 1. Pressure Advance (PA) Tests

#### Current Implementation
- **PA Line Test** (`calib.cpp`): Prints lines at varying speeds with different PA values
- **PA Pattern Test**: Grid pattern showing PA effects at corners
- **PA Tower**: Vertical tower with PA varying per height
- **Auto PA Line**: Automatic PA calibration using sensor feedback

#### Belt Adaptation Strategy: **COMPATIBLE WITH MODIFICATIONS**

**PA Line Test** - Good fit for belt printers:
```
Original (flat bed):              Belt (45° surface):

─────────────────  Line at Z=0.2  ╱╱╱╱╱╱╱╱╱╱╱  Lines on belt surface
─────────────────                 ╱╱╱╱╱╱╱╱╱╱╱  (inclined in machine coords)
─────────────────                 ╱╱╱╱╱╱╱╱╱╱╱
```

**Changes needed:**
- Apply inclined slicing transform (already implemented)
- Test lines print on belt surface at 45°
- First-layer settings apply to ALL lines (they're all on the belt)
- No conceptual changes needed - test measures PA at speed changes

**PA Tower** - Needs rethinking:
- Original: PA varies with Z height
- Problem: On belt, Z height = first layer everywhere
- **Solution:** Convert to Y-direction variation
  - Print horizontally along belt
  - Vary PA along Y axis instead of Z
  - Each segment is a "first layer" section with different PA

---

### 2. Flow Rate Calibration

#### Current Implementation
- Two-stage process (coarse then fine)
- Uses `Orca-LinearFlow.3mf` model
- Prints test blocks to measure flow accuracy

#### Belt Adaptation Strategy: **NEEDS 45° WEDGE BASE**

```
Original:                          Belt Printer:

┌──────────┐                            ╱──────────╲ Test block
│ Test     │  Flat                     ╱    Test    ╲  (on wedge)
│ Block    │  Base                ┌───╱─────────────╲───┐
└──────────┘               45° Wedge base (printed first)
════════════                    ════════╲═══════════════
   Bed                                   Belt
```

**Changes needed:**
1. Generate 45° wedge base first (adheres to belt)
2. Print test block on top of wedge (horizontal surface)
3. Flow calibration then works normally on the flat top surface
4. Wedge must be large enough to support test block
5. First layer of wedge uses belt-specific first layer settings

**Alternative approach:** Adapt test to work directly on inclined surface
- Measure flow on 45° incline
- May reveal belt-specific flow issues (gravity effects on filament)

---

### 3. Temperature Tower

#### Current Implementation
- File: `temperature_tower.stl`
- 10mm blocks, temperature changes every block
- Cut to match start/end temperature range
- Uses G-code temperature changes at height thresholds

#### Belt Adaptation Strategy: **NEEDS 45° WEDGE BASE**

```
Tower height determines temp:        Belt: Need horizontal platform

  260°C  ┌─┐                              ╱┌─┐  260°C
  255°C  ├─┤                             ╱ ├─┤  255°C
  250°C  ├─┤                            ╱  ├─┤  250°C
         └─┘                           ╱   └─┘
         ═══                     45° wedge
                                 ═══════╲═══
```

**Changes needed:**
1. Print 45° wedge base (matches belt angle)
2. Tower prints vertically from wedge top
3. Temperature changes still at Z thresholds (works because tower is vertical)
4. Wedge first layer needs belt-specific adhesion settings

**Implementation:**
- Add `belt_temp_tower_wedge.stl` to resources
- Merge wedge + tower before slicing
- Wedge uses first-layer adhesion settings

---

### 4. Volumetric Speed Tower

#### Current Implementation
- File: `SpeedTestStructure.step`
- Spiral vase mode
- Speed increases with height
- Tests maximum volumetric flow rate

#### Belt Adaptation Strategy: **NEEDS 45° WEDGE BASE**

Same as Temperature Tower:
1. 45° wedge base for belt adhesion
2. Tower structure on top
3. Speed varies with vertical height

**Additional consideration:**
- Verify hotend can maintain temperature at high speeds
- Belt cooling may affect temperature more than flat bed

---

### 5. VFA (Vibration-Free Acceleration) Tower

#### Current Implementation
- File: `VFA.stl`
- Tests resonance/vibration at different speeds
- Identifies optimal acceleration values
- Uses spiral vase mode

#### Belt Adaptation Strategy: **NEEDS 45° WEDGE BASE + CAREFUL ANALYSIS**

```
VFA test detects vibration artifacts:

Regular:           Belt printer:

│▓▓▓▓│            Belt motion may introduce
│▓▓▓▓│            additional vibration modes
│▓▓▓▓│ ← Look     not present on static bed
│▓▓▓▓│   for
│▓▓▓▓│   bands    Need separate belt-specific
└────┘            VFA calibration!
```

**Changes needed:**
1. 45° wedge base
2. **Important:** Belt printers have different vibration characteristics
   - Belt motion adds mechanical complexity
   - May need belt-specific VFA profiles
   - Y-axis (belt) and X-axis may need separate tuning

---

### 6. Retraction Tower

#### Current Implementation
- File: `retraction_tower.stl`
- Tests stringing at different retraction distances
- Height determines retraction amount

#### Belt Adaptation Strategy: **NEEDS 45° WEDGE BASE**

```
Retraction tower:              Belt version:

┌──┐  ┌──┐                         ╱┌──┐  ┌──┐
│  │──│  │  Strings               ╱ │  │──│  │
│  │  │  │  visible              ╱  │  │  │  │
└──┘  └──┘  here                ╱   └──┘  └──┘
════════                    Wedge base
                            ════════╲═══
```

**Changes needed:**
1. 45° wedge base
2. Tower prints normally from wedge top
3. Retraction distance varies with Z height (unchanged logic)

**Additional consideration:**
- Belt printers may have different optimal retraction due to:
  - Different oozing behavior on inclined surface
  - Gravity effects on filament at 45°
  - May need belt-specific retraction tuning

---

### 7. Input Shaping (Frequency & Damping)

#### Current Implementation
- Files: `ringing_tower.stl`, `fast_tower_test.stl`
- Tests mechanical resonance
- Identifies optimal input shaping frequency
- Two-stage: frequency then damping

#### Belt Adaptation Strategy: **NEEDS 45° WEDGE BASE + BELT-SPECIFIC CALIBRATION**

**Critical insight:** Belt printers have fundamentally different mechanical systems:
- Belt tension affects Y-axis dynamics
- Belt inertia differs from leadscrew/belt-drive hybrids
- May have different resonance frequencies

**Changes needed:**
1. 45° wedge base for tower
2. **Separate belt-axis input shaping calibration**
   - Y-axis (belt direction) likely needs different frequency
   - X-axis may match traditional printers
3. Consider adding belt-specific input shaping test

---

### 8. Cornering Test

#### Current Implementation
- File: `SCV-V2.stl`
- Tests junction deviation / square corner velocity
- Prints corners at different speeds to find optimal setting

#### Belt Adaptation Strategy: **NEEDS 45° WEDGE BASE**

```
Cornering test geometry:

  ┌───┬───┐
  │   │   │   Corners at
  ├───┼───┤   various angles
  │   │   │
  └───┴───┘
```

**Changes needed:**
1. 45° wedge base
2. Test geometry on top
3. Corner quality evaluation unchanged

---

## Summary: Belt Calibration Wedge Strategy

### Common 45° Wedge Base

All tower-based tests need a common wedge base:

```
                    ╱│ Test object (tower/pattern)
                   ╱ │
                  ╱  │
        ╱────────╱   │ Height: ~5-10mm
       ╱         │   │
      ╱──────────┴───╱
     ╱           ╱
    ╱───────────╱    45° angle matches belt
═══╱═══════════╱═════
        Belt surface
```

### Wedge Requirements:
1. **Angle:** 45° to match belt angle (configurable for other belt angles)
2. **Size:** Large enough to support test object footprint + margin
3. **Height:** Sufficient for stability (~5-10mm)
4. **First layer:** Uses belt-specific first layer settings:
   - Slower speed
   - More extrusion (squish)
   - Proper temperature
5. **Adhesion:** May need brim on wedge

### Implementation Plan:

1. **Create parametric wedge generator**
   - Input: Test object bounding box
   - Output: 45° wedge STL matching belt angle
   - Configurable angle for other belt printers

2. **Modify calibration workflow**
   - Check if `printer_is_belt` enabled
   - If yes, generate appropriate wedge
   - Merge wedge + calibration model
   - Apply belt transform to combined model

3. **First Layer Settings**
   - Wedge first layer uses belt-specific settings
   - `initial_layer_speed_belt` (new setting?)
   - `initial_layer_flow_belt` (new setting?)

---

## Tests Not Requiring Wedges

Some calibration tests can work directly on the belt:

1. **PA Line Test** - Works with inclined slicing (already implemented)
2. **Simple flow test squares** - Can print directly on belt surface

These tests benefit from:
- Inclined G-code generation (implemented)
- Belt-specific first layer settings
- No vertical tower structure

---

## New Belt-Specific Calibration Tests

Consider adding these belt-specific tests:

### 1. Belt Adhesion Test
```
Print parallel lines along belt direction
Varying: first layer height, speed, temperature
Goal: Find optimal belt adhesion settings
```

### 2. Belt Angle Verification
```
Print square on belt, measure for skew
Verify 45° transform is correct
Check for mechanical misalignment
```

### 3. Belt Tension/Tracking Test
```
Print long narrow object along Y
Check for drift or inconsistency
Identify belt tracking issues
```

---

## Implementation Priority

1. **High Priority (Needed for basic calibration):**
   - [ ] 45° wedge generator function
   - [ ] PA Line test with inclined slicing (works now)
   - [ ] Flow rate test with wedge base
   - [ ] Temperature tower with wedge base

2. **Medium Priority:**
   - [ ] Retraction tower with wedge
   - [ ] VFA tower with wedge
   - [ ] Input shaping with wedge

3. **Lower Priority (Advanced tuning):**
   - [ ] Belt-specific input shaping calibration
   - [ ] Belt adhesion test
   - [ ] Cornering test with wedge

---

## Configuration Options to Add

```cpp
// New belt calibration settings
ConfigOptionFloat belt_first_layer_speed;      // Slower for belt adhesion
ConfigOptionFloat belt_first_layer_flow;       // Extra flow for belt adhesion
ConfigOptionFloat belt_first_layer_height;     // May need different height
ConfigOptionBool  belt_calib_auto_wedge;       // Auto-generate wedge for towers
ConfigOptionFloat belt_calib_wedge_height;     // Wedge height (default 5mm)
```

---

*Document created: 2026-02-06*
*Project: ORCA_BELT - Belt Printer Support for OrcaSlicer*
