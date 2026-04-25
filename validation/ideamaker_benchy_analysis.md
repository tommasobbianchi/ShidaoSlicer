# IdeaMaker Belt Printer Benchy G-code Analysis

**File:** `validation/test_output/ideamaker_benchy.gcode`
**Slicer:** IdeaMaker 5.2.2.8570 (2025-04-22)
**Printer:** IdeaFormer IR3 V2 (Belt Printer, 45-degree gantry angle)
**Firmware:** Klipper
**Model:** Benchy (filename encoded as `??????.stl`)
**Total lines:** 169,661
**Print time:** 2739 seconds (~45.6 minutes)
**Material used:** 3670.7 mm of filament

---

## 1. Layer Structure

### Summary

| Property | Value |
|---|---|
| Total layers | 292 (layer 0 through layer 291) |
| First layer Z | 0.400 mm |
| Last layer Z | 82.753 mm |
| Z increment | 0.283 mm (constant for all layers) |
| First layer HEIGHT | 0.400 (HEIGHT-BELT: 0.283) |
| Subsequent HEIGHT | 0.283 (HEIGHT-BELT: 0.200) |

### Z Value Progression

The Z increment is **exactly 0.283 mm** for every layer transition, with zero exceptions across all 292 layers. This value equals `0.200 / cos(45deg)` -- the user-facing layer height of 0.200 mm divided by cos(45deg) to get the gantry-direction spacing.

The first layer is thicker:
- HEIGHT = 0.400 mm (gantry direction)
- HEIGHT-BELT = 0.283 mm (belt-normal = `0.400 * cos(45deg)`)
- This gives a first belt-normal layer height of 0.283 mm vs 0.200 mm for subsequent layers

IdeaMaker annotates each layer with both values:
```
;LAYER:1
;Z:0.683
;HEIGHT:0.283
;HEIGHT-BELT:0.200
```

### Z Values for First 20 Layers

| Layer | Z (mm) | Delta from previous |
|---|---|---|
| 0 | 0.400 | -- (first layer) |
| 1 | 0.683 | 0.283 |
| 2 | 0.966 | 0.283 |
| 3 | 1.249 | 0.283 |
| 4 | 1.532 | 0.283 |
| 5 | 1.815 | 0.283 |
| 6 | 2.098 | 0.283 |
| 7 | 2.381 | 0.283 |
| 8 | 2.664 | 0.283 |
| 9 | 2.947 | 0.283 |
| 10 | 3.230 | 0.283 |
| 11 | 3.513 | 0.283 |
| 12 | 3.796 | 0.283 |
| 13 | 4.079 | 0.283 |
| 14 | 4.362 | 0.283 |
| 15 | 4.645 | 0.283 |
| 16 | 4.928 | 0.283 |
| 17 | 5.211 | 0.283 |
| 18 | 5.494 | 0.283 |
| 19 | 5.777 | 0.283 |

### Last Few Layers

| Layer | Z (mm) |
|---|---|
| 288 | 81.904 |
| 289 | 82.187 |
| 290 | 82.470 |
| 291 | 82.753 |

---

## 2. Y Range Per Layer (First 20 Layers)

Y represents the gantry axis (tilted 45 degrees from horizontal). Y grows as the model builds upward away from the belt surface. The minimum Y across all layers is **0.050 mm** -- extrusions start very close to the belt but never touch Y=0.

