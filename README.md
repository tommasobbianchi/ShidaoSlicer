<div align="center">

<picture>
  <img alt="ShidaoSlicer icon" src="resources/images/ShidaoSlicer_256px.png" width="20%" height="20%">
</picture>

# ShidaoSlicer (试刀)

**An unofficial belt-printer fork of [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer)**

*试刀 — "trying the blade"*

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Upstream: OrcaSlicer](https://img.shields.io/badge/upstream-OrcaSlicer-181717?logo=github&logoColor=white)](https://github.com/SoftFever/OrcaSlicer)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#hardware-validated)

</div>

---

## ⚠️ Disclaimer

**ShidaoSlicer is not affiliated with, endorsed by, or sponsored by OrcaSlicer / SoftFever, BambuStudio / Bambu Lab, or PrusaSlicer / Prusa Research.** It is an independent community fork released under the same license as upstream (AGPL-3.0-or-later).

The name **Shidao (试刀)** is Chinese for *"testing the blade"* — the classical practice of a swordsman proving a freshly-forged **dao** (刀, the single-edged Chinese sabre) before trusting it in combat. The logo depicts that scene: a Chinese warrior bench-testing his dao. The workflow mindset here is exactly that — every change to the belt pipeline must pass a slice + safety-gate test before it touches a real machine. The artwork is original to this fork; it is **not** a derivative of the OrcaSlicer orca logo, and the weapon depicted is a **dao**, not a Japanese katana.

This is **alpha-quality software** targeting a niche of printer (45°-inclined-belt CR-30 / IdeaFormer-IR3 family). Do not use it for production prints without validating each gcode through `validation/belt_gcode_gate.py` first. Driver-killer first-layer faults are an everyday risk on belt printers, and a small math error in the slicer becomes a 200 € TMC2240 in the bin.

## What's a belt printer?

A belt 3D printer prints onto a **continuous polymer belt** that rolls under the toolhead. The bed is tilted at a fixed angle (almost always 45°) and the third axis is effectively infinite: when the print is taller than the gantry travel, it simply rolls forward.

This breaks every assumption in a normal slicer. There is no bed Z bound, no "first layer is layer 0 at Z=0.2 mm", no "Z column above a face supports it". Instead:

- A model-space point `(X, Y, Z)` is printed at gcode coordinates `(X, √2·Y, Y+Z)`.
- Layers are **oblique 45°-inclined planes**, not horizontal slabs.
- The print "scrolls past" the toolhead in `+Y_machine` direction.

ShidaoSlicer is a fork of OrcaSlicer that bakes this transform into the slicer pipeline, validates the output, and adds the belt-specific UX (preview at 45°, no false "out-of-bed" warnings, a per-belt support generator).

## Hardware validated

| Printer | Status | Notes |
|---|---|---|
| **IdeaFormer IR3 V2** | ✅ Routinely used | Klipper, belt α=45°, X=250 mm, std CoreXY kinematics, NO firmware-side belt transform |
| Creality CR-30 | ❓ Untested but math model is identical | Reports welcome via issues |
| Other 45° belt printers | ❓ Untested | Reports welcome via issues |

Hardware-validated filaments / fixtures: PETG generic 235 °C, PLA eSUN 210 °C; print smoke set `box_10`, `box_20`, `arc_bridge`, `inverted_L`, `Supports_Test_small`, multi-rotation supports.

## License

**AGPL-3.0-or-later**, inherited from upstream OrcaSlicer. All belt-specific modifications in this fork are released under the same license. See [LICENSE](LICENSE).

## What's different from upstream OrcaSlicer

### 1. Belt mathematical model (C++ core)

Files: `src/libslic3r/GCode.cpp`, `src/libslic3r/GCodeWriter.cpp`, `src/libslic3r/PrintObject.cpp`, `src/libslic3r/PrintObjectSlice.cpp`, `src/libslic3r/PrintApply.cpp`, `src/libslic3r/BeltTransform.{h,cpp}`.

- **Forward transform** (model → virtual): `[Y_virt = Z_model;  Z_virt = Y_model + Z_model]` — i.e. `[[0,1],[1,1]]`.
- **Inclined-Z**: `Z_post = Z_virt + Y_virt · tan(α)` with α = 45°.
- **Inverse transform** (virtual → machine): `[[√2,0],[-1,1]]`, so `Y_mach = √2·Z_model` and `Z_mach = Y_model + Z_model`.
- **Layer height scaled by `1/cos(α)`**, so a 0.20 mm belt-normal step becomes 0.283 mm in virtual Z. This is what `layer_height` in the preset actually represents on belt.
- **Y-lift in GCodeWriter**: `z_hop` is reinterpreted as a gantry lift; the emitted gcode adds `hop/√2` to both Y and Z (the only safe way to lift the nozzle off a moving belt).
- **Keel-first slicing** (`trafo_centered()`): shifts `Y_min = 0` and `Z_min = 0` before the forward transform, so the first slice intersects the model corner that actually touches the belt first ("the keel").

The model is invariant and hardware-validated. **Do not touch the transform core** — every consumer (gcode viewer, gate, analyzers) is expected to adapt to the gcode it produces. See `docs/architecture/BELT_IMPLEMENTATION_DESIGN_DOC.md` for the formal derivation.

### 2. Belt slicer fixes

| Fix | Where | What it solves |
|---|---|---|
| **45° cut bug** | `PrintApply.cpp` (a9c1c6b5b3) | Multi-volume objects silently lost top layers because the slicing bbox was tested in world coords while the layer index lives in virtual coords. Fixed by passing `trafo_centered()`. |
| **Top-shell at 45°** | `PrintObject*` | Upstream samples `top_shell_layers` along Z; on belt this walks along Y instead of into the model. Raises the count to `ceil(model_Y / z_step)` for belt printers. |
| **Multi-instance keel-guard** | `Plater.cpp` | Original code reset `Y_min → 0` unconditionally on every load, collapsing multi-instance plates on re-open. Now only shifts when `Y_min < 0` (mirrors the pre-existing Z guard). |
| **CLI null guards** | `PartPlate.cpp`, various | Headless multi-object slicing no longer SIGSEGVs on sparse 3MFs (`config.option<T>()` null-checked, `m_plater` null-guarded in `PartPlate::check_outside`). |

### 3. Belt safety gate

[`validation/belt_gcode_gate.py`](validation/belt_gcode_gate.py) runs **11 R-rules** over a sliced gcode before it ever reaches the printer. The driver-killers:

- **R7** — first-layer Y ≤ 2 mm (a gcode that starts with Y > 2 commands the belt to slam forward at full speed at print start).
- **R11** — `Z_machine ≥ −0.05 mm` (no command may dive the toolhead through the belt).

There is a **printer-side mirror** of the gate at `~/obp/belt_gcode_gate.py` on the Klipper host that re-checks every uploaded gcode as a second safety net. R7+R11 have caught real-world regressions multiple times; one of them killed a TMC2240 (200 €) before the gate existed.

### 4. Support pipeline

The native OrcaSlicer support generator is unusable on belt — it runs in virtual space and produces support columns whose toolpaths fall *under* the belt surface (R7+R11 fail regardless of parameters).

[`validation/support_preprocess.py`](validation/support_preprocess.py) is a Python pre-slice step that does the belt-correct thing:

1. Detect overhangs in **model space** with gravity `[0, 0, -1]`.
2. Project Cartesian support columns from each overhang down to the belt surface (Y+Z=0 diagonal).
3. Build a 2- or 3-volume 3MF (model + support body + optional **keel wedge** that anchors the supports to the belt from layer 1).
4. Stamp `enable_support = 0` in the 3MF's `Metadata/project_settings.config` so OrcaSlicer's native support generator does **not** also run.

Tunables: `--infill <pct>`, `--threshold-angle`, `--xy-gap`, `--top-z-distance`, `--bottom-z-distance`, `--wedge-layers N`, `--tree`, `--belt-directional` (planned).

Workflow:
```bash
python3 validation/support_preprocess.py model.3mf -o model_supported.3mf
orca-slicer --slice 0 --load-settings belt-preset.json --export-3mf out.3mf model_supported.3mf
python3 validation/belt_gcode_gate.py out.gcode
```

### 5. Belt-aware GUI

`src/slic3r/GUI/Plater.cpp`, `src/slic3r/GUI/MainFrame.cpp`, `src/slic3r/GUI/PrinterWebView.cpp` (and the new `orcabelt_fluidd_host`):

- **Print button** stays enabled after belt slicing. Upstream gates on a `printable_height` rectangle check that always fails on belt.
- **Preview slider** survives belt-specific re-slices: 3 guards in `Plater.cpp` against spurious `APPLY_STATUS_INVALIDATED`.
- **Preview rendering** at 45° (not collapsed to horizontal layers — Z quantization removed in `GCodeViewer::load_toolpaths`).
- **Toolpath / mesh alignment** uses a corrected `belt_to_model` inverse (`Z_model = Y_gcode/√2`, `Y_model = Z_gcode − Z_model`).
- **Ctrl+0 robust on belt** (orbits the loaded volumes, not the empty 2 m-wide belt center).
- **ImGui assert soften** so the wx ↔ ImGui modifier-key desync doesn't abort Debug builds on every slice.
- **SIGSEGV signal handler** writes `/tmp/orcabelt_crash_<pid>.log` with a demangled backtrace, GTK/GLib log capture, and recent ImGui state — for offline triage of UI crashes.

### 6. Embedded Fluidd / Mainsail in the Device tab

Out-of-process `orcabelt_fluidd_host` subprocess (GTK + webkit2gtk-4.1) wrapped by a wxPanel overlay tracker. This bypasses the upstream `libjavascriptcoregtk-4.1` SIGSEGV that crashes Orca whenever Fluidd loads in-process on Ubuntu noble (see upstream issues SoftFever/OrcaSlicer#10756 #10804 #12919 #6043 — all open with no PR).

If the subprocess dies within 5 s of spawn, the panel falls back to an **"Open in browser"** button (`xdg-open`). Future-proof: when WebKit on Ubuntu ≥ 2.52 ships, the subprocess will survive and the overlay just shows the embedded Fluidd inline — zero code changes needed.

### 7. Calibration helpers

- [`validation/calib_temp_belt_v5.py`](validation/calib_temp_belt_v5.py) — belt-adapted **temperature tower**. 45° tilt + leading wedge for first-layer adhesion + per-zone M104 events embedded directly in `Metadata/custom_gcode_per_layer.xml`. Single merged-mesh object (workaround for the multi-instance pipeline collapse — see Known Issues).
- [`validation/orca_profile_flatten.py`](validation/orca_profile_flatten.py) — flattens the `inherits` chain in any preset JSON so the CLI's `--load-settings` actually sees parent fields (`gcode_flavor`, `machine_start_gcode`, etc.). Without this, CLI-sliced gcodes emit Marlin defaults and the first layer fires the extruder cold — driver-risk.
- [`validation/belt_smoke.sh`](validation/belt_smoke.sh) — pipeline regression harness (12 PASS / 2 WARN / 0 FAIL baseline on `inverted_L` + `Test_Supports` fixtures, ~3 s wall-clock).
- [`validation/belt_gui_validate.py`](validation/belt_gui_validate.py) — thin wrapper that flattens the preset, slices via the Release binary, and runs the gate.

### 8. Optional MCP server

Compiled in when `cmake -DENABLE_MCP_SERVER=ON`. Adds 25 JSON-RPC tools on `127.0.0.1:13619/mcp` for headless control (`model_load_file`, `model_add_text`, `slice_and_stats`, `screenshot`, `object_transform`, …). Used by the calibration scripts to drive an `xvfb-run`'d Orca for batch slicing / text-mesh generation, and by external agents (Claude-Code, etc.) for round-trip GUI automation.

## Building

Linux:

```bash
./build_linux.sh -u     # first time: install system deps
./build_linux.sh -dsi   # build deps + slicer + AppImage
```

macOS / Windows: same as upstream OrcaSlicer (`build_release_macos.sh`, `build_release_vs2022.bat`). The belt-specific changes are header-compatible — no extra dependencies beyond what OrcaSlicer already requires.

Output binary:
- `build/src/Release/orca-slicer` — Release (~135 MB), fast, **use this for normal slicing**.
- `build/src/Debug/orca-slicer` — Debug (~2 GB), use for ImGui asserts + verbose logs when chasing crashes.

The binary is still called `orca-slicer` for compatibility with downstream tooling (Moonraker thumbnail extractor, IdeaFormer Klipper macros). The window title and `About` dialog identify themselves as ShidaoSlicer.

## Roadmap

- Fix the deeper multi-instance belt-slicer collapse (`PrintApply::print_objects_from_model_object` zeroes Y_world per instance, so N copies along the belt render into the same Z_gcode range; current workaround is a single merged-mesh object).
- **Belt-directional support filter** — skip support columns already in the print-forward shadow of an earlier column (saves a lot of filament on staircase-like geometry).
- Tree / organic supports adapted for belt — currently axis-aligned box columns only.
- Y-speed ramp, outer-wall-first, 45° gap-fill, fan ramp.
- Full **A3 + C1 calibration suite** (gap tuning + interface-layer optimization + PLA temp / pressure-advance / retraction on belt-adapted geometry).
- CLI `unprintable_area` bypass for merged multi-zone meshes (the GUI path already bypasses `BuildVolume::all_paths_inside`; the CLI path is still pending).
- Native Windows / macOS binaries (currently Linux-only AppImage).
- Wave-overhangs integration (research branch, see acknowledgements).

## Known issues

- **Multi-instance plate collapse on belt**: `PrintApply::print_objects_from_model_object` zeroes `trafo.data()[13]` (Y_world) per instance, so N copies of a model laid along Y all share the same virtual Z range. **Workaround**: bake into a single merged-mesh object.
- **WebKit2GTK 4.1 2.50.4 crash**: Ubuntu noble's bundled `libjavascriptcoregtk` SIGSEGVs ~2 s after Fluidd finishes loading. The subprocess host bypasses this; the inline embed will return when WebKit ≥ 2.52 ships (likely Ubuntu 26.04 LTS).
- **CLI `unprintable area` error code 8** on merged multi-zone meshes — `BuildVolume::all_paths_inside` enforces `printable_height` which belt Z routinely exceeds. The GUI path already bypasses this; the CLI bypass is pending.

## Credits / attribution

Massive credit goes upstream:

- **OrcaSlicer maintainers** (SoftFever and the OrcaSlicer community) — every line of the Cartesian slicer core, the wxWidgets / ImGui shell, the calibration framework, and the 3MF format support.
- **BambuStudio / Bambu Lab** — original upstream that OrcaSlicer forked from.
- **PrusaSlicer / Prusa Research** — the slicing kernel both inherit from.
- **WaveOverhangs sandbox** (dennisklappe/OrcaSlicer-WaveOverhangs) — research that will inform the planned wave-overhangs integration.

Belt-specific work, math model, validation tooling, calibration helpers, MCP integration, and the icon (original artwork) are by this fork's maintainer.

## Contributing / bug reports

Open an issue or PR against the GitHub repo. Reports of belt printers other than IdeaFormer IR3 V2 are particularly welcome — the math model should generalize to any 45°-inclined-belt machine, but it has only been hardware-validated on one.

For changes touching the C++ belt transform core (`GCode.cpp`, `GCodeWriter.cpp`, `PrintObject*.cpp`, `BeltTransform.*`), please add an entry to `validation/` reproducing the change with a synthetic STL + expected gcode + R-gate decision. Without that, PRs will not be merged — every transform change has a way of breaking something downstream that only shows up on real hardware.
