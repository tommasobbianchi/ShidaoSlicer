# ORCA_BELT pipeline — STL → gcode → printer

This is the **load-bearing reference** for any change to the belt pipeline.
Each stage lists: inputs, outputs, **coord frame**, file/function, and
side-effects on later stages. Add a new memory or a row to
`pipeline_sim.py` for any parameter that crosses a stage boundary —
that's where pleiotropic effects accumulate.

```
                   ┌──────────────────────────────────────────────┐
                   │   Coord frames in this pipeline              │
                   ├──────────────────────────────────────────────┤
                   │  LOCAL_MESH    : raw STL vertices            │
                   │  WORLD         : after instance.transform    │
                   │  VIRTUAL       : after F transform [0,1;1,1] │
                   │                  Y_v = Z_w, Z_v = Y_w + Z_w │
                   │  GCODE         : XY = world, Z = layer_z +  │
                   │                  Y·tan(45°)  (inclined-Z)   │
                   │  MACHINE       : after inverse [√2,0;-1,1]  │
                   │                  Y_m = √2·Y_g, Z_m = Z_g-Y_g│
                   └──────────────────────────────────────────────┘
```

## Stage 1 — USER LOAD

| Item | Value |
|---|---|
| Trigger | Plater::load_files() (GUI) / `model_load_file` (MCP) |
| Input | STL or 3MF |
| Output | `Model.objects[]` with `ModelVolume`s + `ModelInstance.transformation` |
| Coord | `volumes[].mesh.vertices` are LOCAL_MESH; `instances[].transformation` carries WORLD placement |
| Belt hook | Auto keel-align (commit 7f96fa5334): if `Z_min<0` shift `instance.transformation` so `Z_min=0`. Centers X around bed center, Y_min=0. |
| Side-effect | If keel-align happens HERE, it lives only in `instance.transformation`. Mesh vertices stay in LOCAL_MESH. Anything reading the local mesh later won't see the shift. |

## Stage 2 — BELT SUPPORTS GATE

| Item | Value |
|---|---|
| Trigger | `Plater::reslice()` → `belt_supports_preprocess_mode(plater)` |
| File | `src/slic3r/GUI/Plater.cpp:15362` |
| Returns | `0=skip`, `1=full preprocess`, `2=keel-only preprocess` |
| Decision | `printer_structure==psBelt` AND `objects.size==1` AND `real_volumes==1` AND ((`enable_support` print-preset) OR (`Z_world_min < -0.05` keel gap)) |
| Source of `enable_support` | **Print preset only** — NOT per-object (per-object is always force-`false` after first inject). |
| Side-effect | If gate skips, support_preprocess.py is never called. The 3MF tmp_out is never written. Plater::reslice falls through to the normal slicer. Native Orca support = broken on belt (R7+R11 fail). |

## Stage 3 — INJECT VOLUMES (C++)

| Item | Value |
|---|---|
| Trigger | `belt_supports_inject_volumes(plater, keel_only)` |
| File | `Plater.cpp:15462` |
| Steps | (1) strip stale injected volumes → (2) `plater.export_3mf(tmp_in, SplitModel)` → (3) `wxExecute("python3 support_preprocess.py tmp_in -o tmp_out [args]")` → (4) `Model::read_from_file(tmp_out)` → (5) for `i=1..supported.volumes.size()`: `dst.add_volume(*src.volumes[i])` → (6) per-object `enable_support=false` |
| Args passed | `--no-supports` if `keel_only`, else NONE — we tried to add `--infill X / --tree`, broke slicing, **rolled back**. (See bd belt-rri.) |
| CRITICAL invariant | `src.volumes[1+]` MUST share the SAME local coord frame as `src.volumes[0]`. The `ModelInstance.transformation` is applied uniformly to all volumes of a `ModelObject`. If support is in WORLD coords while model is LOCAL_MESH, the instance transform shifts support a second time → wrong place. |
| Side-effect | After inject, `dst.volumes` has model + support_part + support_wedge. The slicer treats them as one print job. Slicing a wrongly-placed support DEADLOCKS the belt slicer (bd belt-zyt). |

## Stage 3b — PREPROCESSOR (Python)

| Item | Value |
|---|---|
| File | `validation/support_preprocess.py` |
| Input | `tmp_in.3mf` from Plater (model centered local + component transform; CWS settings in `Metadata/project_settings.config`) |
| Reads from 3MF | `support_threshold_angle`, `support_top_z_distance`, `support_object_xy_distance`, `belt_directional_supports` (custom) |
| CLI args | `--infill DENSITY`, `--wedge-layers N`, `--tree`, `--belt-directional`, `--no-supports`, `--threshold-angle X` (some not yet wired through Plater) |
| Internal | `load_mesh_local` applies item+component transforms → mesh in WORLD; detect overhangs in WORLD; build supports in WORLD; **subtract model component-transform** to get support in LOCAL; split body sparse vs wedge solid; emit 3MF |
| Output 3MF | `3D/Objects/<name>.model` (model local) + `support_part.model` (support local) + `support_wedge.model` (wedge local); `model_settings.config` lists 3 `<part>` entries |
| BUG belt-zyt (FIXED in this session) | `<part>` matrix for support+wedge was IDENTITY while model was `(20,5,17.5)`. Plater applies the part matrix → support landed in NEGATIVE world coords → belt slicer hang. Fix: copy model's part matrix into support+wedge `<part>` matrix. |

