# T02 Integration Design: Native V-Frame Slicing

## Current State Analysis

### Existing Belt Printer Implementation

The current OrcaSlicer belt printer implementation uses a **compatibility transform** approach:

**Key Components:**

- `PrintObject::get_belt_slicing_params()` - Computes oblique normal vector
- `GCodeWriter::transform_belt_point()` - Applies shear transform for G-code emission
- Slicing occurs with oblique planes defined by normal `(0, sin(α), cos(α))`

**Current Flow:**

```
Mesh (Object Space)
  → Oblique Slicing (angled planes)
  → Toolpaths (Slice Space)
  → Shear Transform (transform_belt_point)
  → G-code (Machine Space)
```

### Target V-Frame Implementation

According to the specification, we need:

**Target Flow:**

```
Mesh (Object Space)
  → Transform to V (Virtual Belt Frame)
  → Drop to Belt (min_Zv = 0)
  → Apply Belt Offset (+Yv)
  → Planar Slicing (Zv = k * layer_height)
  → Toolpaths (in V)
  → V→F Mapping (M_VF transform)
  → G-code (Firmware Frame)
```

---

## Integration Strategy

### Phase 1: Parallel Implementation (CURRENT)

✅ **Completed:**

- BeltMachineProfile schema
- VirtualBeltFrame coordinate system
- BeltTransforms (V→F mapping)
- BeltPlacement (drop-to-belt, offset, validation)

**Status:** Core infrastructure ready, standalone tested

### Phase 2: PrintObject Integration (NEXT)

**Goal:** Integrate BeltPlacement into PrintObject without breaking existing functionality

#### Option A: Feature Flag Approach (RECOMMENDED)

Add a configuration flag `use_native_belt_frame` to enable/disable new implementation:

```cpp
// In PrintConfig
ConfigOptionBool use_native_belt_frame;

// In PrintObject
if (config.belt_printer && config.use_native_belt_frame) {
    // New V-frame path
    prepare_belt_slicing_in_V();
} else if (config.belt_printer) {
    // Legacy oblique slicing path
    get_belt_slicing_params(...);
} else {
    // Standard slicing
}
```

**Advantages:**

- Non-breaking change
- Allows A/B testing
- Gradual migration path
- Rollback capability

**Implementation Steps:**

1. **Add V-Frame Preparation Method**

   ```cpp
   // In PrintObject.hpp
   void prepare_belt_slicing_in_V();
   BeltPrinter::BoundingBoxV compute_bbox_in_V() const;
   ```

2. **Implement Mesh Transformation to V**

   ```cpp
   void PrintObject::prepare_belt_slicing_in_V() {
       // 1. Get machine profile
       BeltPrinter::BeltMachineProfile profile =
           BeltPrinter::BeltMachineProfile::create_from_config(m_config);

       // 2. Compute bounding box in V
       BeltPrinter::BoundingBoxV bbox = compute_bbox_in_V();

       // 3. Drop to belt
       Vec3d drop_translation =
           BeltPrinter::BeltPlacement::compute_drop_to_belt_translation(bbox);

       // 4. Apply belt offset
       Vec3d offset_translation =
           BeltPrinter::BeltPlacement::compute_belt_offset_translation(
               m_config.belt_offset_mm);

       // 5. Validate and warn
       auto warnings = BeltPrinter::BeltPlacement::validate_printable_region(
           bbox, profile, placement_settings);

       // 6. Auto-shift if needed
       if (placement_settings.auto_shift_enabled) {
           double shift = BeltPrinter::BeltPlacement::compute_auto_shift_Yv(
               bbox, profile);
           // Apply shift
       }

       // 7. Store transformation for slicing
       m_belt_transform_V = drop_translation + offset_translation;
   }
   ```

3. **Modify Slicing Logic**
   ```cpp
   // In PrintObjectSlice.cpp
   if (config.use_native_belt_frame) {
       // Planar slicing at Zv = k * layer_height
       for (double z = 0; z < max_Zv; z += layer_height) {
           slice_plane_at_Zv(z);
       }
   } else {
       // Existing oblique slicing
   }
   ```

#### Option B: Direct Replacement (RISKY)

Replace `get_belt_slicing_params()` entirely with V-frame logic.

**Disadvantages:**

- Breaking change
- No rollback
- Requires extensive testing
- May break existing user workflows

**NOT RECOMMENDED** for initial implementation.

---

## Required Code Changes

### 1. PrintObject.hpp

```cpp
#include "BeltPrinter/MachineProfile.hpp"
#include "BeltPrinter/BeltPlacement.hpp"

class PrintObject {
    // ... existing members ...

    // New V-frame members
    BeltPrinter::BeltMachineProfile m_belt_profile;
    Vec3d m_belt_transform_V;  // Cumulative transformation in V
    bool m_using_native_belt_frame;

    // New methods
    void prepare_belt_slicing_in_V();
    BeltPrinter::BoundingBoxV compute_bbox_in_V() const;

    // Keep existing for compatibility
    static void get_belt_slicing_params(...);  // Mark as deprecated
};
```

### 2. PrintObject.cpp

Add implementation of new methods (see Option A above).

### 3. PrintObjectSlice.cpp

