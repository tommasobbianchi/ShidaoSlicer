# IdeaMaker Belt Benchy Gcode: Grain-Level Analysis

**File:** `validation/test_output/ideamaker_benchy.gcode`
**Slicer:** IdeaMaker 5.2.2.8570 (2025-04-22)
**Printer:** IdeaFormer IR3 V2 (Klipper firmware)
**Belt Gantry Angle:** 45 degrees
**Total layers:** 292 (layer 0 through 291)
**Total lines:** 169,661
**Print time:** 2739 seconds (~45.6 minutes)
**Material used:** 3670.7mm of filament

---

## 1. MODEL ORIENTATION

### Bounding Box (from header)
```
;Bounding Box: 109.420 140.580 -0.150 68.275 0.000 58.283
  X: 109.42 to 140.58 (span: 31.16mm)  = Benchy width
  Y: -0.15 to 68.275  (span: 68.43mm)  = Benchy height / cos(45°)
  Z: 0.00  to 58.283  (span: 58.28mm)  = Benchy length along belt
```

### Orientation Determination

The standard 3DBenchy STL has:
- Hull bottom flat on the XY plane
- Bow pointing toward -Y, stern toward +Y
- Length (~60mm) along Y axis
- Width (~31mm) along X axis
- Height (~48mm) along Z axis

**In IdeaMaker's belt output, the Benchy is oriented as follows:**

| Benchy Axis | Machine Axis | Evidence |
|---|---|---|
| **Width** (~31mm) | **X** (belt width) | X span = 30.7mm at widest (layer 150) |
| **Height** (~48mm) | **Y** (gantry) | Y max = 68.275mm = 48/cos(45°) = 67.9mm |
| **Length** (~60mm) | **Z** (belt travel) | Z span in bbox = 58.3mm; gcode Z extends to 82.75mm |

**The model has been rotated 90 degrees from its default STL orientation:**
- The default STL has length along Y and height along Z
- IdeaMaker rotates it so that length goes along Z (belt travel = "infinite" axis) and height goes along Y (gantry = build height)
- The **hull bottom (keel) touches the belt first** (Y near 0)
- The **bow and stern point along the Z axis** (belt travel direction)
- The **chimney extends upward** (increasing Y, away from belt)

### Layer Geometry Progression

| Layer | Z (mm) | Y_min | Y_max | Y_span | X_min | X_max | X_span |
|---|---|---|---|---|---|---|---|
| 0 | 0.400 | 0.050 | 0.331 | 0.28 | 119.48 | 130.52 | 11.04 |
| 1 | 0.683 | 0.050 | 1.096 | 1.05 | 119.05 | 130.96 | 11.92 |
| 5 | 1.815 | 0.050 | 4.060 | 4.01 | 117.94 | 132.07 | 14.13 |
| 10 | 3.230 | 0.050 | 7.804 | 7.75 | 116.68 | 133.32 | 16.65 |
| 20 | 6.060 | 0.050 | 13.903 | 13.85 | 114.40 | 135.60 | 21.20 |
| 50 | 14.550 | 0.050 | 14.842 | 14.79 | 113.11 | 136.88 | 23.77 |
| 100 | 28.700 | 0.050 | 21.745 | 21.70 | 111.29 | 138.71 | 27.42 |
| 150 | 42.850 | 2.588 | 35.678 | 33.09 | 109.65 | 140.35 | 30.70 |
| 200 | 57.000 | 12.132 | 54.348 | 42.22 | 109.97 | 140.03 | 30.07 |
| 250 | 71.150 | 24.476 | 68.069 | 43.59 | 114.93 | 135.08 | 20.15 |
| 290 | 82.470 | 37.986 | 38.534 | 0.55 | 124.02 | 125.99 | 1.97 |

Key observations:
- **Y_min stays at 0.050** for layers 0-100+ (the belt contact line)
- **Y_min rises above 0** starting around layer 150 (the stern/bow has passed the slice plane)
- **X_span peaks at ~30.7mm** around layer 150 (widest part of the hull)
- The model narrows rapidly in the final 40 layers (chimney tapering)

---

## 2. PATH ORDERING WITHIN LAYERS

### Feature Type Order

**Layer 0:** `WALL-OUTER` (only)
- A single closed perimeter. Too thin (Y span = 0.28mm) for any fill.

**Layer 1:** `WALL-OUTER -> GAP-FILL`
- One wall perimeter (closed loop), then diagonal gap-fill lines

