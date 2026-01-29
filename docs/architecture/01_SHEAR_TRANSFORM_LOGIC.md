# Belt Printer Slicing Logic: Shear Transformation

## Core Philosophy

Unlike standard printers where slicing planes are orthogonal to the Z-axis, Belt Printers require slicing along inclined planes (typically 45°) relative to the bed.

Instead of **Rotating** the object (which creates artifacts with supports and gravity handling), we apply a **Shear Transformation** to the slicing volume.

### The Concept

Imagine the slicing volume as a deck of cards.

- **standard Slicing**: The deck is a vertical stack.
- **Belt Slicing**: The deck is "sheared" sideways (like pushing the top of the deck). The cards remain parallel to each other, but the stack leans.
- The **Belt** moves along the shearing direction (Y).
- The **Gantry** slices along the angled face of the deck.

To implement this in a slicer that expects horizontal Z-layers, we transform the mesh vertices from **Machine Coordinate System** to **Shear (Slicer) Coordinate System**.

## Coordinate Systems

1.  **Machine System ($X_m, Y_m, Z_m$)**: The physical dimensions.

    - $X_m$: Gantry Width.
    - $Y_m$: Belt Direction (infinite).
    - $Z_m$: Nozzle Height (perpendicular to belt).

2.  **Slicer System ($X_s, Y_s, Z_s$)**: The orthogonal space used for layer calculations.
    - $Z_s$: Corresponds to the sequential "Layers" (which are actually increments of the belt).

## Transformation Matrix (Machine $\rightarrow$ Slicer)

We apply a Z-Shear based on Y.
Assuming `alpha` ($\alpha$) is the Belt Angle (typically 45°):

$$
T_{shear} = \begin{bmatrix}
1 & 0 & 0 & 0 \\
0 & 1 & 0 & 0 \\
0 & \tan(\alpha) & 1 & 0 \\
0 & 0 & 0 & 1
\end{bmatrix}
$$

The mapping equations are:

- $X_s = X_m$
- $Y_s = Y_m$
- $Z_s = Z_m + Y_m \cdot \tan(\alpha)$

This aligns the inclined planes of the machine ($Z_m + Y_m \tan(\alpha) = \text{const}$) to horizontal planes in the slicer ($Z_s = \text{const}$).

## Benefits

- **Supports**: Gravity direction remains implicitly more consistent with the "base" of the model.
- **Geometry**: Topologically preserves flatness relative to the belt Z-plane, avoiding "floating corner" issues common with rotation.
- **Infinity**: The $Y$ axis remains the belt axis, allowing correct handling of "infinite" dimensions.

## Support Generation Implications

The Shear Slicing logic separates **Object Slicing** from **Support Generation**.

### The Problem

- **Standard Slicers** generate supports as "Vertical Towers" in Slicer Space ($X_s, Y_s$ fixed, extending down to $Z_{min}$).
- **In Machine Space**, these "Vertical Towers" become **45° Leaning Columns** due to the inverse shear.
- While 45° supports (parallel to the gantry) are sometimes desirable for belt printers, **Gravity acts Vertically ($Z_m$)**.
- Ideally (and in software like IdeaMaker), supports should be **Vertical in Machine Space** (90° relative to the bed).

### The Solution (Vertical Supports)

To achieve Vertical Machine Supports, we cannot simply use the standard support generator on the sheared mesh.

- Vertical Machine Supports ($X_m, Y_m$ constant) map to **Diagonal Lines** in Slicer Space ($Y_s$ decreases as $Z_s$ decreases).
- **Implementation Strategy**:
  1.  Generate Support Volumes based on the **Unsheared Mesh** (Machine Space) using standard vertical projection.
  2.  Apply the **Shear Transformation** to these Support Volumes.
  3.  Slice the Sheared Support Volumes along with the Sheared Object.

This ensures that the final printed supports stand vertically upright relative to gravity, even though they appear slanted in the slicer's layer view.