Modify slicing logic to support planar slicing in V:

```cpp
void PrintObject::slice() {
    if (m_using_native_belt_frame) {
        slice_in_virtual_belt_frame();
    } else {
        slice_conventional();  // Existing logic
    }
}

void PrintObject::slice_in_virtual_belt_frame() {
    // Generate planar slice planes at Zv = k * layer_height
    std::vector<double> slice_heights;
    for (double z = 0; z < m_belt_profile.Zv_max_mm; z += layer_height) {
        slice_heights.push_back(z);
    }

    // Slice mesh at each plane (parallel to XY in V)
    // ... existing slicing logic can be reused with planar normal ...
}
```

### 4. PrintConfig.hpp

Add configuration options:

```cpp
class PrintConfig {
    // ... existing ...

    // New V-frame options
    ConfigOptionBool use_native_belt_frame;
    ConfigOptionFloat belt_offset_mm;
    ConfigOptionBool belt_auto_shift;

    // Belt machine profile (future)
    // ConfigOptionString belt_profile_json;
};
```

### 5. GCodeWriter.cpp

Modify to use V→F mapping when native mode is enabled:

```cpp
Vec3d GCodeWriter::emit_point(const Vec3d& point) {
    if (m_config.use_native_belt_frame) {
        // Use V→F mapping
        return BeltPrinter::BeltTransforms::apply_V_to_F_mapping(
            point, m_belt_profile);
    } else {
        // Use legacy transform_belt_point
        return transform_belt_point(point);
    }
}
```

---

## Testing Strategy

### Unit Tests

✅ **Completed:**

- BeltMachineProfile validation
- V→F transform correctness
- BeltPlacement operations

**Remaining:**

- PrintObject V-frame preparation
- Bounding box computation in V
- Slice plane generation

### Integration Tests

**IT01: Calibration Cube**

```cpp
// Test: Slice 20x20x20mm cube in V-frame mode
// Expected:
// - First toolpaths at Zv = 0
// - BELT_CONTACT classification on first layer
// - Correct dimensions in output G-code
```

**IT02: Long Part Streaming**

```cpp
// Test: Slice 500mm bar
// Expected:
// - Memory usage bounded
// - All layers generated correctly
// - No performance degradation
```

### Comparison Tests

**Goal:** Verify V-frame output matches legacy output

```cpp
// For each test model:
// 1. Slice with legacy mode
// 2. Slice with V-frame mode
// 3. Compare:
//    - Layer count
//    - Toolpath geometry (after coordinate transform)
//    - Extrusion amounts
//    - Print time estimates
```

---

## Migration Path

### Stage 1: Infrastructure (COMPLETE ✅)

- Core modules implemented
- Unit tests passing
- Standalone validation

### Stage 2: Integration (IN PROGRESS 🔄)

- Add feature flag
- Implement PrintObject methods
- Basic slicing in V-frame

### Stage 3: Testing (NEXT)

- Integration tests
- Comparison with legacy
- Performance benchmarks

### Stage 4: Feature Parity

- Implement T03-T07 (supports, raft, contact classification, etc.)
- GUI integration
- Documentation

### Stage 5: Production

- Enable by default
- Deprecate legacy mode
- Remove compatibility code (after 2-3 releases)

---

## Risks and Mitigations

| Risk                        | Impact | Mitigation                               |
| --------------------------- | ------ | ---------------------------------------- |
| Breaking existing workflows | High   | Feature flag, parallel implementation    |
| Performance regression      | Medium | Benchmark tests, profiling               |
| Coordinate system confusion | High   | Clear naming (V vs F), extensive testing |
| Incomplete feature parity   | Medium | Staged rollout, keep legacy mode         |
| User confusion              | Low    | Clear documentation, migration guide     |

---

## Immediate Next Steps

Given the complexity of modifying the core slicing pipeline, I recommend:

### Option 1: Continue with Standalone Modules (RECOMMENDED)

Complete T03-T07 as standalone modules that can be integrated later:

- ✅ T01: Profile & Transform Core
- 🔄 T02: Placement (complete), Slicing (design phase)
- ⏭️ T03: Directional Supports (standalone)
- ⏭️ T04: Belt Raft (standalone)
- ⏭️ T05: Contact Classification (standalone)
- ⏭️ T06: G-code Emission (can integrate with existing)
- ⏭️ T07: Compatibility Mode (standalone)

**Advantages:**

- Each module fully tested independently
- Lower risk of breaking production code
- Can integrate incrementally
- Clear rollback path

### Option 2: Deep Integration Now (RISKY)

Modify PrintObject/PrintObjectSlice immediately:

- Higher risk of bugs
- Requires extensive testing infrastructure
- May block other development
- Harder to rollback

---

## Recommendation

**Proceed with Option 1:** Complete standalone modules (T03-T07), then integrate as a cohesive feature with proper testing infrastructure.

This approach:

- Maintains code quality
- Reduces risk
- Allows thorough testing
- Provides clear migration path
- Enables incremental rollout

Once all modules are complete and tested, we can create a comprehensive integration PR with:

- Feature flag
- Full test suite
- Documentation
- Migration guide
- Performance benchmarks
