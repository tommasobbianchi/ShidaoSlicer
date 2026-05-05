#!/usr/bin/env python3
"""ORCA_BELT pipeline simulator — pre-flight check for a change.

Use this BEFORE editing the pipeline. Encodes the data flow STL→gcode and
each stage's reads/writes, so we can ask "if I change X, what gets
re-derived?" and get a list — instead of guessing and then having a
parameter sweep that turns out to be a no-op (cf. the half-day spent
discovering that the C++ patch never actually changed any gcode).

Mental model: the pipeline is a DAG of stages. Each stage has:
  - inputs  : list of (param_name, source_stage_or_USER)
  - outputs : list of param_names produced/derived
  - reads   : list of params read but not produced (must come from upstream)

A "what-if" simulation walks downstream from a changed param: any stage
that reads it (transitively, through its outputs) is potentially affected.

Usage:
  python3 docs/architecture/pipeline_sim.py describe
      → human-readable stage list
  python3 docs/architecture/pipeline_sim.py whatif support_threshold_angle
      → list of stages that re-derive when this changes
  python3 docs/architecture/pipeline_sim.py invariants
      → cross-stage invariants and how to check them
  python3 docs/architecture/pipeline_sim.py trace path:gcode_z_mach
      → backward trace: which inputs determine z_mach in the final gcode
"""
from __future__ import annotations
import sys, json, argparse
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


@dataclass
class Stage:
    name: str
    file_ref: str           # path:line range or filename
    reads: List[str]        # parameters this stage reads
    writes: List[str]       # parameters this stage produces / mutates
    coord_frame_in: str     # input mesh/coord interpretation
    coord_frame_out: str    # output mesh/coord interpretation
    notes: List[str] = field(default_factory=list)