| Layer | Z | Y min | Y max | Y range | Ext. moves | Travels | Retracts |
|---|---|---|---|---|---|---|---|
| 0 | 0.400 | 0.050 | 0.331 | 0.281 | 10 | 2 | 0 |
| 1 | 0.683 | 0.050 | 1.096 | 1.046 | 47 | 20 | 1 |
| 2 | 0.966 | 0.050 | 1.846 | 1.796 | 82 | 20 | 3 |
| 3 | 1.249 | 0.050 | 2.589 | 2.539 | 97 | 22 | 3 |
| 4 | 1.532 | 0.050 | 3.330 | 3.280 | 115 | 25 | 3 |
| 5 | 1.815 | 0.050 | 4.060 | 4.010 | 135 | 30 | 4 |
| 6 | 2.098 | 0.050 | 4.779 | 4.729 | 148 | 34 | 4 |
| 7 | 2.381 | 0.050 | 5.490 | 5.440 | 159 | 37 | 5 |
| 8 | 2.664 | 0.050 | 6.191 | 6.141 | 193 | 39 | 4 |
| 9 | 2.947 | 0.050 | 6.877 | 6.827 | 227 | 36 | 4 |
| 10 | 3.230 | 0.050 | 7.804 | 7.754 | 249 | 34 | 6 |
| 11 | 3.513 | 0.050 | 8.462 | 8.412 | 310 | 45 | 2 |
| 12 | 3.796 | 0.050 | 9.102 | 9.052 | 351 | 52 | 5 |
| 13 | 4.079 | 0.050 | 9.730 | 9.680 | 378 | 50 | 8 |
| 14 | 4.362 | 0.050 | 10.344 | 10.294 | 343 | 49 | 7 |
| 15 | 4.645 | 0.050 | 10.948 | 10.898 | 334 | 47 | 6 |
| 16 | 4.928 | 0.050 | 11.317 | 11.267 | 332 | 50 | 7 |
| 17 | 5.211 | 0.050 | 11.899 | 11.849 | 347 | 51 | 7 |
| 18 | 5.494 | 0.050 | 13.103 | 13.053 | 361 | 49 | 7 |
| 19 | 5.777 | 0.050 | 13.503 | 13.453 | 366 | 45 | 8 |
| 20 | 6.060 | 0.050 | 13.903 | 13.853 | 407 | 68 | 5 |

**Key observations:**
- Y range grows rapidly in early layers as the model's cross-section grows upward along the belt-normal direction.
- All layers start at Y near 0.050, meaning each layer has extrusions touching the belt surface.
- By layer 20, the Y range reaches ~14 mm (the model is ~14 mm tall in the gantry direction at this belt position).

---

## 3. First 5 Layers Detailed

### Layer 0 (Z=0.400)

- **Z value:** 0.400 mm
- **HEIGHT:** 0.400 / **HEIGHT-BELT:** 0.283 (first layer is thicker)
- **Y range:** 0.050 to 0.331 mm (only 0.28 mm band -- a thin strip on the belt)
- **Types:** WALL-OUTER only
- **Extrusion moves:** 10
- **Travels:** 2 (one XY travel, one Z positioning)
- **Retractions:** 0
- **Pattern:** A single closed loop of outer wall. No inner wall, no infill. The model's cross-section at this Z/belt position is just a thin strip. The very first extrusion starts at X=124.999, Y=0.331.

```
G0 F15000 X124.999 Y0.331     ; Travel to start position
G0 F600 Z0.400                  ; Move to layer Z
;TYPE:WALL-OUTER
G1 F1800 X119.832 Y0.331 E0.2480  ; First extrusion
...
G1 F1800 X124.999 Y0.331 E0.2481  ; Close the loop
```

### Layer 1 (Z=0.683)

- **Z value:** 0.683 mm
- **Y range:** 0.050 to 1.096 mm
- **Types:** WALL-OUTER, GAP-FILL
- **Extrusion moves:** 47 (28 wall-outer, 20 gap-fill)
- **Travels:** 20 (mostly short hops within gap-fill)
- **Retractions:** 1 (only at layer transition)
- **Pattern:**
  - Retraction at previous layer end, Z move to 0.683, XY travel to start, unretract
  - Outer wall loop around the full cross-section
  - **GAP-FILL diagonal lines at exactly +/-45 degrees**: These fill the triangular wedge between the 45-degree belt surface and the flat bottom of the model. The diagonals alternate between 135 degrees and -45 degrees (northwest-southeast and northeast-southwest), creating a zigzag pattern.

