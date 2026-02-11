# Behemoth Remote Build Saga & Validation

## Objective

Offload OrcaSlicer compilation to "Behemoth" (Ubuntu 24.04, 16-core) to overcome local resource limits and fix dependency issues.

## Build Process (Iterative Fixes)

The build process involved solving a chain of strict linking errors typical of Ubuntu 24.04 (GCC 13 + Newer CMake).

### 1. Ambiguous Overload (v32)

- **Error**: `set_values({...})` ambiguous in `PhysicalPrinterDialog.cpp`.
- **Fix**: Explicit cast `std::vector<std::string>{...}`.

### 2. OpenCV "World" vs Modules (v33-v42)

- **Issue**: `opencv_world` does not exist on standard Linux installs.
- **Error**: `undefined reference` to `cv::threshold`, `cv::imread`.
- **Fix**:
  - Switched to `${OpenCV_LIBS}` in `libslic3r`.
  - Updated `find_package` to explicitly request `imgproc`, `imgcodecs` (not just `core`).
  - Added `${OpenCV_LIBS}` to `libslic3r_gui` which also uses OpenCV directly.

### 3. WebKitGTK (v34)

- **Error**: `undefined reference` to `webkit_...` symbols.
- **Fix**: Explicitly `pkg_check_modules(WEBKIT webkit2gtk-4.1)` and linked it in `src/slic3r/CMakeLists.txt`.

### 4. OpenVDB & The Dependency Tree (v35-v40)

- **Issue**: OpenVDB static linking failed due to missing transitive dependencies.
- **Errors**: Undefined references to `LeafBuffer`, `MappedFile`, `Blosc`, `TBB`.
- **Fixes**:
  - **Imath**: Explicitly linked `Imath::Imath`.
  - **Boost::iostreams**: Added for OpenVDB I/O.
  - **TBB**: Explicitly linked `TBB::tbb`.
  - **Blosc**: Manually found and linked `libblosc` (`find_library` + link).
  - **Target Definition**: Patched `FindOpenVDB.cmake` to manually define `OpenVDB::openvdb` target in the hardcoded block for Behemoth.

## Final Result (v42)

- **Build Success**: `orca-slicer` executable generated.
- **Time**: ~10-15 mins for full incremental build on Behemoth.

## Validation (Belt Logic)

Run `belt_validation_loop.sh` on Behemoth.

### Results

- **Z_min >= 0** (Negative Z check): ✅ **PASS** (0.20mm). _Major fix confirmed._
- **Z Start**: > -1000mm. ✅ **PASS**. Error -102 (Unprintable area) likely resolved.
- **Z Range**: ❌ **FAIL**.
  - Input: 20mm Cube.
  - Output: 39.60mm (Run 2) / 37.40mm (Run 1).
  - Scale Factor: ~1.8 - 2.0x.
- **Z Monotonic**:
  - Run 1 (Diamond orientation): ✅ PASS.
  - Run 2 (Flat): ❌ FAIL.

## Next Steps

The build infrastructure is solid. The focus now shifts purely to **Translation Logic Debugging**:

1.  Investigate the ~2x Z-scaling factor.
2.  Fix Z monotonicity for flat objects.
