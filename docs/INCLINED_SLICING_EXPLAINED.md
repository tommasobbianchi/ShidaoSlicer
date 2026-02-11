# Understanding Inclined Slicing for Belt Printers

*A beginner-friendly guide to the math behind belt printer G-code generation*

---

## The Problem: Why Can't We Just Slice Normally?

Imagine you're slicing a simple cube for a regular 3D printer. The slicer cuts the model into horizontal layers, like slicing a loaf of bread. Each layer is printed at a constant Z height - layer 1 at Z=0.2mm, layer 2 at Z=0.4mm, and so on.

```
Regular Printer (side view):

    ┌─────────┐  ← Layer 3 (Z=0.6mm)
    ├─────────┤  ← Layer 2 (Z=0.4mm)
    └─────────┘  ← Layer 1 (Z=0.2mm)
    ═══════════  ← Flat bed
```

But a **belt printer** is different. The print surface is tilted at 45 degrees! The "bed" is actually a moving conveyor belt, and the print head approaches it at an angle.

```
Belt Printer (side view):

         Print Head
              ↓
              ▼
             ╱
            ╱  ← Object printed on 45° surface
           ╱
    ══════╱════  ← Belt moving this direction →
```

If we used horizontal slices on a 45° surface, the layers wouldn't align properly with the belt. We need **inclined slicing**.

---

## The Solution: Making Z Vary with Y

Here's the key insight: on a belt printer, as you move along the belt direction (Y), you're also moving up or down relative to the print head (Z).

Think of it like walking up a ramp:
- At the bottom of the ramp, you're at a low height
- As you walk forward, your height increases
- The relationship is: `height = distance × slope`

For a 45° belt, the slope is `tan(45°) = 1`, which means:
- Move 1mm along the belt → Move 1mm up in height

---

## The Formula Explained

```
Z_virt = layer_z + Y_point × tan(belt_angle)
```

Let's break this down piece by piece:

### `layer_z` - The Base Layer Height

This is the height of the current layer in "virtual" (horizontal slicing) coordinates. For example:
- Layer 1: `layer_z = 0.2mm`
- Layer 2: `layer_z = 0.4mm`
- Layer 50: `layer_z = 10.0mm`

### `Y_point` - Position Along the Belt

This is where you are on the Y axis (the belt direction) for the current extrusion point. Different points in the same layer have different Y values:

```
Same layer, different Y positions:

Point A (Y=0mm)     Point B (Y=10mm)    Point C (Y=20mm)
       •                  •                   •
       │                  │                   │
       └──────────────────┴───────────────────┘
                    Belt direction →
```

### `tan(belt_angle)` - The Slope Factor

This converts horizontal distance into vertical rise:

| Belt Angle | tan(angle) | Meaning |
|------------|------------|---------|
| 30° | 0.577 | 1mm forward = 0.577mm up |
| 45° | 1.000 | 1mm forward = 1mm up |
| 60° | 1.732 | 1mm forward = 1.732mm up |

For most belt printers (like the CR-30 or IdeaFormer IR3), the angle is **45 degrees**, so `tan(45°) = 1`.

### Putting It All Together

For a 45° belt printer, the formula simplifies to:

```
Z_virt = layer_z + Y_point × 1
Z_virt = layer_z + Y_point
```

**Example:** Printing layer 1 (layer_z = 0.2mm) with three points:

| Point | Y_point | Calculation | Z_virt |
|-------|---------|-------------|--------|
| A | 0mm | 0.2 + 0 × 1 | 0.2mm |
| B | 5mm | 0.2 + 5 × 1 | 5.2mm |
| C | 10mm | 0.2 + 10 × 1 | 10.2mm |

Even though all three points are on "layer 1", they have **different Z heights** in the output G-code!

---

## Visual Comparison

### Without Inclined Slicing (Wrong!)

```
G-code output:         What it prints on belt:

G1 X10 Y0 Z0.2            ═══════
G1 X10 Y5 Z0.2         Flat layers don't
G1 X10 Y10 Z0.2        match the 45° surface!
                              ╱
                             ╱
                       ═════╱═════
```

### With Inclined Slicing (Correct!)

```
G-code output:         What it prints on belt:

G1 X10 Y0 Z0.2              ╱
G1 X10 Y5 Z5.2             ╱  Layers follow
G1 X10 Y10 Z10.2          ╱   the belt surface!
                         ╱
                   ═════╱═════
```

---

## Why This Matters

Without inclined slicing, your print would have several problems:

1. **Layer adhesion issues** - Layers wouldn't stack properly on the angled surface
2. **Dimensional inaccuracy** - The print would be distorted
3. **Collision risk** - The nozzle might crash into already-printed material

With inclined slicing, each extrusion point is at the correct height for the belt surface, ensuring:
- Proper layer stacking
- Accurate dimensions
- Safe nozzle clearance

---

## In Code

Here's how it looks in the OrcaSlicer implementation:

```cpp
double GCode::compute_belt_inclined_z(const Vec2d& point, double layer_z) const
{
    // Skip if inclined mode is disabled
    if (!m_belt_inclined_gcode) {
        return layer_z;  // Just use flat layer height
    }

    // Calculate the slope factor
    double tan_angle = std::tan(m_belt_angle_radians);

    // Apply the formula: Z = layer_z + Y × tan(angle)
    double inclined_z = layer_z + point.y() * tan_angle;

    return inclined_z;
}
```

---

## Summary

| Concept | Explanation |
|---------|-------------|
| **Belt printer** | Has a 45° angled print surface |
| **Inclined slicing** | Adjusts Z height based on Y position |
| **The formula** | `Z = layer_z + Y × tan(belt_angle)` |
| **For 45° belts** | `Z = layer_z + Y` (since tan(45°) = 1) |
| **Result** | G-code with varying Z within each layer |

---

## Further Reading

- [status.md](../status.md) - Current implementation status
- [todo.md](../todo.md) - Project roadmap
- [PROMPT_05_INTEGRATION_LOGIC.md](runbook/PROMPT_05_INTEGRATION_LOGIC.md) - Technical implementation details

---

*This document is part of the ORCA_BELT project - adding native belt printer support to OrcaSlicer.*
