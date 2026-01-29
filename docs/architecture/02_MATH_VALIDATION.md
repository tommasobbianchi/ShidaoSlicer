# Math Validation: Belt Slicing

**Generated:** 2026-01-29
**Source:** Analyzed `deps_ref/grid-apps/src/kiri/run/worker.js` and `deps_ref/BeltPrinterSlicing`.

## 1. Validated Strategy: Virtual Upright

Kiri:Moto explicitly performs a mesh rotation before slicing (`widget.rotate` in `worker.js`). This confirms the strategy of **Pre-Rotating** the mesh to align the slicing planes (which are physically inclined) with the logical horizontal slicing planes of the engine.

## 2. Coordinate Systems

### A. Machine Frame (Physical G-code)

- **X**: Belt Width (Standard)
- **Y**: Gantry Axis (Inclined at $\theta = 45^\circ$)
- **Z**: Belt Motion (Infinite)

### B. Virtual Slicing Frame (Inside Orca)

- **X**: Same as Machine X
- **U**: Horizontal axis in slicer (corresponds to Belt Z minus shear)
- **V**: Vertical axis in slicer (corresponds to Layer Height)

## 3. Certified Transform Formulas

### Forward Transform (Model $M \rightarrow$ Virtual $V$)

To slice a models intended for belt printing, we rotate it so the "bottom" (belt side) is flat on the virtual bed.
Transform: **Rotate around X by $-\theta$ (-45°)**.

$$
y_{virt} = y_{model} \cdot \cos(-\theta) - z_{model} \cdot \sin(-\theta) \\
z_{virt} = y_{model} \cdot \sin(-\theta) + z_{model} \cdot \cos(-\theta)
$$

### Inverse Transform (Virtual $V \rightarrow$ Machine $P$)

Used during G-code emission (`GCodeWriter`).
Given a point $(x, u, v)$ in Virtual frame (where $v$ is layer height Z in slicer):

$$
X_{mach} = x \\
Y_{mach} = v / \cos(\theta) \\
Z_{mach} = u - v \cdot \tan(\theta)
$$

**For $\theta = 45^\circ$:**

$$
X_{mach} = x \\
Y_{mach} = v \cdot \sqrt{2} \\
Z_{mach} = u - v
$$

## 4. Derived Constraints

### Bed Boundary (Clipping)

Geometry must not be generated "below" the belt. In Virtual Frame, the belt plane is NOT $z=0$, but the inclined plane transformed.
Actually, if we Pre-Rotate the model, the "Belt Plane" becomes the $Z=0$ plane in the slicer!
**Correction:**
If we rotate the model by -45°, the face touching the belt becomes horizontal at $Z_{virt}=0$.
So basic clipping at $Z_{virt} < 0$ handles the "under belt" check naturally for the object.

**However**, for Supports and Brims, we must ensure they respect the _belt start_ and _belt width_.

- Belt Start (Lead-In): $u \ge 0$ (or offset).

## 5. Conclusion

The **Shear Logic** described in `01_SHEAR_TRANSFORM_LOGIC.md` is mathematically equivalent to the **Rotation Logic** found in Kiri, but Rotation is easier to implement in existing Slicers (just a matrix op on the model). The Shear logic is implicitly handled by the coordinate re-mapping at the end.

**Decision:** Implement via **Model Rotation** (as Kiri) + **Inverse Coordinate Mapping** (as derived).
