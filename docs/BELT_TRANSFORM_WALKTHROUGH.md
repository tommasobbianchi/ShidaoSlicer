# Belt Printer Transformation Walkthrough

**A newbie-friendly, step-by-step explanation of how ORCA_BELT transforms coordinates.**

> **Audience:** You don't need to be a math expert. If you know what X/Y/Z mean on a
> regular 3D printer, you can follow this. We'll build up from the physical machine all
> the way to the final G-code, one step at a time.

---

## Table of Contents

1. [Why Do We Need Transforms At All?](#1-why-do-we-need-transforms-at-all)
2. [The Two Worlds: Machine Frame vs Virtual Frame](#2-the-two-worlds-machine-frame-vs-virtual-frame)
3. [The Forward Transform (Machine → Virtual)](#3-the-forward-transform-machine--virtual)
4. [The Inverse Transform (Virtual → Machine)](#4-the-inverse-transform-virtual--machine)
5. [The Full Pipeline: From STL to G-code](#5-the-full-pipeline-from-stl-to-gcode)
6. [Step-by-Step: trafo_centered()](#6-step-by-step-trafo_centered)
7. [Step-by-Step: Slicing in Virtual Space](#7-step-by-step-slicing-in-virtual-space)
8. [Step-by-Step: Inclined Z Computation](#8-step-by-step-inclined-z-computation)
9. [Step-by-Step: The Inverse Transform in GCodeWriter](#9-step-by-step-the-inverse-transform-in-gcodewriter)
10. [The Hot-Reload Config (belt_transform.ini)](#10-the-hot-reload-config-belt_transformini)
11. [The New V-Frame System (BeltPrinter/ module)](#11-the-new-v-frame-system-beltprinter-module)
12. [Worked Example: One Point Through the Whole Pipeline](#12-worked-example-one-point-through-the-whole-pipeline)
13. [Common Pitfalls and FAQ](#13-common-pitfalls-and-faq)

---

## 1. Why Do We Need Transforms At All?

A **normal 3D printer** builds objects layer by layer. Each layer is a perfectly
horizontal slice. The slicer cuts the model into flat pancakes stacked on top of
each other. Simple.

A **belt printer** (like the CR-30 or IdeaFormer IR3 V2) is different:

```
  Normal Printer                Belt Printer (side view)

      Z ↑                          Y (gantry)
        |                           ↗  (tilted 45°)
        |_____ Y                   /
       /                          /_____ Z (belt motion → "infinite")
      X                          X (width, same as normal)
```

On a belt printer:
- The **print bed is a moving belt** (the Z axis moves it)
- The **print head is tilted 45°** relative to the belt (the Y axis)
- Objects are printed at an angle, and the belt can be infinite

**The problem:** OrcaSlicer (and all normal slicers) thinks in horizontal layers.
It doesn't know how to slice at 45°. So we need to **transform** coordinates:

1. **Before slicing:** Rotate the model so the slicer *thinks* it's slicing normally
2. **After slicing:** Rotate the G-code coordinates back to what the belt printer expects

That's the core idea. Everything else is details.

---

## 2. The Two Worlds: Machine Frame vs Virtual Frame

We work with two coordinate systems:

### Machine Frame (F) — What the printer firmware understands

```
   Machine Frame (CR-30 style):

   X = belt width        (left-right, finite ~200mm)
   Y = gantry axis       (tilted 45° from belt, finite ~200mm)
   Z = belt motion        (forward along belt, effectively infinite)
```

When we write `G1 X10 Y5 Z100`, these are **machine frame** coordinates.
The firmware moves motors to reach exactly those positions.

### Virtual Frame (V) — What the slicer works in

```
   Virtual Frame (slicer's world):

   Xv = belt width       (same as machine X)
   Yv = along belt        (forward direction on belt surface)
   Zv = height above belt (perpendicular to belt surface, the "layer height" axis)
```

In this frame, the belt surface is a flat table (Zv = 0) and layers are
horizontal planes at Zv = 0.2mm, 0.4mm, 0.6mm... just like a normal printer.

**The slicer does ALL its work in the Virtual Frame**, then converts to Machine
Frame only at the very end when writing G-code.

---

## 3. The Forward Transform (Machine → Virtual)

The Forward Transform takes machine coordinates and maps them to virtual
(slicer) coordinates. This is used during **setup** — when we position the model
before slicing.

### The Math (for 45°)

```
Yv = Zm                          (belt position maps to virtual Y)
Zv = Ym + Zm × tan(45°) = Ym + Zm   (height = gantry + belt contribution)
Xv = Xm                          (width unchanged)
```

### As a Matrix

The Y/Z part is a 2×2 shear matrix:

```
| Yv |   | 0  1 |   | Ym |
|    | = |      | × |    |
| Zv |   | 1  1 |   | Zm |
```

Reading the matrix row by row:
- Row 1: `Yv = 0×Ym + 1×Zm` → Virtual Y comes entirely from machine Z
- Row 2: `Zv = 1×Ym + 1×Zm` → Virtual Z is the sum of machine Y and Z

### Why "shear" and not "rotation"?

This is NOT a simple rotation! A rotation preserves distances. Our transform
doesn't — it's a **shear**. Think of it like pushing the top of a deck of cards
sideways. This is intentional: the belt's motion creates a skewed geometry that
requires a shear to un-skew.

### In the Code

**File:** `src/libslic3r/BeltTransform.cpp`, function `make_forward_transform()`

```
belt_transform.ini values:
f_yy = 0.0    f_yz = 1.0     →  Yv = 0×Ym + 1×Zm
f_zy = 1.0    f_zz = 1.0     →  Zv = 1×Ym + 1×Zm
```

---

## 4. The Inverse Transform (Virtual → Machine)

The Inverse Transform does the opposite: it takes virtual (slicer) coordinates
and maps them to machine coordinates. This is used during **G-code generation**
— converting slicer output to printer commands.

### The Math (for 45°)

```
Ym = Zv - Yv              (reverse the shear)
Zm = Yv                   (reverse the swap)
Xm = Xv                   (width unchanged)
```

### As a Matrix

```
| Ym |   | -1  1 |   | Yv |
|    | = |       | × |    |
| Zm |   |  1  0 |   | Zv |
```

Reading the matrix row by row:
- Row 1: `Ym = -1×Yv + 1×Zv` → Machine Y is the difference (reverse shear)
- Row 2: `Zm =  1×Yv + 0×Zv` → Machine Z comes entirely from virtual Y (reverse swap)

### Verify: Forward then Inverse = Identity

Let's check. Start with machine point (Ym=3, Zm=7):

**Forward:**
```
Yv = 0×3 + 1×7 = 7
Zv = 1×3 + 1×7 = 10
```

**Inverse:**
```
Ym = -1×7 + 1×10 = 3  ✓
Zm =  1×7 + 0×10 = 7  ✓
```

We get back the original point. The transforms are true inverses.

### In the Code

**File:** `src/libslic3r/BeltTransform.cpp`, function `inverse_transform_point()`

```
belt_transform.ini values:
i_yy = -1.0   i_yz = 1.0     →  Ym = -1×Yv + 1×Zv
i_zy =  1.0   i_zz = 0.0     →  Zm =  1×Yv + 0×Zv
```

Plus offsets (explained later):
```
y_mach_offset = 0.5    → added to Ym to keep belt coordinates positive
z_mach_offset = 2.5    → added to Zm to keep head coordinates positive
```

---

## 5. The Full Pipeline: From STL to G-code

Here's the entire journey of a 3D model through the belt slicer:

```
                        ┌─────────────────────┐
                        │    1. Load STL       │
                        │  (Object Space)      │
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │  2. trafo_centered() │ ← Forward belt transform
                        │  Position model in   │   + Z-shift (-990mm)
                        │  virtual space       │   + X centering
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │  3. Slice            │ ← Horizontal planes in
                        │  Generate layers     │   virtual space (Zv = k×h)
                        │  at Zv heights       │
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │  4. Generate         │ ← Perimeters, infill,
                        │  Toolpaths           │   supports in slice plane
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │  5. Inclined Z       │ ← Z_inclined = layer_z
                        │  Computation         │   + Yv × tan(45°)
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │  6. Inverse          │ ← Virtual → Machine
                        │  Transform           │   Ym = Zv - Yv
                        │  (GCodeWriter)       │   Zm = Yv
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │  7. Write G-code     │ ← G1 X... Y... Z...
                        │  (Machine coords)    │   (firmware-ready)
                        └─────────────────────┘
```

Let's walk through each step in detail.

---

## 6. Step-by-Step: trafo_centered()

**File:** `src/libslic3r/Print.hpp` — `PrintObject::trafo_centered()`

This is the **first** transformation applied to the model. It happens before
slicing, and its job is to position the model in virtual space so the slicer
can slice it normally.

### What it does (for belt printers):

```
Step 1: Start with the raw model transformation (position, scale, rotation)
                    ↓
Step 2: Center X only (NOT Y — belt axis is handled differently)
                    ↓
Step 3: Apply Forward Belt Transform
        (shear matrix: maps machine coords → virtual coords)
                    ↓
Step 4: Apply Z-shift (trafo_z_shift = -990.0mm)
        (brings the model down from belt center to near Zv ≈ 0)
                    ↓
Result: Model positioned in virtual space, ready for slicing
```

### Why the Z-shift?

The model starts at the belt center, which in OrcaSlicer is around Y_machine
= 1000mm (the middle of a 2000mm virtual bed). After the forward transform,
this becomes a very large Zv value. The Z-shift of -990mm brings it back down
so the bottom of the model sits near Zv = 0 (the belt surface).

Think of it as: "The slicer places the model at the center of a huge virtual
bed. We need to slide it down to sit on the belt."

### Code walkthrough:

```cpp
Transform3d PrintObject::trafo_centered() const {
    Transform3d t = this->trafo();           // Raw model transform

    BeltSlicingParams belt_params = this->get_belt_slicing_params();

    if (belt_params.angle != 0.0) {          // Belt printer detected!
        // Step 2: Center X only
        t.pretranslate(Vec3d(-unscale<double>(m_center_offset.x()), 0, 0));

        // Step 3: Apply forward belt transform (shear matrix)
        Transform3d belt_forward = BeltTransform::make_forward_transform(
            Geometry::rad2deg(belt_params.angle));
        t = belt_forward * t;

        // Step 4: Z-shift to bring model near Zv=0
        double z_shift = BeltTransform::get_trafo_z_shift();  // -990.0
        t.translate(Vec3d(0, 0, z_shift));
    }
    return t;
}
```

### Additional: Adjusting Z min to 0

**File:** `src/libslic3r/PrintObjectSlice.cpp`

After `trafo_centered()`, the code checks if the model's minimum Zv is exactly
0. If not (due to rounding), it applies one more small translation:

```cpp
// Make sure the model sits exactly on the belt (Zv_min = 0)
BoundingBoxf3 bbox = model_object->raw_bounding_box();
bbox = bbox.transformed(slice_trafo);
slice_trafo.pretranslate(Vec3d(0, 0, -bbox.min.z()));
```

This is a safety net — it ensures the first layer starts exactly at Zv = 0.

---

## 7. Step-by-Step: Slicing in Virtual Space

After `trafo_centered()`, the model is in virtual space. Now the slicer can
slice it with perfectly horizontal planes.

### How OrcaSlicer's normal slicer sees it:

```
Virtual Space (what the slicer sees):

    Zv ↑
    6  |  ─────── Layer 3 (Zv = 0.6)
    4  |  ─────── Layer 2 (Zv = 0.4)
    2  |  ─────── Layer 1 (Zv = 0.2)
    0  |========= Belt surface (Zv = 0)
       └──────────→ Yv (along belt)
```

The slicer generates layers at:
- Zv = 0 + first_layer_height
- Zv = first_layer_height + layer_height
- Zv = first_layer_height + 2 × layer_height
- ... and so on

Each layer contains 2D toolpaths (perimeters, infill) in the XY-virtual plane.
At this point, the slicer has no idea it's working on a belt printer — it thinks
it's slicing a completely normal model.

### The Oblique Normal (alternative approach)

There's also code for an **oblique slicing** approach that predates the current
virtual-frame method:

```cpp
BeltSlicingParams(double angle_rad) : angle(angle_rad) {
    normal = Vec3d(0.0, -std::sin(angle), std::cos(angle));
}
```

This defines a slicing plane normal that's tilted at 45°. Instead of slicing at
constant Z, it slices at constant `V = Y×cos(θ) + Z×sin(θ)`. Both approaches
produce equivalent results, but the virtual-frame approach is cleaner.

---

## 8. Step-by-Step: Inclined Z Computation

This is where belt printing gets clever. During G-code generation, each
extrusion point gets a **modified Z** that varies within the same layer.

**File:** `src/libslic3r/GCode.cpp` — `compute_belt_inclined_z()`

### The Problem

On a normal printer, all points in layer N have the same Z height.
On a belt printer, the Z height must vary because the belt is tilted:

```
  Normal printer layer:            Belt printer "layer" (side view):

  Z = 0.4 ─────────────           Z varies!
                                        ╱  Higher Z at larger Y
                                      ╱
                                    ╱  Lower Z at smaller Y
```

### The Formula

```
Z_inclined = layer_z + Yv × tan(belt_angle)
```

For 45°, `tan(45°) = 1`, so:

```
Z_inclined = layer_z + Yv
```

This means: for every 1mm you move forward on the belt (Yv), the Z goes
up by 1mm (because the belt is at 45°).

### Code:

```cpp
double GCode::compute_belt_inclined_z(const Vec2d& point_gcode, double layer_z) const
{
    if (!m_belt_inclined_gcode) return layer_z;  // Normal printer: Z unchanged

    double tan_angle = std::tan(m_belt_angle_radians);  // tan(45°) = 1.0
    double inclined_z = layer_z + point_gcode.y() * tan_angle;
    return inclined_z;
}
```

### Where it's called:

In the extrusion loop (`GCode.cpp`, `_extrude()` method):

```cpp
// For each point on the extrusion path:
Vec2d dest2d = this->point_to_gcode(line.b);

if (m_belt_inclined_gcode) {
    double inclined_z = compute_belt_inclined_z(dest2d, m_nominal_z);
    // Use 3D extrusion (X, Y, Z all specified)
    gcode += m_writer.extrude_to_xyz(
        Vec3d(dest2d.x(), dest2d.y(), inclined_z), dE, comment);
} else {
    // Normal printer: only X, Y (Z set once per layer)
    gcode += m_writer.extrude_to_xy(dest2d, dE, comment);
}
```

### Important consequence: No arc fitting!

Because Z varies continuously along each move, **G2/G3 arc commands can't be
used** in belt mode. Arcs assume constant Z within the arc, which isn't true
when the belt is tilted. The code disables arc fitting when belt inclined mode
is active.

---

## 9. Step-by-Step: The Inverse Transform in GCodeWriter

This is the **final transformation** — converting virtual coordinates to machine
coordinates for the actual G-code output.

**File:** `src/libslic3r/GCodeWriter.cpp` — `GCodeG1Formatter::emit_xyz()`

### What happens:

When the G-code generator calls `extrude_to_xyz(point)`:

```
Virtual point (Xv, Yv, Zv)   (from inclined Z computation)
          │
          ▼
   Add Z offset (z_offset)
          │
          ▼
   Apply inverse_transform_point()
          │
          ▼
   Machine point (Xm, Ym, Zm)
          │
          ▼
   Write "G1 X{Xm} Y{Ym} Z{Zm}"
```

### The inverse transform in detail:

```cpp
// BeltTransform::inverse_transform_point(pt, angle)

// Load config from belt_transform.ini (hot-reloadable!)
BeltConfig cfg = get_config();

// Apply the 2×2 inverse matrix + shifts + offsets:
double y_in = pt.y() + cfg.i_y_shift;       // Apply Y shift
double z_in = pt.z() + cfg.i_z_shift;       // Apply Z shift

double y_out = cfg.i_yy * y_in + cfg.i_yz * z_in;   // Matrix multiply
double z_out = cfg.i_zy * y_in + cfg.i_zz * z_in;

y_out += cfg.y_mach_offset;    // Add machine Y offset (0.5mm)
z_out += cfg.z_mach_offset;    // Add machine Z offset (2.5mm)

return Vec3d(pt.x(), y_out, z_out);
```

With the default values:
```
Ym = -1×Yv + 1×Zv + 0.5      (belt movement + offset)
Zm =  1×Yv + 0×Zv + 2.5      (head height + offset)
```

### Why the offsets?

The offsets (`y_mach_offset = 0.5`, `z_mach_offset = 2.5`) ensure that **all
machine coordinates are positive**. Without them, the first layer might produce
negative Y or Z values, which many firmwares reject or interpret incorrectly.

The values were tuned empirically by comparing with IdeaMaker's output:
- IdeaMaker: Y starts at 0.05mm, Z starts at 0.40mm
- ORCA_BELT: Y starts at 0.70mm, Z starts at 0.31mm (close enough!)

---

## 10. The Hot-Reload Config (belt_transform.ini)

**File:** `belt_transform.ini` (project root)

All transform parameters are loaded from this INI file **at runtime**. This
means you can edit the file while OrcaSlicer is running, and the next slice
will use the updated values. No recompilation needed!

### Full parameter reference:

```ini
[Forward]
f_yy = 0.0         # Yv = f_yy × Ym + f_yz × Zm
f_yz = 1.0         #   → Yv comes from Zm (swap)
f_zy = 1.0         # Zv = f_zy × Ym + f_zz × Zm
f_zz = 1.0         #   → Zv is Ym + Zm (shear)
f_y_shift = 0.0    # Shift applied to Yv after matrix

[Inverse]
i_yy = -1.0        # Ym = i_yy × Yv + i_yz × Zv
i_yz = 1.0         #   → Ym = Zv - Yv (reverse shear)
i_zy = 1.0         # Zm = i_zy × Yv + i_zz × Zv
i_zz = 0.0         #   → Zm = Yv (reverse swap)
i_y_shift = 0.0    # Shift applied to Yv before matrix
i_z_shift = 0.0    # Shift applied to Zv before matrix
y_mach_offset = 0.5   # Added to final Ym (keeps coords positive)
z_mach_offset = 2.5   # Added to final Zm (keeps coords positive)
trafo_z_shift = -990.0 # Applied in trafo_centered() to bring model to belt
```

### When to tweak these values:

| Symptom | Parameter to adjust |
|---------|-------------------|
| Model floating above belt | Decrease `trafo_z_shift` (more negative) |
| Model below belt surface | Increase `trafo_z_shift` (less negative) |
| Negative Y in G-code | Increase `y_mach_offset` |
| Negative Z in G-code | Increase `z_mach_offset` |
| First layer too high | Decrease `z_mach_offset` |
| Print shifted along belt | Adjust `i_y_shift` or `f_y_shift` |

---

## 11. The New V-Frame System (BeltPrinter/ module)

The project also contains a **newer, more principled** transformation system in
`src/libslic3r/BeltPrinter/`. This is the target architecture that will
eventually replace the shear-matrix approach.

### Key difference: Orthonormal transforms only

The new system uses a **permutation matrix** M_VF (orthonormal — no shear, no
scaling) to map between Virtual (V) and Firmware (F) frames:

```
For CR-30:
          | 1  0  0 |
M_VF  =   | 0  0  1 |   →  Xv→Xf,  Yv→Zf,  Zv→Yf
          | 0  1  0 |
```

This means:
- **Xv → Xf**: Width axis is the same
- **Yv → Zf**: Belt travel (Virtual Y) maps to firmware Z
- **Zv → Yf**: Layer height (Virtual Z) maps to firmware Y

The shearing/inclination is handled **before** this mapping, during slicing,
rather than baked into the coordinate transform.

### V→F Transform:

```
point_firmware = M_VF × point_virtual + translation_VF
```

### F→V Transform (inverse):

Because M_VF is orthonormal, its inverse is just its transpose:

```
point_virtual = M_VF^T × (point_firmware - translation_VF)
```

### Files:

| File | Role |
|------|------|
| `VirtualBeltFrame.hpp/.cpp` | Defines Xv/Yv/Zv coordinate system and utilities |
| `BeltTransforms.hpp/.cpp` | V↔F mapping with orthonormality validation |
| `MachineProfile.hpp/.cpp` | Full machine description (angles, volumes, dynamics) |
| `MachineProfileConfig.cpp` | Factory: creates profile from PrintConfig |
| `BeltPlacement.hpp/.cpp` | Drop-to-belt, offset, printable region validation |

### Relationship to the current (shear) system:

```
CURRENT SYSTEM (working, tuned):
  trafo_centered() → [shear forward] → slice → [inclined Z] → [shear inverse] → G-code

NEW SYSTEM (under development):
  mesh → [transform to V] → [drop to belt] → slice (planar in V) → [V→F mapping] → G-code
```

The new system separates concerns more cleanly:
1. The inclined slicing geometry is handled by transforming the mesh first
2. The coordinate mapping is a pure permutation (no shear)
3. No need for `trafo_z_shift` hacks

Both systems coexist and will be selectable via a `use_native_belt_frame` feature flag.

---

## 12. Worked Example: One Point Through the Whole Pipeline

Let's trace a single extrusion point from the model all the way to G-code.

### Setup

- Model: 20mm cube, bottom-left corner at origin
- Belt angle: 45°
- Layer height: 0.2mm
- We'll follow the point at model position **(10, 15, 0)** (center-X, Y=15mm along belt, sitting on belt)

### Step 1: Object Space

```
Point in model: (Xm=10, Ym=15, Zm=0)
```

The model is placed at belt center in OrcaSlicer, so Y_machine ≈ 1000mm.

### Step 2: trafo_centered()

**2a. Raw position:** After OrcaSlicer positions it on the bed:
```
(Xm=10, Ym=1000+15, Zm=0) = (10, 1015, 0)
```

**2b. Center X:**
```
(10 - center_offset_x, 1015, 0) ≈ (0, 1015, 0)
```
(Assuming X center offset is 10)

**2c. Apply forward transform (shear matrix):**
```
Yv = 0×1015 + 1×0 = 0
Zv = 1×1015 + 1×0 = 1015
Xv = 0
```
Point is now: `(0, 0, 1015)`

**2d. Apply Z-shift (-990):**
```
(0, 0, 1015 - 990) = (0, 0, 25)
```

**2e. Adjust to Zv_min=0:** (the model's min Zv might not be exactly 0)
```
After bounding box adjustment: (0, 0, ~0)  (this was the bottom face)
```

### Step 3: Slicing

The slicer generates layers at Zv = 0.2, 0.4, 0.6, etc.
Our point on the bottom face is on layer 1 (Zv = 0.2).

After toolpath generation, let's say we have an extrusion point at:
```
Virtual: (Xv=0, Yv=8.5, Zv=0.2)    ← (on layer 1, 8.5mm along belt)
```

### Step 4: Inclined Z Computation

```
Z_inclined = layer_z + Yv × tan(45°)
           = 0.2    + 8.5 × 1.0
           = 8.7
```

Point becomes: `(Xv=0, Yv=8.5, Z_inclined=8.7)`

### Step 5: Inverse Transform

```
Ym = -1 × 8.5 + 1 × 8.7 + 0.5 = 0.7
Zm =  1 × 8.5 + 0 × 8.7 + 2.5 = 11.0
Xm = 0
```

### Step 6: G-code Output

```gcode
G1 X0.000 Y0.700 Z11.000 E1.234
```

The firmware will:
- Keep the nozzle at X=0 (center of belt width)
- Move the belt to Y=0.7mm from the leading edge
- Move the head to Z=11.0mm above the belt

This point sits on the belt surface at 45°, exactly where it should be!

---

## 13. Common Pitfalls and FAQ

### Q: Why is trafo_z_shift so large (-990)?

Because OrcaSlicer internally places objects at the center of the build plate,
which has Y ≈ 1000mm. After the forward transform, this Y becomes a huge Z.
The -990 shift brings it back to near zero. It's not a hack — it's compensating
for OrcaSlicer's internal positioning.

### Q: Why shear and not rotation?

A pure rotation would distort distances. The belt kinematics create a sheared
geometry: as the belt moves forward (Z_machine), the print head stays at a fixed
angle (Y_machine). This is fundamentally a shear, not a rotation.

### Q: Why are there TWO transform systems?

Historical reasons. The shear matrix system (`BeltTransform.cpp`) was developed
first and is currently in production. The new V-frame system (`BeltPrinter/`)
is a cleaner architecture being developed in parallel. They will coexist behind
a feature flag until the new system is fully validated.

### Q: What happens if I change belt_transform.ini while slicing?

The config is reloaded on every call to `get_config()`. So if you change it
mid-slice, different layers might use different parameters. Usually you want to
edit it between slices, not during one.

### Q: Why can't belt mode use G2/G3 arcs?

Arc commands (G2/G3) assume the Z height is constant during the arc. In belt
inclined mode, Z varies continuously with Y position (`Z = layer_z + Y×tan(θ)`).
A straight line segment in virtual space maps to a curve in machine space,
which can't be represented by a simple circular arc.

### Q: What's the difference between `belt_angle` and `gantry_angle_theta_deg`?

They're the same angle (45° for CR-30 style printers) stored in different
places:
- `belt_angle` — in `PrintConfig`, used by the current shear system
- `gantry_angle_theta_deg` — in `BeltMachineProfile`, used by the new V-frame system

### Q: How do I know the transforms are correct?

Compare the output with IdeaMaker (a known-working belt slicer):
- IdeaMaker Y range: 0.05mm to 27.93mm
- ORCA_BELT Y range: 0.70mm to 40.30mm (slightly different model positioning, but same ballpark)
- Both have 0% negative coordinates

There's also `scripts/belt_transform_validator.py` that validates the math
independently in Python.

---

## Visual Summary

```
                    MODEL (STL)
                        │
          ┌─────────────┼─────────────┐
          │    trafo_centered()        │
          │                            │
          │  1. Center X               │
          │  2. Forward shear          │
          │     (machine → virtual)    │
          │  3. Z-shift (-990mm)       │
          │  4. Snap Zv_min to 0       │
          └─────────────┬─────────────┘
                        │
              VIRTUAL SPACE (flat belt)
                        │
          ┌─────────────┼─────────────┐
          │  Standard OrcaSlicer       │
          │  slicing engine            │
          │  (horizontal planes at     │
          │   Zv = k × layer_height)   │
          └─────────────┬─────────────┘
                        │
              TOOLPATHS (Xv, Yv per layer)
                        │
          ┌─────────────┼─────────────┐
          │  compute_belt_inclined_z() │
          │                            │
          │  Z = layer_z + Yv × tan(θ) │
          │  (Z varies within layer!)  │
          └─────────────┬─────────────┘
                        │
              INCLINED POINTS (Xv, Yv, Z_inclined)
                        │
          ┌─────────────┼─────────────┐
          │  GCodeWriter inverse       │
          │  transform                 │
          │                            │
          │  Ym = -Yv + Z_incl + 0.5   │
          │  Zm =  Yv          + 2.5   │
          │  Xm =  Xv                  │
          └─────────────┬─────────────┘
                        │
              G-CODE (G1 X... Y... Z...)
```

---

*Last updated: 2026-02-12*
*Part of the ORCA_BELT project — OrcaSlicer fork with native belt printer support.*