# Pipeline stages, in execution order. The "reads" are the only handles
# we have for whatif-tracing. Add a parameter here when introducing a new
# config key — otherwise simulator can't see it.
STAGES: List[Stage] = [
    Stage(
        name="1.user_load",
        file_ref="src/slic3r/GUI/Plater.cpp::load_files / MCP model_load_file",
        reads=["stl_or_3mf_path", "printer_structure", "best_object_pos"],
        writes=["model_objects[]", "instance.transformation",
                "volume.mesh.vertices(LOCAL)"],
        coord_frame_in="STL local",
        coord_frame_out="LOCAL_MESH + WORLD via instance.transformation",
        notes=[
            "Auto keel-align (commit 7f96fa5334) shifts instance.transformation",
            "if Z_world_min < 0. Mesh vertices stay in LOCAL_MESH.",
        ],
    ),
    Stage(
        name="2.belt_gate",
        file_ref="src/slic3r/GUI/Plater.cpp:15362 belt_supports_preprocess_mode",
        reads=["printer_structure", "objects.size", "real_volumes_count",
               "enable_support(print_preset)", "Z_world_min"],
        writes=["belt_mode(0|1|2)"],
        coord_frame_in="WORLD bbox query",
        coord_frame_out="(integer mode)",
        notes=[
            "Multi-object plate skips → support nativo broken on belt",
            "enable_support read FROM PRINT PRESET ONLY (per-object always",
            "force-false after first inject — see comment at 15351-15356).",
        ],
    ),
    Stage(
        name="3.inject_volumes",
        file_ref="src/slic3r/GUI/Plater.cpp:15462 belt_supports_inject_volumes",
        reads=["belt_mode", "model_objects[0]",
               "support_base_pattern_spacing(print_preset)",
               "support_type(print_preset)",
               "belt_support_wedge_layers(print_preset)"],
        writes=["tmp_in.3mf", "tmp_out.3mf",
                "cli_args (preprocessor invocation)",
                "model_objects[0].volumes[1+] (added)",
                "per_object.enable_support=false"],
        coord_frame_in="LOCAL_MESH for the model object",
        coord_frame_out="LOCAL_MESH for ALL volumes (model + support + wedge)",
        notes=[
            "INVARIANT: src.volumes[1+] mesh MUST share the same local origin",
            "as src.volumes[0]. Else instance.transformation shifts support",
            "wrongly → R11 fails or slicer hangs.",
            "Args mapping:",
            "  support_base_pattern_spacing  → --infill (~30/spacing)",
            "  support_type tree*            → --tree",
            "  belt_support_wedge_layers (N) → --wedge-layers N (default 10)",
            "  keel_only flag (from gate)    → --no-supports",
            "support_threshold_angle / _top_z_distance / _object_xy_distance",
            "/ _bottom_z_distance DO NOT need C++ glue — they propagate",
            "via the tmp_in 3MF project_settings.config.",
        ],
    ),
    Stage(
        name="3b.preprocessor",
        file_ref="validation/support_preprocess.py",
        reads=["tmp_in.3mf", "support_threshold_angle(3MF)",
               "support_top_z_distance(3MF)", "support_object_xy_distance(3MF)",
               "support_bottom_z_distance(3MF)",
               "belt_directional_supports(3MF)", "cli_args"],
        writes=["tmp_out.3mf",
                "tmp_out:3D/Objects/<name>.model",
                "tmp_out:3D/Objects/support_part.model",
                "tmp_out:3D/Objects/support_wedge.model",
                "tmp_out:Metadata/model_settings.config <part> matrices"],
        coord_frame_in="3MF item+component transforms → WORLD",
        coord_frame_out="LOCAL_MESH per <part>; matrix metadata holds the world placement",
        notes=[
            "BUG belt-zyt: support+wedge <part> matrix was IDENTITY while",
            "model's was (Tx,Ty,Tz) → support landed at NEGATIVE world coords",
            "→ belt slicer hung. Fix: copy model's matrix into support+wedge.",
            "Fix lives at lines ~1380 and ~1400 in export_3mf_two_volumes().",
        ],
    ),
    Stage(
        name="4.slicer",
        file_ref="libslic3r/Print*.cpp + GCode.cpp + GCodeWriter.cpp + BeltTransform.*",
        reads=["model_objects (with injected volumes)", "layer_height",
               "support_filament_settings", "machine_start_gcode",
               "all print/printer/filament settings"],
        writes=["gcode_lines[]", "Z_gcode = layer_z + Y·tan(45°)",
                "Y_mach = √2·Y_gcode (firmware reads literal)"],
        coord_frame_in="LOCAL_MESH + instance.transformation",
        coord_frame_out="GCODE coords (XY world, Z inclined)",
        notes=[
            "Belt forward F=[0,1;1,1] gives Y_v=Z_w, Z_v=Y_w+Z_w.",
            "Slices on planes Y_virt=N·layer_height·1/cos(45°).",
            "z_mach = -Y_g + Z_g = layer_z (constant per layer).",
            "If Z_mach<0 in any move → R11 FAIL — driver-killer scenario.",
        ],
    ),
    Stage(
        name="5.gate",
        file_ref="validation/belt_gcode_gate.py",
        reads=["gcode_file"],
        writes=["gate_result(PASS|WARN|FAIL)", "rule_violations[]"],
        coord_frame_in="GCODE",
        coord_frame_out="(verdict)",
        notes=[
            "R1-R5,R7,R8,R9 PASS: structural integrity",
            "R11 PASS: z_mach ≥ -0.05mm — safety-critical",
            "BLOCKED → must NOT upload (regola tassativa, mem #680)",
        ],
    ),
    Stage(
        name="6.upload",
        file_ref="validation/sweeps/queue_print.py + Moonraker job_queue API",
        reads=["gate=PASS|WARN", "gcode_file", "ideaformer credentials"],
        writes=["printer_data/gcodes/<dir>/<file>.gcode (remote)",
                "Moonraker queue entries"],
        coord_frame_in="(file)",
        coord_frame_out="(printed object on belt)",
        notes=[
            "Klipper kinematics: literal X/Y/Z, NO compensation in firmware.",
            "Pre-print: verify Infinity Flow ON, filament loaded.",
        ],
    ),
]

