#!/usr/bin/env python3
"""
calib_temp_belt_v3 — multi-instance belt temp tower with per-zone T + text-cut.

Workflow:
  1. For each T in PLA temp array [230..190 step 5°C]:
       - Generate text mesh via MCP `model_add_text` (HarmonyOS Sans bundled)
       - SCP exported 3MF from behemoth back to nativedev
       - Build instance_<T>.3mf locally by injecting the new text mesh into the
         template (replaces Part 2 mesh + metadata text)
  2. Combine all 9 instances into one assembly via MCP:
       - clear plate, load each instance, object_transform translate to Y_offset
       - model_export combined 3MF
  3. Slice combined 3MF via Orca CLI Release with flattened PLA preset.
  4. Inject M104 transitions:
       - At Z_gcode of each instance's wedge start: M104 S<T_wedge>
       - At Z_gcode of each instance's tower body start (layer 32 of instance):
         M104 S<TEMPS[n]>
  5. Run belt_gcode_gate.

Output: /tmp/calib_temp_belt_v6/calib_temp_belt_v6.gcode (sliced + M104 injected)

Dry-run by default. No upload.
"""
from __future__ import annotations

import argparse, json, re, shutil, subprocess, sys, time, zipfile
from pathlib import Path
import requests
import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[1]
MCP_URL = "http://127.0.0.1:13619/mcp"
BEHEMOTH = "<WORKSTATION_HOST>"
BEHEMOTH_USER = "tommaso"
BEHEMOTH_PASS = "<PASSWORD>"

TEMPLATE_LOCAL = Path("/tmp/template_temp_belt.3mf")
OUT_DIR = Path("/tmp/calib_temp_belt_v6")
MACHINE = REPO / "resources/profiles/IdeaFormer/machine/IdeaFormer IR3 V2 0.4 nozzle.json"
PROCESS = REPO / "resources/profiles/IdeaFormer/process/0.20mm Standard @IdeaFormer IR3 V2.json"
FILAMENT = REPO / "resources/profiles/IdeaFormer/filament/Generic PLA @IdeaFormer IR3 V2.json"
ORCA = REPO / "build/src/Release/orca-slicer"
GATE = REPO / "validation/belt_gcode_gate.py"

TEMPS = [230, 225, 220, 215, 210, 205, 200, 195, 190]
T_WEDGE = 220
GAP_MM = 5.0
LAYER_HEIGHT = 0.283
WEDGE_LAYERS = 31

sys.path.insert(0, str(REPO / "validation"))
from orca_profile_flatten import flatten_profile  # noqa: E402


# ----- MCP helpers ------------------------------------------------------------
def _mcp(method, params=None, timeout=60):
    r = requests.post(
        MCP_URL,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        timeout=timeout,
    )
    return r.json()