**Gap-fill diagonal pattern (layer 1):**
```
;TYPE:GAP-FILL
G0 F15000 X129.910 Y0.895      ; Travel to start of diagonal
G1 F600 X130.556 Y0.249 E0.0304  ; Extrude at -45deg
G0 F600 X129.990 Y0.249        ; Travel
G1 F600 X129.344 Y0.895 E0.0304  ; Extrude at 135deg
G0 F600 X128.779 Y0.895        ; Travel
G1 F600 X129.425 Y0.249 E0.0304  ; Extrude at -45deg
...
```
Each diagonal line is ~0.91 mm long, spanning the Y range of 0.249 to 0.895 at the 45-degree angle. This is IdeaMaker's approach to filling the wedge-shaped void between the inclined belt surface and the model's horizontal bottom.

### Layer 2 (Z=0.966)

- **Z value:** 0.966 mm
- **Y range:** 0.050 to 1.846 mm
- **Types:** WALL-OUTER, WALL-INNER, GAP-FILL
- **Extrusion moves:** 82 (39 wall-outer, 26 wall-inner, 20 gap-fill)
- **Travels:** 20
- **Retractions:** 3 (1 layer transition + 2 mid-layer between regions)
- **Pattern:** First layer with inner walls. Cross-section is now wide enough for inner+outer wall pairs. Gap-fill diagonals continue. Multiple speed values (F600, F768, F828, F1028, F1800) indicate IdeaMaker varies speed based on feature geometry.

### Layer 3 (Z=1.249)

- **Z value:** 1.249 mm
- **Y range:** 0.050 to 2.589 mm
- **Types:** WALL-OUTER, WALL-INNER, BOTTOM-SURFACE
- **Extrusion moves:** 97 (52 wall-outer, 28 wall-inner, 20 bottom-surface)
- **Travels:** 22
- **Retractions:** 3
- **Pattern:** First layer with BOTTOM-SURFACE (solid bottom fill). Gap-fill diagonals are replaced by proper bottom infill. The bottom surface fill uses the same zigzag diagonal pattern but classified differently.

### Layer 4 (Z=1.532)

- **Z value:** 1.532 mm
- **Y range:** 0.050 to 3.330 mm
- **Types:** WALL-OUTER, WALL-INNER, BOTTOM-SURFACE
- **Extrusion moves:** 115 (58 wall-outer, 37 wall-inner, 23 bottom-surface)
- **Travels:** 25
- **Retractions:** 3
- **Pattern:** Similar to layer 3 with growing cross-section. The bottom-surface fill lines use speeds around F1355 and travel between fill lines at the same speed.

---

## 4. Coordinate System Analysis

### These Are Machine Coordinates

**Conclusion: The G-code uses MACHINE coordinates (gantry frame), not virtual/model coordinates.**

Evidence:

1. **Z is constant within each layer.** Every layer has exactly ONE Z value. No Z variation within a layer. This is the belt position (distance along the belt surface).

2. **Z increases monotonically across layers** by exactly 0.283 mm per layer. The belt advances 0.283 mm between layers (= 0.2 mm belt-normal / cos(45deg)).

3. **Y represents the gantry axis** (tilted 45 degrees). Y ranges from ~0.050 (near belt surface) upward. The model grows in Y as it builds upward from the belt.

4. **There are ZERO combined Y+Z moves in extrusion (G1 with both Y and Z).** Z only changes via G0 at layer transitions. Within a layer, moves are purely in XY at constant Z. This confirms machine-coordinate output where each layer is a constant-Z slice.

5. **No negative Y values anywhere.** The minimum Y across all extrusion moves is 0.050 mm. Y is always positive (gantry only moves away from belt).

6. **No negative coordinates at all.** All X, Y, Z values are positive throughout the file.

### Axis Mapping

| G-code Axis | Machine Meaning | Physical Direction |
|---|---|---|
| X | Belt width | Perpendicular to belt travel, horizontal |
| Y | Gantry height | 45 degrees from horizontal, perpendicular to belt surface |
| Z | Belt travel | Along belt surface direction (belt moves in -Z, equivalent to model moving in +Z) |

### Z vs Y Relationship

- Z and Y are **independent** within each layer (Z is constant, Y varies freely)
- Across layers: Z increases by 0.283 per layer; Y range grows as the model cross-section grows
- The ratio Z/Y_max starts around 1.2 (layer 0) and varies with model geometry, reaching ~2.14 at the final layers where the model narrows

