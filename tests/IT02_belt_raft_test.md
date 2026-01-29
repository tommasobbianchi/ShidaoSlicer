# IT02: Belt Raft Integration Test

## Objective

Verify BeltRaft module integrates correctly with V-frame slicing pipeline.

## Test Fixture

### Input: Tall Thin Model

**File**: `tests/fixtures/belt_test_tower.stl`

- Dimensions: 10x10x50mm (tall tower)
- Purpose: Tests upstream raft extension

### Belt Config with Raft

**File**: `tests/fixtures/belt_raft_config.json`

```json
{
  "printer_model": "Test_Belt_CR30",
  "belt_printer": true,
  "belt_angle": 45.0,
  "belt_axis": "Z",
  "layer_height": 0.2,
  "raft_layers": 3,
  "raft_contact_distance": 0.2,
  "raft_expansion": 5.0
}
```

## Integration Point

**Location**: `PrintObject::slice()` (early, before layer generation)

**Insertion**:

```cpp
void PrintObject::slice()
{
    // ... existing layer generation ...

    // Belt Raft: Insert raft layers if enabled
    if (this->is_belt_printer() && m_config.raft_layers > 0) {
        const auto& profile = *this->belt_profile();

        // Get object footprint in V-frame
        double min_Yv, max_Yv, min_Zv;
        get_belt_slicing_params_v_frame(*this, min_Zv, max_Yv, min_Yv);

        // Generate raft geometry
        BeltPrinter::BeltRaftSettings raft_settings;
        raft_settings.num_layers = m_config.raft_layers;
        raft_settings.layer_height = m_config.raft_contact_distance;
        raft_settings.expansion_mm = m_config.raft_expansion;
        raft_settings.upstream_extension_mm = 20.0; // Config parameter

        auto raft_layers = BeltPrinter::BeltRaft::generate_raft_geometry(
            /* object_footprint */ ...,
            profile,
            raft_settings
        );

        // Prepend raft layers to m_layers
        // ... implementation ...
    }

    // ... continue with existing slicing ...
}
```

## Test Procedure

### Step 1: Slice with Raft

```bash
./orca-slicer --no-gui \
  --load tests/fixtures/belt_raft_config.json \
  --load tests/fixtures/belt_test_tower.stl \
  --export-gcode /tmp/it02_output.gcode
```

### Step 2: Verify Raft Geometry

**Check 1: Raft Layer Count**

```bash
# Should have 3 raft layers before object layers
grep "; raft layer" /tmp/it02_output.gcode | wc -l
# Expected: 3
```

**Check 2: Upstream Extension**

```bash
# Raft should extend in -Yv direction (upstream on belt)
# For CR30 (Yv→Z), check minimum Z coordinate
grep "G1.*Z" /tmp/it02_output.gcode | \
  awk '{for(i=1;i<=NF;i++) if($i~/^Z/) print substr($i,2)}' | \
  sort -n | head -1

# Expected: Negative value (upstream extension)
```

**Check 3: Expansion**

```bash
# Raft perimeter should be object + 5mm expansion
# For 10x10mm object, raft should be ~20x20mm (10 + 2*5)
# Check X range in first raft layer
grep "G1.*X" /tmp/it02_output.gcode | head -50 | \
  awk '{for(i=1;i<=NF;i++) if($i~/^X/) print substr($i,2)}' | \
  awk 'NR==1{min=max=$1} {if($1<min) min=$1; if($1>max) max=$1} END{print max-min}'

# Expected: ~20mm
```

**Check 4: Leading Edge Compliance**

```bash
# All raft coordinates should be within printable strip
# Y >= belt_leading_edge (5mm default)
grep "G1.*Y" /tmp/it02_output.gcode | \
  awk '{for(i=1;i<=NF;i++) if($i~/^Y/) print substr($i,2)}' | \
  sort -n | head -1

# Expected: >= 5.0mm (leading edge constraint)
```

## Success Criteria

✅ **Raft Generated**: 3 raft layers present in G-code
✅ **Upstream Extension**: Raft extends behind object
✅ **Expansion**: Raft boundary = object + expansion
✅ **Clipping**: All coordinates within printable strip
✅ **Adhesion**: First object layer sits on raft surface

## Failure Modes

❌ **No raft**: BeltRaft not called or integration point missing
❌ **Wrong position**: Raft not upstream or incorrectly transformed
❌ **Clipping error**: Raft exceeds printable bounds
❌ **Layer mismatch**: Object layers don't align with raft top

## Implementation Notes

**BeltRaft Module Status**: ✅ Core logic complete (6/6 tests passing)

**Remaining Work**:

- Add integration call in `PrintObject::slice()`
- Extract object footprint from first layer
- Transform raft geometry to Layer\* structures
- Insert into m_layers vector

**Estimated Effort**: ~30 lines of integration code
