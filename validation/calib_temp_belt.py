#!/usr/bin/env python3
"""
calib_temp_belt — Belt-adapted temperature tower calibration.

Reuses resources/calib/temperature_tower/temperature_tower.stl:
  1. Cut Z to N_zones × zone_height (default 5 × 10mm = 50mm)
  2. Rotate 90° around X axis (Z_cart → Y_orca, Y_cart → Z_orca)
     Final dims in Orca CAD frame: X≈44.5, Y=50, Z=10mm
  3. Add 45° wedge in front (Y_min): triangular prism, X spans tower X,
     ramp from (Y=0,Z=0) to (Y=H_tower,Z=H_tower) — slope matches tower
     leading edge, no overhang generation needed
  4. Translate so min(Y+Z) = 0 (belt keel-align preview)
  5. Export 3MF with Generic PLA @IdeaFormer IR3 V2 preset + enable_support=0
  6. Slice via Orca CLI Release binary with flattened machine preset
  7. Inject M104 at Z_gcode = N×zone_height_Y for n=2..N_zones (zone-boundary
     temperature ramps). Initial temp = temps[0] already set in start gcode.
  8. Gate via belt_gcode_gate.py

Dry-run by default — outputs gcode + report; does NOT upload to printer.

Usage:
    python3 validation/calib_temp_belt.py
    python3 validation/calib_temp_belt.py --temps 195,205,215,225,235 --out /tmp/calib_temp
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[1]
STL = REPO / "resources/calib/temperature_tower/temperature_tower.stl"
MACHINE = REPO / "resources/profiles/IdeaFormer/machine/IdeaFormer IR3 V2 0.4 nozzle.json"
PROCESS = REPO / "resources/profiles/IdeaFormer/process/0.20mm Standard @IdeaFormer IR3 V2.json"
FILAMENT = REPO / "resources/profiles/IdeaFormer/filament/Generic PLA @IdeaFormer IR3 V2.json"
ORCA = REPO / "build/src/Release/orca-slicer"
GATE = REPO / "validation/belt_gcode_gate.py"

sys.path.insert(0, str(REPO / "validation"))
from orca_profile_flatten import flatten_profile  # noqa: E402


def build_tower_and_wedge(zone_height: float, n_zones: int) -> trimesh.Trimesh:
    """
    Belt-correct orientation (v3 — hypotenuse on belt):
    1. Cut Z to N zones × zone_height (50mm for 5×10)
    2. Rotate 180° around Y axis (small base now at Z_cart=0)
    3. Rotate -45° around X axis (tilt 45° in YZ)
    4. Translate so tower's small-base line coincides with wedge cateto BC
    5. Build isocele right-triangle wedge prism:
         A(0,0), B(L_hyp, 0), C(L_hyp/2, L_hyp/2),  L_hyp = zone_height·√2
       HYPOTENUSE AB on belt (Z=0). Cateti AC, BC each = zone_height long.
       Tower's small base coincides with cateto BC: from B(L_hyp,0) → C(L_hyp/2, L_hyp/2).
       3 long edges of wedge prism parallel to X.

    Tower grows in +Y, +Z direction from cateto BC at 45°. Base piccola near
    wedge, base grande far from wedge. Zone print-order: small→big.
    Z_gcode per zone = zone_height·√2 (no overlap between zones).
    First-layer behavior applies ONLY to the wedge (hypotenuse-on-belt).
    """
    tower = trimesh.load_mesh(STL)
    assert tower.is_watertight, "upstream STL not watertight"

    # 1. Cut Z to target height
    target_z = zone_height * n_zones
    if tower.bounds[1, 2] > target_z:
        b = tower.bounds
        cx, cy = 0.5 * (b[0, 0] + b[1, 0]), 0.5 * (b[0, 1] + b[1, 1])
        size_x = (b[1, 0] - b[0, 0]) + 20.0
        size_y = (b[1, 1] - b[0, 1]) + 20.0
        clip = trimesh.creation.box(extents=[size_x, size_y, target_z])
        clip.apply_translation([cx, cy, target_z / 2.0])
        tower = tower.intersection(clip)

    # 2. Rotation 180° around Y axis → small base now at Z_cart=0
    rot1 = trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0])
    tower.apply_transform(rot1)
    b = tower.bounds
    tower.apply_translation([
        -0.5 * (b[0, 0] + b[1, 0]),  # center X
        -b[0, 1],                     # Y_min=0
        -b[0, 2],                     # Z_min=0
    ])

    # 3. Rotation -45° around X axis: (y,z) → ((y+z)/√2, (z-y)/√2)
    rot2 = trimesh.transformations.rotation_matrix(-np.pi / 4, [1, 0, 0])
    tower.apply_transform(rot2)

    # 4. Translate to place tower's small-base coincident with wedge BC cateto
    # After rot, tower has a small-base line from (Y=0, Z_neg) to (Y=zh, Z=Z_neg-zh).
    # We want it to go from C(L_hyp/2, L_hyp/2) to B(L_hyp, 0), where L_hyp = zh·√2.
    L_hyp = zone_height * np.sqrt(2)
    h = L_hyp / 2  # = zone_height/√2 = 7.07 for zh=10
    b = tower.bounds
    tower.apply_translation([
        0,
        -b[0, 1] + h,  # extra +h so small-base goes (Y=h,Z=h)→(Y=L_hyp,Z=0)
        -b[0, 2],
    ])

    # 5. Wedge isocele right-triangle prism, HYPOTENUSE on belt
    b = tower.bounds
    x_min, x_max = b[0, 0], b[1, 0]
    wedge_verts = np.array([
        [x_min, 0, 0],         # 0: A_left  (ipotenusa start, on belt)
        [x_max, 0, 0],         # 1: A_right
        [x_min, L_hyp, 0],     # 2: B_left  (ipotenusa end, on belt; tower attaches at C)
        [x_max, L_hyp, 0],     # 3: B_right
        [x_min, h, h],         # 4: C_left  (peak, right angle)
        [x_max, h, h],         # 5: C_right
    ])
    wedge_faces = np.array([
        # bottom (hypotenuse AB face on belt, -Z normal)
        [0, 3, 1], [0, 2, 3],
        # left slope (cateto AC, normal up-left −Y+Z)
        [0, 1, 5], [0, 5, 4],
        # right slope (cateto BC, normal up-right +Y+Z) — tower attaches here
        [2, 5, 3], [2, 4, 5],
        # side −X (triangle A-B-C at x=x_min, normal −X)
        [0, 4, 2],
        # side +X (triangle at x=x_max, normal +X)
        [1, 3, 5],
    ])
    wedge = trimesh.Trimesh(vertices=wedge_verts, faces=wedge_faces)
    wedge.fix_normals()
    assert wedge.is_watertight, "wedge not watertight"

    # 6. Final rotation -90° around Z model axis (long axis on X belt).
    # Applied separately so we can track wedge's post-rotation bounds.
    rot_final = trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 0, 1])
    tower.apply_transform(rot_final)
    wedge.apply_transform(rot_final)

    combined = trimesh.util.concatenate([tower, wedge])
    b = combined.bounds
    translation = np.array([-b[0, 0], -b[0, 1], -b[0, 2]])
    combined.apply_translation(translation)
    wedge.apply_translation(translation)

    yz_sum = combined.vertices[:, 1] + combined.vertices[:, 2]
    assert yz_sum.min() >= -1e-6, (
        f"keel-align violated: min(Y+Z)={yz_sum.min()} < 0 — would fail R11"
    )

    # Track wedge's Z_gcode max for layer-bound M104 boundary calc
    combined.metadata["wedge_max_yz"] = float(
        np.max(wedge.vertices[:, 1] + wedge.vertices[:, 2])
    )
    return combined


def export_3mf(mesh: trimesh.Trimesh, out_3mf: Path, project_config: dict):
    """Write minimal Orca 3MF with the compound mesh + embedded preset config."""
    out_3mf.parent.mkdir(parents=True, exist_ok=True)
    # Use trimesh to write base 3MF then patch in project_settings.config
    mesh.export(str(out_3mf), file_type="3mf")

    # Patch project_settings.config in the 3MF zip
    cfg_lines = []
    for k, v in project_config.items():
        if isinstance(v, list):
            v = ";".join(str(x) for x in v)
        cfg_lines.append(f"{k} = {v}\n")
    cfg_text = "".join(cfg_lines)

    tmp_3mf = out_3mf.with_suffix(".tmp.3mf")
    with zipfile.ZipFile(out_3mf, "r") as zin, zipfile.ZipFile(
        tmp_3mf, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.namelist():
            zout.writestr(item, zin.read(item))
        zout.writestr("Metadata/project_settings.config", cfg_text)
    tmp_3mf.replace(out_3mf)


def slice_cli(in_3mf: Path, out_dir: Path, temps: list[int]) -> Path:
    """Invoke Orca CLI with flattened machine preset + process + filament."""
    out_dir.mkdir(parents=True, exist_ok=True)
    flat_machine = flatten_profile(MACHINE)
    settings_arg = f"{flat_machine};{PROCESS}"

    # Override filament nozzle_temperature[_initial_layer] to first zone temp
    flat_fil_path = flatten_profile(FILAMENT)
    fil_data = json.loads(flat_fil_path.read_text())
    fil_data["nozzle_temperature_initial_layer"] = [str(temps[0])]
    fil_data["nozzle_temperature"] = [str(temps[0])]
    flat_fil_path.write_text(json.dumps(fil_data, indent=2))

    cmd = [
        str(ORCA),
        "--slice", "1",
        "--load-settings", settings_arg,
        "--load-filaments", str(flat_fil_path),
        "--outputdir", str(out_dir),
        str(in_3mf),
    ]
    print(f"[slice] {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0:
        print(f"[slice] STDERR:\n{res.stderr[-2000:]}")
        raise RuntimeError(f"orca-slicer exit {res.returncode}")

    flat_machine.unlink(missing_ok=True)
    flat_fil_path.unlink(missing_ok=True)

    gcodes = sorted(out_dir.glob("*.gcode"))
    if not gcodes:
        raise RuntimeError(f"no gcode produced in {out_dir}")
    return gcodes[0]


def inject_m104(gcode_path: Path, boundaries: list[tuple[float, int]]) -> int:
    """
    Inject `M104 S<T>` lines at the layer immediately reaching each Z_gcode
    threshold. Returns count of injections done.

    boundaries: list of (z_threshold_mm, temp_celsius). Sorted ascending z.
    The first temp must already be in start gcode — we inject only transitions.
    """
    src = gcode_path.read_text().splitlines(keepends=True)
    out_lines = []
    cursor = 0
    z_pat = re.compile(r"^;Z[: ]\s*(-?\d+(?:\.\d+)?)")
    z_height_pat = re.compile(r"^;Z_HEIGHT:\s*(-?\d+(?:\.\d+)?)")
    layer_change = ";LAYER_CHANGE"
    in_layer_after_change = False
    cur_z = None
    n_injected = 0
    pending_inject = None

    for line in src:
        out_lines.append(line)
        if line.startswith(layer_change):
            in_layer_after_change = True
            cur_z = None
            continue
        if in_layer_after_change:
            m = z_pat.match(line) or z_height_pat.match(line)
            if m:
                cur_z = float(m.group(1))
                while cursor < len(boundaries) and cur_z >= boundaries[cursor][0]:
                    z_thr, T = boundaries[cursor]
                    pending_inject = (
                        f"M104 S{T} ; calib-zone-{cursor + 2} "
                        f"(z_gcode>={z_thr:.1f}mm)\n"
                    )
                    cursor += 1
                if pending_inject:
                    out_lines.append(pending_inject)
                    n_injected += 1
                    pending_inject = None
                in_layer_after_change = False

    gcode_path.write_text("".join(out_lines))
    return n_injected


def gate(gcode_path: Path) -> tuple[int, str]:
    """Run belt_gcode_gate.py. Returns (exit_code, last 30 lines of stdout)."""
    res = subprocess.run(
        ["python3", str(GATE), str(gcode_path)],
        capture_output=True, text=True, timeout=60,
    )
    return res.returncode, "\n".join(res.stdout.splitlines()[-30:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--temps", default="195,205,215,225,235",
                    help="Comma-separated zone temperatures. Default PLA range.")
    ap.add_argument("--zone-height", type=float, default=10.0,
                    help="Y_orca height per zone in mm (default 10).")
    ap.add_argument("--out", type=Path, default=Path("/tmp/calib_temp_belt"),
                    help="Output directory.")
    args = ap.parse_args()

    temps = [int(t) for t in args.temps.split(",")]
    n_zones = len(temps)
    assert n_zones >= 2, "need ≥2 temperatures"

    print(f"=== Belt Temperature Tower Calibration ===")
    print(f"  Zones        : {n_zones} × {args.zone_height}mm")
    print(f"  Temperatures : {temps} °C")
    print(f"  Output       : {args.out}")
    print()

    # 1. Geometry
    print("[1/6] Building tower + wedge...")
    mesh = build_tower_and_wedge(args.zone_height, n_zones)
    ext = mesh.extents
    bounds = mesh.bounds
    print(f"  Tower+wedge bounds: X={bounds[0,0]:.1f}..{bounds[1,0]:.1f}, "
          f"Y={bounds[0,1]:.1f}..{bounds[1,1]:.1f}, "
          f"Z={bounds[0,2]:.1f}..{bounds[1,2]:.1f}")
    print(f"  Extents (X,Y,Z): {ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f} mm")
    z_gcode_max = ext[1] + ext[2]
    print(f"  Z_gcode max ≈ {z_gcode_max:.1f}mm; ~{z_gcode_max/0.283:.0f} layers")

    args.out.mkdir(parents=True, exist_ok=True)
    out_3mf = args.out / "calib_temp_belt.3mf"

    # 2. Project config — disable support, set initial temp, force flat layout
    project_cfg = {
        "enable_support": 0,
        "support_threshold_angle": 30,
        "nozzle_temperature_initial_layer": temps[0],
        "nozzle_temperature": temps[0],
        "brim_type": "outer_only",
        "brim_width": 0,  # no brim — wedge IS the adhesion
        "enable_prime_tower": 0,
    }
    print(f"[2/6] Exporting 3MF → {out_3mf}")
    export_3mf(mesh, out_3mf, project_cfg)

    # 3. Slice
    print(f"[3/6] Slicing via Orca CLI (Release)...")
    gcode = slice_cli(out_3mf, args.out, temps)
    print(f"  Sliced: {gcode.name} ({gcode.stat().st_size} bytes)")

    # 4. M104 injection — LAYER-BOUND (not geometry-bound).
    # After the wedge phase (Z_gcode ∈ [0, wedge_max_yz]) all at initial T,
    # split the remaining Z_gcode into n_zones equal stripes.
    # Each stripe gets temps[i]; M104 transitions between consecutive stripes.
    wedge_max_yz = mesh.metadata["wedge_max_yz"]
    post_wedge_range = z_gcode_max - wedge_max_yz
    seg_width = post_wedge_range / n_zones
    boundaries = []
    for i in range(1, n_zones):  # n_zones - 1 transitions
        z_thr = wedge_max_yz + i * seg_width
        boundaries.append((z_thr, temps[i]))

    print(f"[4/6] Injecting M104 at zone boundaries:")
    for z, t in boundaries:
        print(f"  Z_gcode ≥ {z:.1f}mm → M104 S{t}")
    n_inj = inject_m104(gcode, boundaries)
    print(f"  Injected {n_inj} M104 lines (expected {len(boundaries)})")
    if n_inj != len(boundaries):
        print(f"  WARN: mismatch — gcode layer markers may differ from expected")

    # 5. Gate
    print(f"[5/6] Running belt_gcode_gate...")
    rc, gate_tail = gate(gcode)
    label = {0: "PASS", 1: "FAIL", 2: "WARN"}.get(rc, f"rc={rc}")
    print(f"  Gate result: {label}")
    print(f"  {'─' * 50}")
    print(gate_tail)

    # 6. Report
    info = {
        "gcode": str(gcode),
        "extents_mm": {"X": ext[0], "Y": ext[1], "Z": ext[2]},
        "bounds_mm": {
            "x_min": bounds[0, 0], "x_max": bounds[1, 0],
            "y_min": bounds[0, 1], "y_max": bounds[1, 1],
            "z_min": bounds[0, 2], "z_max": bounds[1, 2],
        },
        "n_zones": n_zones,
        "zone_height_mm": args.zone_height,
        "temps_celsius": temps,
        "m104_boundaries": [{"z_gcode_mm": z, "temp": t} for z, t in boundaries],
        "z_gcode_max_mm": z_gcode_max,
        "gate_exit_code": rc,
        "gate_label": label,
        "m104_injections_actual": n_inj,
    }
    info_path = args.out / "calib_info.json"
    info_path.write_text(json.dumps(info, indent=2))
    print(f"[6/6] Report → {info_path}")
    print()
    print(f"Final gcode: {gcode}")
    print(f"DRY-RUN COMPLETE. No upload performed.")
    print(f"To print: sshpass -p 1234 scp {gcode.name} "
          f"ideaformer@<PRINTER_HOST>:printer_data/gcodes/ && "
          f"curl -X POST 'http://<PRINTER_HOST>/printer/print/start' "
          f"-H 'Content-Type: application/json' "
          f"-d '{{\"filename\":\"{gcode.name}\"}}'")
    return 0 if rc != 1 else 2


if __name__ == "__main__":
    sys.exit(main())