def mcp_tool(name, args=None, timeout=60):
    res = _mcp("tools/call", {"name": name, "arguments": args or {}}, timeout).get(
        "result", {}
    )
    content = res.get("content", [])
    if content:
        text = content[0].get("text", "{}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
    return res


def behemoth_scp_from(remote, local):
    subprocess.run(
        ["sshpass", "-p", BEHEMOTH_PASS, "scp", "-o", "StrictHostKeyChecking=no",
         f"{BEHEMOTH_USER}@{BEHEMOTH}:{remote}", str(local)],
        check=True, capture_output=True,
    )


def behemoth_scp_to(local, remote):
    subprocess.run(
        ["sshpass", "-p", BEHEMOTH_PASS, "scp", "-o", "StrictHostKeyChecking=no",
         str(local), f"{BEHEMOTH_USER}@{BEHEMOTH}:{remote}"],
        check=True, capture_output=True,
    )


def clear_plate():
    while True:
        objs = mcp_tool("model_list_objects").get("objects", [])
        if not objs:
            break
        mcp_tool("model_delete_object", {"index": 0})


# ----- Text mesh generation ---------------------------------------------------
def generate_text_mesh(T: int) -> trimesh.Trimesh:
    """Generate 3D text mesh via MCP. Returns trimesh.Trimesh in local coords."""
    clear_plate()
    mcp_tool(
        "model_add_text",
        {"text": str(T), "depth_mm": 1.0, "size_mm": 9.9},
    )
    remote = f"/tmp/text_{T}.3mf"
    mcp_tool("model_export", {"path": remote})
    local = OUT_DIR / f"text_{T}.3mf"
    behemoth_scp_from(remote, local)
    scene = trimesh.load(str(local))
    mesh = (
        scene.to_geometry()
        if hasattr(scene, "to_geometry")
        else scene.dump(concatenate=True) if hasattr(scene, "dump") else scene
    )
    return mesh


# ----- 3MF instance builder ---------------------------------------------------
def _make_object_xml(obj_id: int, mesh: trimesh.Trimesh) -> str:
    """Build a single <object id="N"> XML with raw mesh content."""
    verts = "\n".join(
        f'     <vertex x="{v[0]:.6f}" y="{v[1]:.6f}" z="{v[2]:.6f}"/>'
        for v in mesh.vertices
    )
    tris = "\n".join(
        f'     <triangle v1="{int(f[0])}" v2="{int(f[1])}" v3="{int(f[2])}"/>'
        for f in mesh.faces
    )
    return f'''  <object id="{obj_id}" type="model">
   <mesh>
    <vertices>
{verts}
    </vertices>
    <triangles>
{tris}
    </triangles>
   </mesh>
  </object>'''


def build_instance_3mf(T: int, text_mesh: trimesh.Trimesh, out_3mf: Path) -> Path:
    """Copy template, replace object id=2 (Part 2 text) mesh with the new T text
    mesh, update text metadata. Save as out_3mf."""
    shutil.copy(TEMPLATE_LOCAL, out_3mf)
    with zipfile.ZipFile(out_3mf, "r") as zf:
        xml = zf.read("3D/3dmodel.model").decode("utf-8")
        ms = zf.read("Metadata/model_settings.config").decode("utf-8")

    # Replace <object id="2" ...>...</object> with new text mesh
    new_obj_xml = _make_object_xml(2, text_mesh)
    new_xml = re.sub(
        r'<object id="2"[^>]*>.*?</object>',
        new_obj_xml,
        xml,
        count=1,
        flags=re.DOTALL,
    )

    # Update metadata: name="215" → name="<T>", text="215" → text="<T>"
    new_ms = re.sub(
        r'<metadata key="name" value="215"/>',
        f'<metadata key="name" value="{T}"/>',
        ms,
    )
    new_ms = re.sub(r'text="215"', f'text="{T}"', new_ms)

    tmp = out_3mf.with_suffix(".tmp.3mf")
    with zipfile.ZipFile(out_3mf, "r") as zin, zipfile.ZipFile(
        tmp, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.namelist():
            if item == "3D/3dmodel.model":
                zout.writestr(item, new_xml)
            elif item == "Metadata/model_settings.config":
                zout.writestr(item, new_ms)
            else:
                zout.writestr(item, zin.read(item))
    tmp.replace(out_3mf)
    return out_3mf


# ----- Combined assembly via MCP ---------------------------------------------
def assemble_combined_via_mcp(instance_3mfs: list[Path], out_combined_local: Path):
    """Clear plate, load each instance, translate to Y_offset, export combined."""
    clear_plate()

    # Get template instance bbox (the first loaded gives us reference)
    y_extent = None
    for i, p in enumerate(instance_3mfs):
        T = TEMPS[i]
        remote = f"/tmp/instance_T{T}.3mf"
        behemoth_scp_to(p, remote)
        res = mcp_tool("model_load_file", {"path": remote})
        idx = (res.get("object_indices") or [res.get("object_index")])[0]
        if idx is None:
            # Fallback: list and take last
            objs = mcp_tool("model_list_objects").get("objects", [])
            idx = len(objs) - 1

        # Get bbox of just-loaded instance
        objs = mcp_tool("model_list_objects").get("objects", [])
        bbox = objs[idx]["bounding_box"]
        bb_min = bbox["min"]
        bb_max = bbox["max"]
        if y_extent is None:
            y_extent = bb_max[1] - bb_min[1]
            print(f"  template instance Y extent = {y_extent:.2f}mm")

        # Compute desired Y position
        desired_y_min = i * (y_extent + GAP_MM)
        cur_center_y = 0.5 * (bb_min[1] + bb_max[1])
        new_center_y = desired_y_min + 0.5 * y_extent
        cur_center_x = 0.5 * (bb_min[0] + bb_max[0])
        cur_center_z = 0.5 * (bb_min[2] + bb_max[2])

        mcp_tool(
            "object_transform",
            {
                "index": idx,
                "translate": [cur_center_x, new_center_y, cur_center_z],
            },
        )
        print(f"  [{i+1}/{len(TEMPS)}] T={T}: loaded idx={idx}, center_y → {new_center_y:.2f}mm")

    # Export combined
    remote_combined = "/tmp/calib_temp_belt_v6.3mf"
    mcp_tool("model_export", {"path": remote_combined})
    behemoth_scp_from(remote_combined, out_combined_local)
    return out_combined_local


# ----- Slice ------------------------------------------------------------------
def slice_cli(in_3mf: Path, out_dir: Path, temp_init: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    flat_machine = flatten_profile(MACHINE)
    flat_fil = flatten_profile(FILAMENT)
    fil_data = json.loads(flat_fil.read_text())
    fil_data["nozzle_temperature_initial_layer"] = [str(temp_init)]
    fil_data["nozzle_temperature"] = [str(temp_init)]
    fil_data["hot_plate_temp"] = ["75"]
    fil_data["hot_plate_temp_initial_layer"] = ["75"]
    flat_fil.write_text(json.dumps(fil_data, indent=2))

    settings_arg = f"{flat_machine};{PROCESS}"
    cmd = [
        str(ORCA),
        "--slice", "1",
        "--load-settings", settings_arg,
        "--load-filaments", str(flat_fil),
        "--outputdir", str(out_dir),
        str(in_3mf),
    ]
    print(f"[slice] {' '.join(cmd[:5])} ... {in_3mf.name}")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    flat_machine.unlink(missing_ok=True)
    flat_fil.unlink(missing_ok=True)
    if res.returncode != 0:
        print(res.stderr[-2000:])
        raise RuntimeError(f"orca-slicer exit {res.returncode}")
    gcs = sorted(out_dir.glob("*.gcode"))
    if not gcs:
        raise RuntimeError("no gcode produced")
    return gcs[0]


# ----- M104 inject -----------------------------------------------------------
def inject_m104_per_instance(
    gcode_path: Path, boundaries: list[tuple[float, int, str]]
) -> int:
    """boundaries: list of (z_gcode_threshold, temp, comment_tag). Sorted asc."""
    src = gcode_path.read_text().splitlines(keepends=True)
    out_lines = []
    cursor = 0
    z_pat = re.compile(r"^;Z[: ]\s*(-?\d+(?:\.\d+)?)")
    z_height_pat = re.compile(r"^;Z_HEIGHT:\s*(-?\d+(?:\.\d+)?)")
    layer_change = ";LAYER_CHANGE"
    in_layer_after_change = False
    n_injected = 0
    for line in src:
        out_lines.append(line)
        if line.startswith(layer_change):
            in_layer_after_change = True
            continue
        if in_layer_after_change:
            m = z_pat.match(line) or z_height_pat.match(line)
            if m:
                cur_z = float(m.group(1))
                injs = []
                while cursor < len(boundaries) and cur_z >= boundaries[cursor][0]:
                    z_thr, T, tag = boundaries[cursor]
                    injs.append(
                        f"M104 S{T} ; {tag} (z_gcode>={z_thr:.2f}mm)\n"
                    )
                    cursor += 1
                if injs:
                    out_lines.extend(injs)
                    n_injected += len(injs)
                in_layer_after_change = False
    gcode_path.write_text("".join(out_lines))
    return n_injected


def gate(gcode_path: Path) -> tuple[int, str]:
    res = subprocess.run(
        ["python3", str(GATE), str(gcode_path)],
        capture_output=True, text=True, timeout=60,
    )
    return res.returncode, "\n".join(res.stdout.splitlines()[-30:])


# ----- Main flow --------------------------------------------------------------
def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"=== Belt Multi-Instance Temp Tower (v3) ===")
    print(f"  Temperatures: {TEMPS}")
    print(f"  T_wedge     : {T_WEDGE}°C")
    print(f"  Gap         : {GAP_MM}mm")
    print(f"  Wedge layers: {WEDGE_LAYERS}")
    print()

    # 1. Generate text meshes via MCP
    print("[1/6] Generating text meshes via MCP...")
    text_meshes = {}
    for T in TEMPS:
        m = generate_text_mesh(T)
        text_meshes[T] = m
        print(f"  T={T}: {len(m.vertices)} verts, {len(m.faces)} faces, extents {m.extents.tolist()}")

    # 2. Build per-T instance 3MFs
    print("\n[2/6] Building per-T instance 3MFs...")
    instance_paths = []
    for T in TEMPS:
        out = OUT_DIR / f"instance_T{T}.3mf"
        build_instance_3mf(T, text_meshes[T], out)
        instance_paths.append(out)
        print(f"  T={T}: {out.name} ({out.stat().st_size} bytes)")

    # 3. Combine via MCP
    print("\n[3/6] Combining instances via MCP (load+transform+export)...")
    combined_local = OUT_DIR / "calib_temp_belt_v6.3mf"
    assemble_combined_via_mcp(instance_paths, combined_local)
    print(f"  Combined: {combined_local} ({combined_local.stat().st_size} bytes)")

    # 4. Slice combined
    print("\n[4/6] Slicing combined via Orca CLI Release...")
    gcode = slice_cli(combined_local, OUT_DIR, T_WEDGE)
    print(f"  Gcode: {gcode.name} ({gcode.stat().st_size} bytes)")

    # 5. Compute M104 boundaries
    # First, determine actual Z_gcode min from sliced gcode (post-Orca-keel-align)
    actual_z_min = None
    for line in gcode.read_text().splitlines():
        m = re.match(r"^;Z[: ]\s*(-?\d+(?:\.\d+)?)", line)
        if m:
            actual_z_min = float(m.group(1))
            break
    print(f"\n[5/6] Computing M104 boundaries (actual Z_gcode_min={actual_z_min})...")

    # Each instance has Y_extent + Z range. We assume instances are along +Y.
    # Z_gcode within each instance: [wedge_start, wedge_end=tower_start, tower_end]
    # wedge_layers * layer_height = 31 * 0.283 = 8.77mm wedge in Z_gcode within an instance
    wedge_zg_local = WEDGE_LAYERS * LAYER_HEIGHT  # 8.77mm
    # Use design Z_gcode_min of first instance ≈ actual_z_min
    boundaries = []
    # First we need the instance Z_gcode span. Use trimesh to get template's Y+Z range.
    tmpl = trimesh.load(str(TEMPLATE_LOCAL))
    tg = tmpl.to_geometry() if hasattr(tmpl, "to_geometry") else tmpl.dump(concatenate=True)
    yz_min = float((tg.vertices[:, 1] + tg.vertices[:, 2]).min())
    yz_max = float((tg.vertices[:, 1] + tg.vertices[:, 2]).max())
    instance_zg_span = yz_max - yz_min
    print(f"  Instance Z_gcode span (template): {instance_zg_span:.2f}mm")

    # Instance n Z_gcode start (relative to actual_z_min, in world post-keel-align):
    # = actual_z_min + n * (instance_zg_span_world + Y_gap_in_zg)
    # Y_gap in Z_gcode adds GAP_MM (because the gap is along +Y)
    # Actually: between two instances along Y by 5mm, the Z_gcode span adds 5mm
    # (because Z_gcode = Y+Z and the gap is pure +Y).
    # Note: the actual Y separation in the combined assembly = y_extent + GAP_MM = 25 + 5 = 30mm.
    # So instance n+1's min Z_gcode = instance n's min Z_gcode + 30mm.
    instance_stride_zg = 25.0 + GAP_MM  # 30mm

    for i, T in enumerate(TEMPS):
        inst_zg_start = actual_z_min + i * instance_stride_zg
        inst_tower_start = inst_zg_start + wedge_zg_local
        # M104 S<T_wedge> at wedge_start (skip for i==0 since start_gcode already sets initial)
        if i > 0:
            boundaries.append((inst_zg_start, T_WEDGE, f"inst{i}-wedge"))
        # M104 S<T> at tower_start
        boundaries.append((inst_tower_start, T, f"inst{i}-tower"))

    boundaries.sort(key=lambda x: x[0])
    print(f"  M104 boundaries ({len(boundaries)} events):")
    for z, T, tag in boundaries:
        print(f"    Z_gcode ≥ {z:.2f}mm → M104 S{T} ; {tag}")
    n_inj = inject_m104_per_instance(gcode, boundaries)
    print(f"  Injected {n_inj}/{len(boundaries)} M104 lines")

    # 6. Gate
    print("\n[6/6] Running belt_gcode_gate...")
    rc, gate_tail = gate(gcode)
    label = {0: "PASS", 1: "FAIL", 2: "WARN"}.get(rc, f"rc={rc}")
    print(f"  Gate: {label}")
    print(gate_tail)

    info = {
        "temps": TEMPS,
        "t_wedge": T_WEDGE,
        "gap_mm": GAP_MM,
        "n_instances": len(TEMPS),
        "instance_zg_span_mm": instance_zg_span,
        "instance_stride_zg_mm": instance_stride_zg,
        "actual_z_min_mm": actual_z_min,
        "m104_boundaries": [{"z": z, "T": T, "tag": tag} for z, T, tag in boundaries],
        "gate": label,
        "gcode_path": str(gcode),
    }
    (OUT_DIR / "calib_info.json").write_text(json.dumps(info, indent=2))
    print(f"\nFinal gcode: {gcode}")
    print(f"DRY-RUN COMPLETE. No upload performed.")
    return 0 if rc != 1 else 2


if __name__ == "__main__":
    sys.exit(main())