### First Layer Coordinates

The very first extrusion occurs at:
```
X=124.999, Y=0.331, Z=0.400
```
- X is centered at 125.0 mm (half of the 250 mm belt width)
- Y is 0.331 mm above the belt surface
- Z is 0.400 mm along the belt (first layer height in gantry direction)

---

## 5. Travel and Retraction Pattern

### Retraction

- **Retraction amount:** 0.6 mm (constant, never varies)
- **Total retractions:** 1,656 across the entire print
- **Extrusion mode:** M83 (relative extrusion) -- set once at line 427, before layer 0
- **Unretraction:** Always exactly +0.6000 mm (`G1 F1800 E0.6000`)

### Layer Transition Pattern

Every layer transition follows this exact sequence:
```
G1 F1800 E-0.6000              ; Retract
SET_VELOCITY_LIMIT ACCEL=10000.00  ; High accel for travel
G0 F600 Z{next_layer_z}        ; Move to next layer Z (belt advance)
G0 F15000 X... Y...            ; Fast XY travel to start of next layer
SET_VELOCITY_LIMIT ACCEL=8000.00   ; Normal accel for printing
;TYPE:WALL-OUTER
G1 F1800 E0.6000               ; Unretract
G1 ...                          ; First extrusion move
```

### No Z-hop / No Y-lift

**IdeaMaker does NOT use Z-hop or Y-lift during mid-layer travels.** This is a critical finding.