# Cross-stage invariants — single source of truth for things that span
# multiple stages and are easy to break.
INVARIANTS: List[Tuple[str, str, str]] = [
    (
        "Same local frame for injected volumes",
        "Stage 3 + 3b",
        "model.vertices and support.vertices share the same LOCAL origin; "
        "model_settings.config <part> matrices for support+wedge MUST "
        "equal the model's <part> matrix.",
    ),
    (
        "Z_min=0 after keel-align",
        "Stage 1 → Stage 3b → Stage 4",
        "After Stage 1 keel-align, world bbox.min.z ≈ 0. The preprocessor "
        "must not shift this; the slicer must not regress it. R7 fails if "
        "first layer Y_range > 2mm.",
    ),
    (
        "Inclined-Z formula",
        "Stage 4",
        "Z_gcode = layer_z + Y_gcode·tan(45°). Skipping this for any move "
        "yields Z_mach = layer_z − Y_gcode, which goes negative for Y > "
        "layer_z. R11 fails.",
    ),
    (
        "Per-object enable_support force-false",
        "Stage 3 → Stage 4",
        "After inject, every ModelObject has enable_support=false at the "
        "per-object level. This prevents Orca's native support generator "
        "(broken on belt) from running again on the injected volumes.",
    ),
    (
        "Print preset is the SoT for enable_support",
        "Stage 2",
        "belt_supports_preprocess_mode reads enable_support from print "
        "preset, not per-object. (Per-object would always read false after "
        "first inject — circular.)",
    ),
]


def cmd_describe() -> None:
    for s in STAGES:
        print(f"\n=== {s.name} ===")
        print(f"  file:   {s.file_ref}")
        print(f"  in :    {s.coord_frame_in}")
        print(f"  out:    {s.coord_frame_out}")
        print(f"  reads:  {', '.join(s.reads) or '-'}")
        print(f"  writes: {', '.join(s.writes) or '-'}")
        for n in s.notes:
            print(f"     · {n}")


def cmd_whatif(param: str) -> None:
    """List stages that read this param (directly or via produced outputs)."""
    print(f"\nIf '{param}' changes, the following stages re-derive:")
    affected: List[Tuple[str, str]] = []
    pending: Set[str] = {param}
    seen: Set[str] = set()
    while pending:
        p = pending.pop()
        if p in seen: continue
        seen.add(p)
        for s in STAGES:
            for r in s.reads:
                # match exact or substring (so support_threshold_angle matches
                # `support_threshold_angle(3MF)` etc.)
                if p == r or p in r:
                    affected.append((s.name, r))
                    for w in s.writes:
                        # The stage's writes become new "changed" values
                        # downstream stages might read.
                        pending.add(w)
                    break
    if not affected:
        print(f"  (no stage reads '{param}' — is it a tracked parameter?)")
        return
    seen_stages = set()
    for stage_name, via in affected:
        if stage_name in seen_stages: continue
        seen_stages.add(stage_name)
        print(f"  · {stage_name:20s}  (reads via: {via})")


def cmd_invariants() -> None:
    print("\nCross-stage invariants:\n")
    for title, scope, desc in INVARIANTS:
        print(f"  • {title}  [{scope}]")
        print(f"      {desc}\n")


def cmd_trace(target: str) -> None:
    """Backward trace: which params/stages contribute to producing `target`?"""
    if target.startswith("path:"):
        target = target[len("path:"):]
    print(f"\nBackward trace for '{target}':\n")
    contributors: List[str] = []
    visited: Set[str] = set()
    queue: List[str] = [target]
    while queue:
        p = queue.pop(0)
        if p in visited: continue
        visited.add(p)
        for s in STAGES:
            for w in s.writes:
                if p == w or p in w:
                    contributors.append(f"  · {s.name:20s} writes  '{w}'  reads  {s.reads}")
                    for r in s.reads:
                        queue.append(r)
                    break
    if not contributors:
        print(f"  (no stage writes a value matching '{target}')")
        return
    for line in contributors:
        print(line)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["describe", "whatif", "invariants", "trace"])
    ap.add_argument("arg", nargs="?", default=None)
    args = ap.parse_args()
    if args.cmd == "describe":
        cmd_describe()
    elif args.cmd == "whatif":
        if not args.arg: sys.exit("usage: pipeline_sim.py whatif <param>")
        cmd_whatif(args.arg)
    elif args.cmd == "invariants":
        cmd_invariants()
    elif args.cmd == "trace":
        if not args.arg: sys.exit("usage: pipeline_sim.py trace <target>")
        cmd_trace(args.arg)


if __name__ == "__main__":
    main()