**Layer 2:** `WALL-OUTER -> WALL-INNER -> GAP-FILL`
- Outer wall first, then inner wall, then gap-fill diagonals

**Layer 3:** `WALL-OUTER -> WALL-INNER -> BOTTOM-SURFACE`
- Gap-fill has been replaced by bottom-surface fill (same diagonal pattern)

**Layer 5:** `WALL-OUTER -> WALL-INNER -> SOLID-FILL -> BOTTOM-SURFACE -> GAP-FILL -> BOTTOM-SURFACE -> FILL`
- First appearance of infill (FILL)
- First appearance of SOLID-FILL (thin transition regions)

**Layer 10:** `WALL-OUTER -> BRIDGE -> WALL-OUTER -> WALL-INNER -> BRIDGE -> WALL-INNER -> GAP-FILL -> SOLID-FILL -> BRIDGE -> GAP-FILL -> SOLID-FILL -> FILL`
- BRIDGE feature appears (the Benchy's hull overhang begins)
- Multiple WALL-OUTER segments = 2 separate islands

**Layer 20:** `WALL-OUTER -> WALL-INNER -> WALL-OUTER -> SOLID-FILL -> GAP-FILL -> SOLID-FILL -> TOP-SURFACE -> BOTTOM-SURFACE -> SOLID-FILL -> FILL`
- 2 islands (main hull + chimney ring)
- TOP-SURFACE appears

**Layer 50:** `WALL-OUTER -> WALL-INNER -> GAP-FILL -> FILL`
- Simplified structure (single island, mid-model)

**Layer 150:** 3 WALL-OUTER segments (3 islands)
**Layer 200:** 4 WALL-OUTER segments (4 islands)
**Layer 250:** 5 WALL-OUTER segments (5 islands -- complex deck region)

### Ordering Rules (verified across all 292 layers)

| Rule | Result |
|---|---|
| WALL-OUTER is always the **first** feature in every layer | **291 of 291 layers** (100%) |
| WALL-OUTER always comes **before** WALL-INNER | **287 of 287 layers** with both (100%) |
| FILL (infill) is the **last** feature when present | **196 of 268 layers** (73%) |

The general ordering pattern is:
```
WALL-OUTER -> WALL-INNER -> [GAP-FILL / SOLID-FILL / BOTTOM-SURFACE / TOP-SURFACE] -> FILL
```

For multi-island layers, each island's walls are printed together, then their fills:
```
Island1: WALL-OUTER -> WALL-INNER
Island2: WALL-OUTER -> WALL-INNER
[gap-fill, solid-fill, bottom-surface, bridge for all islands]
[infill for all islands]
```

### Island Transition Pattern

When multiple islands exist (e.g., hull + chimney ring):
- Each island's walls are printed as a group (outer then inner)
- **A retraction occurs** between islands (always E-0.6000)
- After all walls are done, surface fills and infill follow
- The chimney ring (high Y) is typically printed as a separate wall group

---

## 3. GAP-FILL DIAGONAL STRATEGY

### What is Being Filled

The gap-fill (and later bottom-surface) fills the **triangular wedge region** between:
1. The model's flat horizontal bottom surface (e.g., hull bottom)
2. The oblique 45-degree slicing plane

When slicing at 45 degrees, each layer's cutting plane intersects flat horizontal geometry at an angle, creating a wedge-shaped gap that must be filled with extrusion lines.

### Diagonal Angle: Exactly 45 Degrees

All gap-fill and bottom-surface diagonal lines are at **exactly 45 degrees** relative to the X axis. Verified from coordinate analysis:

```
Layer 1, example line: (129.910, 0.895) -> (130.556, 0.249)
  dX = +0.646, dY = -0.646
  angle = arctan(0.646 / 0.646) = exactly 45.0°
```

This 45-degree angle is not coincidental -- it is exactly the belt angle. The diagonal lines lie parallel to the oblique slicing plane normal projected onto the XY plane.

### Line Spacing

```
Line width:           0.400mm
X-spacing measured:   0.566mm
Theoretical at 45°:   0.400 / cos(45°) = 0.566mm  -- EXACT MATCH
```

The lines are spaced so that their projected coverage on the X axis provides continuous material deposition.

### Direction Alternation

The diagonal direction **alternates every layer**:

| Layer | Direction | Pattern |
|---|---|---|
| 1 (odd) | NW-SE (X-/Y+ and X+/Y-) | Alternating zigzag within layer |
| 2 (even) | NE-SW (X+/Y+ and X-/Y-) | Alternating zigzag within layer |
| 3 (odd) | NW-SE | |
| 4 (even) | NE-SW | |
| 5 (odd) | NW-SE | |
| ... | ... | Continues alternating |

This creates a cross-hatched fill pattern across consecutive layers, providing structural integrity in the wedge region.

### Within Each Layer

The diagonal lines are printed as **short back-and-forth zigzag segments**:
```
Layer 1 example:
  G1 X130.556 Y0.249   (diagonal NW to SE: X+ Y-)
  G0 X129.990 Y0.249   (short travel back in X)
  G1 X129.344 Y0.895   (diagonal SE to NW: X- Y+)
  G0 X128.779 Y0.895   (short travel back in X)
  G1 X129.425 Y0.249   (diagonal NW to SE again)
```

Each line pair consists of one stroke in one direction, a short G0 travel (typically 0.566mm in X), then a stroke back. No retraction between zigzag lines (they are close enough).

### Evolution Across Layers

| Layer Range | GAP-FILL Lines | BOTTOM-SURFACE Lines | Notes |
|---|---|---|---|
| 0 | 0 | 0 | Only wall, too thin |
| 1-2 | 20 | 0 | Gap-fill only (narrow wedge) |
| 3-9 | 0-5 | 20-30 | Bottom-surface replaces gap-fill |
| 10-19 | 3-8 | 0-38 | Mixed; bridge appears at layer 10 |
| 20-30 | 3-45 | 0-72 | Peak bottom-surface (hull widening) |
| 50 | 9 | 0 | Smaller gap regions |
| 100 | 48 | 23 | Multiple small gap regions |
| 150 | 69 | 10 | Deck/cabin complexity |
| 200 | 120 | 0 | Peak gap-fill (complex geometry) |
| 250 | 60 | 0 | Narrowing chimney |
| 290 | 2 | 0 | Tiny chimney tip |

Gap-fill is present on **every layer from 1 to 290** (last layer).
Bottom-surface is present from **layer 3 to layer 282**.

---

## 4. BOTTOM-SURFACE FILL PATTERN

### Pattern: Same 45-Degree Diagonals

Bottom-surface uses the **exact same 45-degree diagonal pattern** as gap-fill. The difference is semantic/contextual:

- **GAP-FILL** (layers 1-2): Used when the wedge region is narrow and there are no inner walls to reference. Lines are printed at slow speed (F600-F828).
- **BOTTOM-SURFACE** (layers 3+): Used when the wedge region has become a proper surface with inner walls defining its boundary. Lines are printed at moderate speed (F1107-F6000).

### Angle and Direction

Bottom-surface fills alternate direction every layer, perfectly synchronized with gap-fill:
- **Odd layers**: NW-SE diagonal (-45 degree in XY, i.e., X+ Y- / X- Y+)
- **Even layers**: NE-SW diagonal (+45 degree in XY, i.e., X+ Y+ / X- Y-)

### Print Order Position

Bottom-surface appears **after walls and before infill**:
```
WALL-OUTER -> WALL-INNER -> [SOLID-FILL] -> BOTTOM-SURFACE -> [GAP-FILL] -> FILL
```

### Key Differences from Gap-Fill

| Property | GAP-FILL | BOTTOM-SURFACE |
|---|---|---|
| Speed | F600-F828 (slow) | F1107-F6000 (moderate-fast) |
| First appearance | Layer 1 | Layer 3 |
| Context | Narrow wedge, no inner wall | Full surface with inner wall boundary |
| E/mm (avg) | 0.0302 | 0.0331 |
| Line lengths | Short (0.3-0.9mm avg) | Longer (0.9-1.9mm avg) |

The higher E/mm for bottom-surface indicates slightly thicker deposition for surface quality.

---

## 5. SEAM PLACEMENT

### Seam Position Analysis

The seam (start/end point of WALL-OUTER loops) varies significantly across layers:

| Layer | Seam X | Seam Y | Location |
|---|---|---|---|
| 0 | 124.999 | 0.331 | Top-center of hull, first G0 travel |
| 1 | 125.004 | 0.050 | Belt contact line, center |
| 2 | 124.523 | 0.050 | Belt contact line, slightly left |
| 3 | 124.809 | 0.359 | Near belt, center-left |
| 5-12 | ~123.8 | ~2.0 | Chimney area (inner circle) |
| 13-20 | ~123.8 | 6-8 | Chimney area, rising Y |
| 50 | 119.735 | 0.050 | Belt contact line, left side |
| 100 | 120.410 | 0.050 | Belt contact line, left side |
| 150 | 117.710 | 28.693 | Mid-height, left hull side |
| 200 | 124.321 | 52.394 | Near chimney, high Y |
| 250 | 122.996 | 67.465 | Chimney top |
| 290 | 124.674 | 38.257 | Final chimney tip |

### Seam Strategy

**IdeaMaker does NOT use a fixed seam position.** The seam moves based on:

1. **Early layers (0-4):** Seam is at or near the belt contact line (Y ~ 0.050), centered on X. This places the seam on the least visible surface (belt contact).

2. **Layers 5-20 (chimney ring appears):** When the chimney ring is a separate island, the outer hull's first wall segment starts near the chimney ring, likely to minimize travel.

3. **Later layers:** Seam placement appears to optimize for minimal travel distance from the previous feature, not aesthetic seam alignment.

**Key finding:** IdeaMaker does NOT consistently place seams at the lowest Y (nearest belt). It uses a travel-distance-minimizing heuristic.

---

## 6. SPEED STRATEGY

### Speed by Feature Type

| Feature Type | Min F | Max F | Mean F | Typical mm/s |
|---|---|---|---|---|
| WALL-OUTER | 600 | 10200 | 2901 | 30 (F1800 dominant) |
| WALL-INNER | 600 | 13500 | 5952 | 30-225 |
| GAP-FILL | 600 | 3600 | 2521 | 10-60 |
| BOTTOM-SURFACE | 600 | 6000 | 3747 | 10-100 |
| SOLID-FILL | 600 | 9000 | 6590 | 100-150 |
| FILL (infill) | 1243 | 15000 | 7754 | 100-250 |
| BRIDGE | 1203 | 3600 | 2403 | 20-60 |
| TOP-SURFACE | 1686 | 6000 | 3063 | 28-100 |

### The Most Common Speed: F1800 (30 mm/s)

F1800 is the dominant outer wall speed, used for:
- All straight segments at Y=0.050 (belt contact line)
- Start/end of wall perimeters
- Retraction/unretraction moves

### Variable Speed: Y-Dependent Speed Ramping

**IdeaMaker reduces outer wall speed as Y increases (farther from belt).**

Layer 20 outer wall speed profile:
```
Y=0.050   F=1800  (30 mm/s)  -- belt contact
Y=1.310   F=2102  (35 mm/s)  -- surprising: slightly faster!
Y=5.643   F=1882  (31 mm/s)
Y=7.417   F=1662  (28 mm/s)
Y=10.739  F=1442  (24 mm/s)
Y=13.254  F=1222  (20 mm/s)  -- highest Y, slowest
```

The speed decreases linearly: approximately **-44 mm/min per mm of Y increase** (for the outer hull).

**However,** the chimney circle (separate island at high Y) uses much higher speeds:
```
Chimney ring: F4125-F5195 (69-87 mm/s)
```

This suggests IdeaMaker has separate speed rules for:
1. **Hull walls** (large perimeter): Speed ramps DOWN with Y
2. **Small features** (chimney, etc.): Speed stays at configured rate

### Early Layer Speed

Layer 0-5 outer walls all start at F1800 (30 mm/s). There is **no dedicated "first layer speed" reduction** -- the first layer is already at the configured outer wall speed. The smaller feature size of early layers naturally limits speed.

### Speed Ramping on Inclined Sides

Layer 2 shows the speed transition clearly:
```
Along Y=0.050 (flat bottom):     F1800 (30 mm/s)
Climbing to Y=0.264:             F768  (12.8 mm/s) -- big speed drop!
Along inclined hull side:         F600  (10 mm/s) -- minimum speed
Coming back toward Y=0.050:       F768  (12.8 mm/s)
Along Y=0.050 again:             F1800 (30 mm/s)
```

The F600 (10 mm/s) minimum speed on inclined sides serves as a "minimum printable speed" for overhanging geometry near the belt.

---

## 7. EXTRUSION FLOW

### Flow Annotations

Three FLOW values are used:
| Flow | Count | Where |
|---|---|---|
| `;FLOW:102.0` | 1878 | All walls (outer, inner), gap-fill, bottom/top surfaces |
| `;FLOW:95.0` | 360 | Infill (FILL) only |
| `;FLOW:100.0` | 360 | Reset annotation between infill and next layer |

### M221 S98 and FLOW:102 Combined Effect

```
M221 T0 S98.00    (firmware flow multiplier = 0.98)
;FLOW:102.0       (slicer flow multiplier = 1.02)

Combined: 0.98 * 1.02 = 0.9996 ≈ 100%
```

The two effectively cancel out, resulting in near-unity flow. The M221 S98 is likely a filament-specific calibration value, and FLOW:102.0 is IdeaMaker's default slight over-extrusion for wall adhesion.

### Measured E/mm by Feature Type

| Feature Type | E/mm (avg) | Width | Expected E/mm | Match |
|---|---|---|---|---|
| WALL-OUTER | 0.0333 | 0.400 | 0.0333 | Exact |
| WALL-INNER | 0.0333 | 0.400 | 0.0333 | Exact |
| FILL | 0.0316 | 0.400 | 0.0310 (95% flow) | Close |
| BOTTOM-SURFACE | 0.0331 | 0.400 | 0.0333 | Very close |
| GAP-FILL | 0.0302 | varies | varies | Variable width |
| SOLID-FILL | 0.0274 | varies | varies | Variable width |

### E/mm Derivation

```
Line width:           0.400mm
Belt-normal height:   0.200mm (HEIGHT-BELT)
Filament diameter:    1.750mm
Filament area:        pi * (0.875)² = 2.405 mm²
Extrusion area:       0.400 * 0.200 = 0.080 mm²
E/mm = 0.080 / 2.405 = 0.03326 mm/mm
```

With FLOW 102% and M221 S98: `0.03326 * 1.02 * 0.98 = 0.03324` -- matches measured 0.0333.

### WIDTH Variations

The `;WIDTH:` annotation varies for:
- **Gap-fill lines:** Width ranges from 0.082mm to 0.563mm depending on the gap being filled
- **Solid-fill transitions:** Width ranges from 0.144mm to 0.565mm
- **Standard features:** Always 0.400mm

Variable-width extrusion is used to fill irregularly shaped gaps that don't fit standard-width lines.

---

## 8. TRAVEL PATTERN

### No Z-Hop

**Confirmed: Zero Z-hop in the entire file.** Analysis shows:
- **292 G0 Z-only moves**: All are layer transitions (changing to next layer's Z height)
- **0 G0 moves with both Z and XY**: No Z-hop during mid-layer travel
- **1 non-layer Z move**: Only at the very end (line 169626: `G0 Z87.470` -- final park position)

### Travel Speed

Two travel speeds are used:
- **F15000** (250 mm/s): Long-distance travel (between features, between islands)
- **F600** (10 mm/s): Short-distance travel within gap-fill zigzag patterns and layer Z-change moves

### Retraction Pattern

All retractions are identical:
```
G1 F1800 E-0.6000    (retract 0.6mm at 30mm/s)
...travel...
G1 F1800 E0.6000     (unretract 0.6mm at 30mm/s)
```

- **Total retractions:** 1656
- **Total unretractions:** 1655 (one final retract at end has no matching unretract)
- Retraction amount: always exactly 0.6mm
- Retraction speed: always F1800 (30 mm/s)

### Travel Distance Statistics

| Category | Count | Min | Max | Mean |
|---|---|---|---|---|
| WITH retraction | 1,656 | 0.24mm | 31.76mm | 11.62mm |
| WITHOUT retraction | 12,452 | 0.00mm | 125.00mm | 1.67mm |

**Key finding:** Most non-retracted travels are very short (< 2mm), corresponding to gap-fill zigzag transitions. The maximum non-retracted travel (125mm) occurs for G0 moves within the same feature type where the nozzle is already primed.

### Acceleration Control

Two acceleration values alternate:
```
SET_VELOCITY_LIMIT ACCEL=10000.00    (749 occurrences) -- for travel moves
SET_VELOCITY_LIMIT ACCEL=8000.00     (748 occurrences) -- for print moves
```

Pattern:
1. Before travel to new feature start: `ACCEL=10000` (high accel for fast travel)
2. Before first print move of new feature: `ACCEL=8000` (lower accel for print quality)

---

## 9. LAYER TRANSITION

### Exact Transition Sequence

The layer transition follows this **invariant pattern** across all 292 layers:

```
[last extrusion of previous layer]
;PRINTING_TIME: N
;REMAINING_TIME: M
;LAYER:N
;Z:X.XXX
;HEIGHT:0.283
;HEIGHT-BELT:0.200
[optional: M106 SXXX -- fan speed change]
;PRINTING: ??????.stl
;PRINTING_ID: 0
G1 F1800 E-0.6000                    -- retract
SET_VELOCITY_LIMIT ACCEL=10000.00     -- high accel for travel
G0 F600 Z0.683                        -- Z move to new layer (SLOW: 10mm/s!)
G0 F15000 X125.004 Y0.050            -- XY travel to start position (FAST)
SET_VELOCITY_LIMIT ACCEL=8000.00      -- lower accel for printing
;TYPE:WALL-OUTER
;WIDTH:0.400
;FLOW:102.0
G1 F1800 E0.6000                      -- unretract
G1 F1800 X... Y... E...               -- first extrusion move
```

### Key Observations

1. **Retraction happens BEFORE Z move** (not after). This prevents oozing during the slow Z transition.

2. **Z move is at F600 (10 mm/s)** -- very slow! This is the belt advancement speed. The belt moves slowly to the new Z position.

3. **XY travel is at F15000 (250 mm/s)** -- fast positioning after Z is reached.

4. **No Z-hop** between the retraction and Z move. The sequence is:
   - Retract filament
   - Move Z to new layer height (belt advances)
   - Move XY to new start position
   - Unretract and start printing

5. **Layer always starts with WALL-OUTER** -- the outermost perimeter is always first.

### Where Does Each Layer Start?

Early layers start near the belt contact line (Y ~ 0.050). Later layers start at varying positions. The start position is typically at a point on the outer wall that minimizes travel from the previous layer's end position.

---

## 10. FAN CONTROL

### Fan Speed Progression

| Layer | Line | M106 Value | % Speed | Stage |
|---|---|---|---|---|
| 0 | 434 | S26 | 10.2% | Initial (minimum cooling) |
| 4 | 831 | S77 | 30.2% | Early ramp |
| 9 | 1963 | S128 | 50.2% | Mid ramp |
| 19 | 6295 | S204 | 80.0% | Late ramp |
| 29 | 12047 | S255 | 100.0% | Full speed (maintained) |

### Fan Ramp Strategy

```
Layer  0: 10% fan  (minimal cooling, belt adhesion critical)
Layer  4: 30% fan  (some cooling, layers still thin)
Layer  9: 50% fan  (half speed)
Layer 19: 80% fan  (most cooling)
Layer 29: 100% fan (full speed, maintained for rest of print)
```

The fan ramps linearly over the first 30 layers (about 8.5mm of belt travel / 6mm of Y height), then stays at 100% for the remaining 262 layers. This is a standard strategy: minimal fan near the belt for adhesion, increasing as the part gains height and needs more cooling.

---

## 11. BRIDGE HANDLING

Bridge features appear on only **3 layers: 10, 19, and 184**.

On layer 10, the bridge is the **Benchy's hull window overhang**:
```
;TYPE:BRIDGE
;WIDTH:0.400
;FLOW:102.0
G1 F1203 X133.296 Y6.644 E0.0128
...
G1 F1375 X128.493 Y7.802 E0.0998    -- bridge lines
G1 F1547 X125.493 Y7.802 E0.0998    -- straight across
```

Bridge characteristics:
- Speed: F1203-F3600 (20-60 mm/s) -- moderate, controlled speed
- Width: 0.400mm (standard) or 0.480mm (slightly wider for adhesion)
- Flow: 102% (same as walls, no flow reduction for bridges)
- The bridge lines span the window opening at constant Y, crossing in X
- Bridge lines are diagonal at 45 degrees (same as bottom-surface), filling the bridge area

---

## 12. LAYER HEIGHT RELATIONSHIP

### Header Annotations

```
;HEIGHT:0.283          -- virtual Z increment between layers
;HEIGHT-BELT:0.200     -- belt-normal (physical) layer thickness
```

For layer 0:
```
;HEIGHT:0.400          -- first layer virtual Z
;HEIGHT-BELT:0.283     -- first layer belt-normal height
```

### Mathematical Relationship

```
HEIGHT = HEIGHT-BELT * sqrt(2)    (for 45° belt angle)

Layer 0:  0.400 / sqrt(2) = 0.283  ✓
Layer 1+: 0.283 / sqrt(2) = 0.200  ✓
```

The virtual Z increment (HEIGHT) is larger than the physical layer thickness (HEIGHT-BELT) because the layers are inclined at 45 degrees. The physical deposition thickness is what matters for extrusion calculations.

### First Layer

The first layer is thicker: 0.283mm belt-normal vs 0.200mm for subsequent layers. This provides better belt adhesion (common practice: first layer is ~1.4x normal height).

---

## 13. MULTI-ISLAND HANDLING

### Island Count by Layer Range

| Layer Range | Typical Islands | Regions |
|---|---|---|
| 0-9 | 1-2 | Hull only, then hull + chimney base |
| 10-24 | 2-3 | Hull + chimney ring + optional window bridge |
| 25-30 | 1-2 | Hull only (chimney merged) |
| 50-140 | 1-2 | Main hull body |
| 150-180 | 3 | Hull + deck features |
| 190-210 | 3-4 | Complex deck/cabin area |
| 220-260 | 2-5 | Chimney + remaining hull features |
| 270-290 | 1-2 | Chimney tapering |

### Inter-Island Travel

When transitioning between islands:
1. **Retract** (E-0.6000)
2. **Travel** at F15000 (250 mm/s) to next island
3. **Unretract** (E0.6000)
4. Begin next island's wall

Within a single island, gap-fill zigzag moves use **G0 without retraction** (short hops of 0.5-0.6mm).

---

## 14. COMPLETE FEATURE TYPE STATISTICS

| Feature Type | Occurrences | Avg E/mm | Primary Purpose |
|---|---|---|---|
| WALL-OUTER | 649 segments | 0.0333 | Outermost perimeter, always first |
| WALL-INNER | 597 segments | 0.0333 | Inner perimeter(s), after outer |
| GAP-FILL | 1012 segments | 0.0302 | 45° diagonal wedge fill, variable width |
| SOLID-FILL | 607 segments | 0.0274 | Thin solid transition regions |
| BOTTOM-SURFACE | 256 segments | 0.0331 | 45° diagonal surface fill (wider wedge) |
| FILL | 360 segments | 0.0316 | Internal infill pattern |
| TOP-SURFACE | 24 segments | 0.0233 | Top-facing surface quality fill |
| BRIDGE | 12 segments | 0.0364 | Unsupported span crossing |

---

## 15. SUMMARY: WHAT ORCASLICER MUST EMULATE

### Critical Items for Belt Printing Fidelity

1. **Outer-wall-first ordering**: Every layer must start with WALL-OUTER. This is already a slicer option but must be mandatory for belt printing.

2. **45-degree diagonal fill for bottom surfaces**: The wedge between the oblique slicing plane and horizontal model geometry must be filled with lines at exactly the belt angle (45 degrees), alternating direction every layer.

3. **Variable speed by Y position**: Outer wall speed should decrease linearly as Y increases (farther from belt = slower). This compensates for the increasing overhang angle and reduced belt-surface support.

4. **No Z-hop**: Belt printers should never Z-hop. Travel moves are XY-only (or use gantry Y-lift, which is our existing implementation).

5. **Slow Z-axis moves**: Layer transitions use F600 (10 mm/s) for Z movement. The belt motor needs time to advance smoothly.

6. **Fan ramp over 30 layers**: Start at ~10% fan, ramp to 100% over the first 30 layers for belt adhesion.

7. **Retraction before Z-move**: Always retract BEFORE advancing the belt to the next layer Z position.

8. **First layer height**: 1.4x normal height (0.283mm vs 0.200mm belt-normal) for adhesion.

9. **E/mm calculation uses belt-normal height**: Extrusion is computed using the 0.200mm belt-normal thickness, not the 0.283mm virtual Z increment.

10. **Gap-fill line spacing**: `width / cos(belt_angle)` for projected coverage on the X axis.

### Items OrcaSlicer Already Handles

- Oblique slicing (45-degree cutting plane) -- implemented
- Layer height scaling (HEIGHT vs HEIGHT-BELT) -- implemented
- E/mm correction for belt-normal height -- implemented (belt shear flow correction)
- Gantry Y-lift instead of Z-hop -- implemented

### Items Needing Implementation

- Y-dependent speed ramping for outer walls
- Mandatory outer-wall-first ordering for belt mode
- 45-degree diagonal bottom-surface fill pattern
- Fan ramp profile for belt adhesion
- Slow Z-move speed for layer transitions
- Retract-before-Z-move enforcement