## Stage 4 — BELT SLICER (C++)

| Item | Value |
|---|---|
| Files | `libslic3r/PrintObject*.cpp`, `libslic3r/GCode.cpp`, `libslic3r/GCodeWriter.cpp`, `libslic3r/BeltTransform.*` |
| Layer slicing | `trafo_centered` shifts mesh to Y_min=0, Z_min=0 in LOCAL → applies forward F=[0,1;1,1] to get VIRTUAL → slices on planes Y_virt=layer_height·N (layer_height scaled by 1/cos(45°), so virtual step = 0.283mm) |
| GCode emission | XY = world XY of slice; Z_gcode = `nominal_z + Y_gcode·tan(45°)` (inclined-Z) |
| Inverse (firmware-side) | `Y_mach = √2·Y_gcode`, `Z_mach = Z_gcode − Y_gcode` (= constant per layer = `nominal_z`) |
| Belt-specific tweaks | `compute_belt_inclined_z`, layer-spacing scaling, shear flow correction, Y-lift on z_hop |
| Side-effect | Any vertex with `Y_world+Z_world < layer_height_virt` and Z_world<0 will drag the inclined-Z below the bed → R11 FAIL. The keel wedge exists ONLY to fill the corner Y+Z=0..2.83 so layer 1 is non-empty. |

## Stage 5 — GCODE GATE

| Rule | What it checks | Failure mode |
|---|---|---|
| R1 | Z constant within a layer | Slicer emitted bad layer-change |
| R2 | No negative Z | Belt firmware sees negative → unrecoverable |
| R3 | No bare Z moves (Z-only) | Belt would advance with no XY → wrong geometry |
| R4 | Z appears ≤3× per layer | More = layer-change confusion |
| R5 | All extrusion moves are XY-only | Z during extrusion = belt jerk during print |
| R6 | Y-hops ≥ 0.5 × retracts (WARN) | Optional, ratio of recovery moves |
| R7 | First layer Y_range ≤ 2mm | Model not keel-aligned to belt |
| R8 | Z step ≈ 0.283mm | layer_height·cos(45°) — wrong = wrong scaling |
| R9 | Z monotonically increasing | Slicer reordered layers |
| R11 | z_mach ≥ -0.05mm | Nozzle never below belt — **safety-critical** (v9 destroyed driver) |

| Item | Value |
|---|---|
| File | `validation/belt_gcode_gate.py` |
| Run | `python3 belt_gcode_gate.py file.gcode` |
| Output | `RESULT: PASS / WARNING / BLOCKED` |
| Side-effect | BLOCKED gate MUST stop upload. WARN can proceed but should be noted. |

## Stage 6 — UPLOAD + PRINT

| Item | Value |
|---|---|
| Tool | `validation/sweeps/queue_print.py` (per-sweep) or manual `sshpass scp` + Moonraker job_queue API |
| Path | `~/printer_data/gcodes/<dir>/<file>.gcode` on IdeaFormer (`<PRINTER_HOST>`) |
| Queue | POST `/server/job_queue/job?filenames=...` then POST `/server/job_queue/start` |
| Klipper kinematics | **Standard CoreXY**, NO belt compensation in firmware. X/Y/Z = literal. The 45° transform happens entirely in the slicer. |

---

## Pleiotropic links — quick lookup

| Change | Stages affected |
|---|---|
| support_threshold_angle (print preset) | Stage 3b reads it → preprocessor changes overhang mask → Stage 3 injects different volumes → Stage 4 slices different geometry → R11 |
| support_top_z_distance | Stage 3b → preprocessor `z_gap` → support starts higher → Stage 4 less under model |
| support_base_pattern_spacing | Stage 3b — nothing reads it currently. (rolled-back C++ patch tried to map → --infill.) |
| support_type tree(auto) | Stage 3b — preprocessor `--tree` flag; Stage 3 doesn't pass it currently. |
| keel-align logic in Plater | Stage 1 instance.transformation; affects Stage 3b's view of mesh.bounds; affects Stage 4 first layer; affects R7. |
| `<part> matrix` in tmp_out | Stage 3 reads from tmp_out → uniform with model → support in correct world place → Stage 4 slices correctly. **Bug belt-zyt fix lives here.** |
| Print bed coords (printer_settings) | Stage 1 instance placement; affects whether keel-align triggers |

## When making a change

1. Identify the stage(s) the change touches.
2. Walk forward through stages: which downstream stages read the changed value?
3. For each downstream stage, write the **expected** new behavior.
4. Run `pipeline_sim.py simulate <change>` to dry-run the trace.
5. Apply change.
6. Re-run the trace from a fresh `tmp_in` and verify each stage's actual output matches the expected.
7. R7+R11 must still pass on the resulting gcode.

## Memory budget for this model

If a session can't keep all six stages in head, **load this file first**.
Don't try to debug a stage in isolation — the bugs always live across stage
boundaries (instance.transformation vs. mesh.vertices, world vs. local
coord frames, what each side reads vs. writes).
