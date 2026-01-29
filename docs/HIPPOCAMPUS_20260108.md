# ORCA_BELT Hippocampus - Session 2026-01-08

**Date**: 2026-01-08 07:04  
**Status**: 🟡 M_VF Fix Applied - CLI Slicing Blocked

---

## ✅ Completed

### M_VF Matrix Fix

**File**: `src/libslic3r/BeltPrinter/MachineProfileConfig.cpp`

**Root Cause**: M_VF matrix for Z-belt was missing Z-scaling and Y-shear.

**Fix** (lines 31-50):

```cpp
double z_scale = 1.0 / cos(α);  // ≈1.4142 for 45°
double tan_a = tan(α);          // = 1 for 45°

profile.M_VF <<
    1,       0,        0,   // Xm = Xv
    0,       0,  z_scale,   // Ym = Zv × 1.4142
    0,       1,    tan_a;   // Zm = Yv + Zv × 1.0
```

**Math Verification**: Belt (Zm) increases 5→15mm for 10mm cube ✓

---

## 🔴 Blocked: CLI Slicing Error

**Symptom**: `throw SlicingError("empty initial layer")` at `GCode.cpp:1593`

**Cause**: First layer has no extrusions detected with new M_VF.

**Note**: Old G-codes worked (e.g., `/tmp/belt_petg_FINAL.gcode` from 2026-01-07)

**Theory**: New M_VF with shear may affect slicing pipeline, not just G-code emission.

---

## Next Steps

1. Investigate if M_VF is applied during slicing or only G-code emission
2. May need to keep old M_VF for slicing and apply shear only in G-code
