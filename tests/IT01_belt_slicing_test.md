# IT01: Belt Slicing Integration Test

## Objective

Verify end-to-end V-frame slicing pipeline produces correct G-code for belt printers.

## Test Fixture

### Input: Simple Cube Model

**File**: `tests/fixtures/belt_test_cube.stl`

- Dimensions: 20x20x20mm
- Position: Centered at origin
- Purpose: Simple geometry for validation

### Belt Printer Config

**File**: `tests/fixtures/belt_config.json`

```json
{
  "printer_model": "Test_Belt_CR30",
  "belt_printer": true,
  "belt_angle": 45.0,
  "belt_axis": "Z",
  "layer_height": 0.2,
  "first_layer_height": 0.25,
  "nozzle_diameter": 0.4,
  "filament_diameter": 1.75
}
```

## Test Procedure

### Step 1: CLI Slice

```bash
cd /home/user/projects/ORCA_BELT/build
./orca-slicer --no-gui \
  --load tests/fixtures/belt_config.json \
  --load tests/fixtures/belt_test_cube.stl \
  --slice 0 \
  --export-gcode /tmp/it01_output.gcode
```

### Step 2: Validate G-code Output

**Check 1: Coordinate Mapping** (CR30: Xv→X, Yv→Z, Zv→Y)

```bash
# Extract first layer extrusion moves
grep "^G1.*E" /tmp/it01_output.gcode | head -20

# Expected pattern for Z-belt CR30:
# - X coordinates: ~-10 to +10 (cube width in Xv)
# - Y coordinates: progressive increase (Zv layers)
# - Z coordinates: stable or slowly increasing (Yv belt travel)
```

**Check 2: Layer Count**

```bash
# Count layer comments
grep -c "; layer" /tmp/it01_output.gcode

# Expected: ~100 layers (20mm height / 0.2mm layer = 100)
```

**Check 3: Slice Normal Application**

```python
# Verify slice planes are at 45° to vertical
import re

gcode = open('/tmp/it01_output.gcode').read()
layers = re.findall(r'; layer (\d+), Z = ([\d.]+)', gcode)

# For 45° belt, each layer advance should have:
# ΔY_firmware ≈ layer_height * cos(45°) ≈ 0.14mm
# ΔZ_firmware ≈ layer_height * sin(45°) ≈ 0.14mm

for i in range(1, min(10, len(layers))):
    prev_z = float(layers[i-1][1])
    curr_z = float(layers[i][1])
    delta = curr_z - prev_z
    print(f"Layer {i}: ΔZ = {delta:.3f}mm (expect ~0.14mm)")
```

**Check 4: V-Frame Transform Verification**

```bash
# First layer should have Y ≈ first_layer_height * cos(45°)
grep "G1.*Z" /tmp/it01_output.gcode | head -1

# Expected Y ≈ 0.25 * 0.707 ≈ 0.177mm (for CR30)
```

## Success Criteria

✅ **Compilation**: orca-slicer builds without errors
✅ **Slicing**: CLI generates G-code without crashes
✅ **Coordinates**: X/Y/Z mapping matches V→F transform
✅ **Layers**: Correct layer count for object height
✅ **Normal**: Slice planes at configured belt angle

## Failure Modes

❌ **Segfault**: V-frame transform issue in slice_volumes()
❌ **Wrong coords**: M_VF matrix mapping incorrect
❌ **Missing include**: BeltPrinter headers not found
❌ **Layer mismatch**: Slicing params not using V-frame height

## Acceptance

Test passes if:

1. G-code generated successfully
2. First 10 layers show consistent ΔY ~= layer_height \* cos(angle)
3. Total layers = object_height / layer_height ± 1
4. No crashes or assertion failures