- Of 1,656 total retractions, only **287 have Z moves** -- and all 287 of these are **layer transitions** (moving Z to the next layer's value), not Z-hops.
- Mid-layer retractions (1,369 total) have **no Z change at all**. The nozzle stays at the current layer Z during travel.
- Only ONE Z move exceeds the current layer Z: the end-of-print move to Z=87.470 (raising the gantry clear of the model).

Mid-layer retraction example (layer 2):
```
G1 F1800 E-0.6000              ; Retract
G0 F15000 X126.105 Y0.660      ; Travel (no Z change!)
G1 F1800 E0.6000               ; Unretract
```

### Travel Speed

- **Layer transitions:** Z moves at F600, XY travels at F15000
- **Mid-layer travels:** F15000 for long travels between regions; F600-F1500 for short hops within gap-fill/infill patterns
- **Klipper-specific:** Uses `SET_VELOCITY_LIMIT ACCEL=` commands to control acceleration (10000 for travel, 8000 for printing)

### Implications for OrcaSlicer Belt Implementation

Since IdeaMaker does not use Z-hop or Y-lift at all during mid-layer travels, the OrcaSlicer belt Y-lift feature (reinterpreting z_hop as gantry lift) is an OrcaSlicer-specific enhancement, not a replication of IdeaMaker behavior. IdeaMaker relies on:
1. Fast XY-only travel (F15000)
2. Simple retraction/unretraction (0.6 mm)
3. No vertical movement during travel

---

## 6. Header Parameters and Bounding Box

### Header Metadata

```
;Belt Printer: 1
;Belt Base Y: 5074.913
;Belt Base Z: 0.000
;Belt Offset Y: 0.000
;Belt Offset Z: 3585.561
;Belt Gantry Angle: 45
;Belt Remove Z: 0.000
;Belt Repetition: 1
```

### Belt Base Y and Belt Offset Z

These are **IdeaMaker's internal slicer coordinates** for model placement, not values that appear in the output G-code:

- **Belt Base Y: 5074.913** -- The Y position in IdeaMaker's internal coordinate system where the model sits on the belt surface. This is the distance from IdeaMaker's virtual origin to the belt contact point. Note: `5074.913 / sqrt(2) = 3588.5`, very close to Belt Offset Z.

- **Belt Offset Z: 3585.561** -- The Z offset in IdeaMaker's internal system. The relationship `Belt Base Y ~ Belt Offset Z * sqrt(2)` (5074.913 vs 5070.749) confirms these represent the same point in different coordinate frames (virtual vs machine), with the sqrt(2) factor from the 45-degree rotation.

These values are used internally by IdeaMaker's slicer to place the model on the virtual belt surface and then transform to machine coordinates. They do not affect the output G-code coordinates (which start near Y=0, Z=0).

### Bounding Box

```
;Bounding Box: 109.420 140.580 -0.150 68.275 0.000 58.283
```

Interpretation: `X_min X_max Y_min Y_max Z_min Z_max`

| Axis | Min | Max | Range | Meaning |
|---|---|---|---|---|
| X | 109.420 | 140.580 | 31.160 mm | Model width, centered at X=125.0 |
| Y | -0.150 | 68.275 | 68.425 mm | Gantry range (model extends slightly below belt surface) |
| Z | 0.000 | 58.283 | 58.283 mm | Belt travel range (model length along belt) |

**Key observations:**
- **Y_min = -0.150**: The bounding box extends 0.15 mm below the belt surface (Y=0). However, actual G-code extrusions never go below Y=0.050. The -0.150 likely accounts for the model geometry that would intersect the belt plane (the portion "inside" the belt surface that is not printed).
- **X centered at 125.0**: Exactly half of the 250 mm belt width.
- **Z range of 58.283**: This represents the belt travel distance for the model's footprint along the belt, which is smaller than the total Z travel of 82.753 mm because later layers extend further along the belt.

### Extruder Offset

```
;Extruder Offset #1: 25.000 0.000
```
This 25 mm X offset is the distance from the machine's X=0 reference to the nozzle. Since the model is centered at X=125, the nozzle physically operates at 125+25=150 mm from X=0, but G-code coordinates already account for this offset.

---

## 7. Overall Print Statistics

### Type Distribution

| Type | Occurrences (region count) |
|---|---|
| GAP-FILL | 1,012 |
| WALL-OUTER | 649 |
| SOLID-FILL | 607 |
| WALL-INNER | 597 |
| FILL | 360 |
| BOTTOM-SURFACE | 256 |
| TOP-SURFACE | 24 |
| BRIDGE | 12 |

GAP-FILL is the most frequent type, which is unusual for a non-belt print but expected here: the 45-degree inclined slicing creates many triangular gaps between the model's geometry and the inclined layer planes, requiring extensive gap-fill.

### Y Range Evolution Through the Print

The print goes through distinct phases visible in the Y range data:

1. **Layers 0-42 (Z=0.4 to 12.3):** Y_max grows rapidly from 0.3 to 18.0 mm. The Benchy's hull cross-section expands as the belt advances.

2. **Layers 43-63 (Z=12.6 to 18.2):** Y_max stabilizes around 14.8-15.0 mm. This is the straight-sided cabin area of the Benchy.

3. **Layers 64-79 (Z=18.5 to 22.8):** Y_max grows again to 21.7 mm as the cabin roof and chimney build up.

4. **Layers 80-117 (Z=23.0 to 33.5):** Y_max plateaus at exactly 21.745 mm for 38 consecutive layers. This is the flat top deck of the Benchy.

5. **Layers 118-255 (Z=33.8 to 72.6):** Y_max gradually increases to 68.1 mm. This is the tall chimney/smoke stack area.

6. **Layers 256-291 (Z=72.8 to 82.8):** Y_max decreases as the top of the chimney narrows, ending at 38.5 mm.

### Start G-code

The start sequence includes belt-specific operations:
```
G92 E0        ; Reset E axis
G1 Y.1        ; Move gantry slightly up
G1 E15 F1000  ; Prime extruder
G1 Z20 E25 F800  ; Advance belt 20mm while priming
G1 E23        ; Retract slightly
G28 Y         ; Home gantry (Y axis)
G1 E25        ; Un-retract
FMS_on        ; Filament motion sensor on
G1 X250 E50 F2000  ; Purge line across belt width
G92 Z0        ; Reset Z (belt position) to 0
G1 Z.4        ; Advance belt to first layer Z
G1 X0 E75     ; Purge line back
G92 E0 Z0     ; Reset E and Z to 0
```

### End G-code

```
G1 F1800 E-0.6000  ; Final retraction
M82                  ; Switch to absolute extrusion
G0 F600 Z87.470     ; Advance belt ~5mm past model (87.47 - 82.75)
G0 F15000 X125.316 Y38.333  ; Park position
G92 E0               ; Reset extruder
PRINT_END            ; Klipper end macro
```

### Print Speed Summary

| Operation | Feed rate | Speed |
|---|---|---|
| Wall-outer | F1800 (typical), F600 (detailed curves) | 30 mm/s, 10 mm/s |
| Wall-inner | F1800-F5529 | 30-92 mm/s |
| Gap-fill | F600-F1533 | 10-26 mm/s |
| Solid-fill / Bottom-surface | F1355-F2870 | 23-48 mm/s |
| Layer transition travel | F15000 | 250 mm/s |
| Layer Z move | F600 | 10 mm/s |
| Mid-layer short travel | F600-F1533 | 10-26 mm/s |

---

## 8. Key Differences from OrcaSlicer Belt Approach

### Coordinate System

Both IdeaMaker and ORCA_BELT output **machine coordinates** (gantry frame) with:
- Z = constant per layer (belt position)
- Y = gantry height (variable within layer)
- Z increment = user_layer_height / cos(45deg)

This is consistent between the two implementations.

### Z-hop / Y-lift

- **IdeaMaker:** No Z-hop or Y-lift whatsoever. Travels are XY-only at layer Z.
- **ORCA_BELT:** Implements Y-lift (reinterpreting z_hop as gantry lift during travel). This is an OrcaSlicer-specific feature not present in IdeaMaker's approach.

### Gap-Fill Strategy

IdeaMaker uses extensive **45-degree diagonal gap-fill** lines to fill the wedge-shaped voids created by the inclined slicing plane. These are classified as GAP-FILL and appear as the most frequent feature type (1,012 occurrences). OrcaSlicer may handle this differently depending on its gap-fill algorithm.

### Layer Height Annotation

IdeaMaker provides both gantry-direction height and belt-normal height:
```
;HEIGHT:0.283      -- Z increment (gantry direction)
;HEIGHT-BELT:0.200 -- belt-normal thickness (actual layer height)
```
This dual annotation helps with extrusion flow calculation: the physical layer thickness (0.200 mm) determines how much material to deposit, while the Z increment (0.283 mm) determines belt advancement.

### Retraction

IdeaMaker uses a fixed 0.6 mm retraction with no deretraction extra. OrcaSlicer typically uses configurable retraction with optional extra restart length.

### Feed Rate Control

IdeaMaker uses Klipper's `SET_VELOCITY_LIMIT ACCEL=` to control acceleration dynamically:
- F15000 + ACCEL=10000 for travel
- Variable speeds + ACCEL=8000 for printing

### Filament Compensation

```
;Filament Compensation #1: 98.000
M221 T0 S98.00
```
IdeaMaker applies 98% flow rate via M221 at start. This 2% reduction may compensate for the belt printer's geometry effects on extrusion.

---

## 9. Mathematical Verification

### Layer Height Math

```
User setting:       0.200 mm (belt-normal layer height)
Gantry angle:       45 degrees
cos(45deg):         0.7071
Z increment:        0.200 / 0.7071 = 0.2828... ~ 0.283 mm (matches)
First layer:        0.283 mm belt-normal -> 0.283 / 0.7071 = 0.400 mm Z increment (matches)
```

### Total Print Dimensions

```
Belt travel (Z):    82.753 mm (first Z=0.400 to last Z=82.753)
Max gantry (Y):     68.275 mm (from bounding box)
Belt width used:    31.16 mm (X range: 109.42 to 140.58)
Belt center:        125.0 mm (half of 250 mm bed)
```

### Model Size in Real Space

The Benchy's actual dimensions in real (world) space:
- Width (X): ~31 mm
- Length along belt surface: ~58 mm (Z range from bounding box)
- Height above belt (belt-normal): ~48 mm (Y_max * cos(45deg) = 68 * 0.707)
