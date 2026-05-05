#!/usr/bin/env python3
"""Belt-support sweep runner — native pathway with C++ Plater→preprocessor mapping.

Topology
--------
  nativedev (this script)
    └── ssh -fN -L 127.0.0.1:13619:127.0.0.1:13619 <WORKSTATION_HOST>
  behemoth
    └── orca-slicer Release on DISPLAY=:1, MCP on 13619
    └── /home/user/orca-belt-local/validation/support_preprocess.py (87KB, --tree etc.)

After the Plater.cpp patch (commit pending), the C++ belt_supports_inject_volumes:
  1. Reads support_base_pattern_spacing from the print preset → --infill (30/spacing).
  2. Reads support_type → --tree if "tree" in name.
  3. Other support_* keys (threshold_angle, top_z_distance, xy_distance) propagate
     via the Orca-exported tmp_in 3MF Metadata/project_settings.config, which
     the preprocessor reads directly via read_3mf_support_settings().

Pipeline per variant
--------------------
  1. clean plate → load arc_bridge.stl (HW-validated belt-OK)
  2. config_set the support_* keys for this variant + enable_support=1
  3. slice_and_stats; poll slice_status.finished=True (NOT state=='complete' — wrong)
  4. find latest /tmp/orcaslicer_model/.../Metadata/.<pid>.<plate>.gcode on behemoth
  5. scp gcode back, run belt_gcode_gate.py, record PASS/WARN/FAIL
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time, urllib.request

REPO       = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE       = os.path.join(REPO, "validation/belt_gcode_gate.py")
OUT_DIR    = os.path.join(REPO, "validation/sweeps/support_v3")
SUMMARY    = os.path.join(OUT_DIR, "sweep_summary.json")
LOCAL_STL  = os.path.join(REPO, "validation/test_models/arc_bridge.stl")

BEHEMOTH       = "<WORKSTATION_HOST>"
BEHEMOTH_STL   = "/tmp/sweep_v1/arc_bridge.stl"
MCP_ENDPOINT   = "http://127.0.0.1:13619/mcp"

# -----------------------------------------------------------------------------
# 11 variants — sweep what the C++ patch + 3MF-config-propagation can actually
# pass to the preprocessor. Param mapping:
#   support_base_pattern_spacing → preprocessor --infill (30/spacing)
#   support_type "tree*"         → preprocessor --tree
#   support_threshold_angle      → preprocessor threshold_angle (via 3MF config)
#   support_top_z_distance       → preprocessor z_gap (via 3MF config)
#   support_object_xy_distance   → preprocessor xy_gap (via 3MF config)
# -----------------------------------------------------------------------------
# Variants effective via the C++/preprocessor pipeline (post belt-zyt fix):
#  - support_threshold_angle  → preprocessor reads from 3MF project_settings  ✓
#  - support_top_z_distance   → preprocessor reads from 3MF project_settings  ✓
#  - support_object_xy_distance → preprocessor reads from 3MF project_settings ✓
# Not effective until belt-rri ships the C++ Plater patch (mapping print preset
# → preprocessor CLI args):
#  - support_base_pattern_spacing → would need --infill X
#  - support_type tree            → would need --tree
# Sweep v3 (2026-05-05) — post-hw-review of v2.
# v2 verdict: ALL bonded to bed and lateral pillars too adhered. v2 swept
# top_z and xy_gap but neither is enough — the bed-attachment driver is
# wedge_layers (solid 100% base) + xy_gap aggressivo + bottom_z lift.
# v3 leverages new patches:
#   - PrintConfig: belt_support_wedge_layers (Plater→preprocessor --wedge-layers)
#   - support_bottom_z_distance now read by preprocessor (lift floor off bed)
# v3 holds: spacing=1.5 (d20%, mid winner), top=0.25 (mid winner), type=normal(auto).
# Sweep dimensions: wedge_layers ∈ {0,3,5,10} × bottom_z_gap ∈ {0,0.3,0.6} × xy_gap ∈ {0.8,1.2}.
COMMON = {"support_type":"normal(auto)","support_base_pattern_spacing":"1.5",
          "support_threshold_angle":"30","support_top_z_distance":"0.25"}
def _v(label, **kv): return {"label": label, "settings": {**COMMON, **{k: str(v) for k,v in kv.items()}}}
VARIANTS = [
    # baseline (current default-ish: wedge=10, bottom=0, xy=0.5)
    _v("0base",      support_object_xy_distance=0.5,                                    belt_support_wedge_layers=10),
    # wedge sweep (xy=0.8 fixed, no bottom lift)
    _v("1w0",        support_object_xy_distance=0.8,                                    belt_support_wedge_layers=0),
    _v("2w3",        support_object_xy_distance=0.8,                                    belt_support_wedge_layers=3),
    _v("3w5",        support_object_xy_distance=0.8,                                    belt_support_wedge_layers=5),
    # bottom-z lift sweep (wedge=3, xy=0.8)
    _v("4b3",        support_object_xy_distance=0.8, support_bottom_z_distance=0.30,    belt_support_wedge_layers=3),
    _v("5b6",        support_object_xy_distance=0.8, support_bottom_z_distance=0.60,    belt_support_wedge_layers=3),
    # aggressive xy sweep (wedge=0)
    _v("6xy12w0",    support_object_xy_distance=1.2,                                    belt_support_wedge_layers=0),
    _v("7xy12w3",    support_object_xy_distance=1.2,                                    belt_support_wedge_layers=3),
    # combos — easy-detach candidates
    _v("8easyL",     support_object_xy_distance=1.0, support_bottom_z_distance=0.30,    belt_support_wedge_layers=3),
    _v("9easyM",     support_object_xy_distance=1.2, support_bottom_z_distance=0.30,    belt_support_wedge_layers=0),
    _v("AeasyH",     support_object_xy_distance=1.2, support_bottom_z_distance=0.60,    belt_support_wedge_layers=0),
]

# ----------------------------------------------------------------- helpers
def sh(cmd, timeout=120, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)

def ssh(remote_cmd, timeout=120):
    return sh(["ssh", BEHEMOTH, remote_cmd], timeout=timeout)

def scp_to(local, remote, timeout=60):
    cp = sh(["scp","-q",local,f"{BEHEMOTH}:{remote}"], timeout=timeout)
    if cp.returncode != 0: raise RuntimeError(f"scp_to: {cp.stderr or cp.stdout}")

def scp_from(remote, local, timeout=60):
    cp = sh(["scp","-q",f"{BEHEMOTH}:{remote}",local], timeout=timeout)
    if cp.returncode != 0: raise RuntimeError(f"scp_from: {cp.stderr or cp.stdout}")

def rpc(method, params=None):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params or {}}).encode()
    req = urllib.request.Request(MCP_ENDPOINT, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())

def call(tool, args=None):
    r = rpc("tools/call", {"name":tool,"arguments":args or {}})
    if r.get("result",{}).get("isError"):
        raise RuntimeError(f"{tool} err: {r['result']}")
    return json.loads(r["result"]["content"][0]["text"])

def clean_plate():
    for o in sorted(call("model_list_objects").get("objects",[]), key=lambda x:-x["index"]):
        call("model_delete_object", {"index":o["index"]})

def wait_slice(deadline_s=300):
    """Poll slice_status until finished=True. Wait 3s first to let slice actually start."""
    time.sleep(3)
    deadline = time.time() + deadline_s
    s = {}
    while time.time() < deadline:
        s = call("slice_status")
        if isinstance(s, dict) and s.get("finished") and s.get("filament_used_mm"):
            return s
        time.sleep(2)
    return s

def latest_gcode_remote():
    rc = ssh("ls -t /tmp/orcaslicer_model/*/*/Metadata/.*.gcode 2>/dev/null | head -1", timeout=10)
    return rc.stdout.strip()

# ------------------------------------------------------------ variant
def run_variant(v):
    label = v["label"]
    t0 = time.time()
    clean_plate()
    call("model_load_file", {"path": BEHEMOTH_STL})
    settings = dict(v["settings"])
    settings["enable_support"] = "1"
    call("config_set", {"settings": settings})
    call("slice_and_stats")
    s = wait_slice()
    if not (isinstance(s, dict) and s.get("finished")):
        return {"label":label,"ok":False,"reason":f"slice timeout/no-finish",
                "settings":v["settings"]}

    src_gc = latest_gcode_remote()
    out_gc = os.path.join(OUT_DIR, f"{label}.gcode")
    if not src_gc:
        return {"label":label,"ok":False,"reason":"no gcode produced",
                "settings":v["settings"]}
    scp_from(src_gc, out_gc)
    return {
        "label": label,
        "ok": True,
        "elapsed_s": round(time.time()-t0,1),
        "print_time": s.get("print_time"),
        "filament_used_mm": s.get("filament_used_mm"),
        "filament_weight_g": s.get("filament_weight_g"),
        "warning": s.get("warning",""),
        "out_gcode": out_gc,
        "gcode_size": os.path.getsize(out_gc),
        "settings": v["settings"],
    }

# ------------------------------------------------------------ gate
def run_gate(gcode_path):
    cp = sh(["python3", GATE, gcode_path], timeout=60)
    out = cp.stdout
    if "RESULT: PASS" in out: return "PASS", out.strip().splitlines()[-1]
    if "WARNING" in out and "BLOCKED" not in out: return "WARN", out.strip().splitlines()[-1]
    if "BLOCKED" in out:
        fails = [l.strip() for l in out.splitlines() if "FAIL" in l]
        return "FAIL", "; ".join(fails[:3]) or "blocked"
    return "UNKNOWN", (out.strip().splitlines() or [cp.stderr])[-1]

# ------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-sep labels")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    ssh("mkdir -p /tmp/sweep_v1", timeout=10)
    scp_to(LOCAL_STL, BEHEMOTH_STL)

    selected = VARIANTS
    if args.only:
        wanted = set(s.strip() for s in args.only.split(","))
        selected = [v for v in VARIANTS if v["label"] in wanted]
        if not selected: sys.exit(f"no variants match --only {args.only!r}")

    existing = []
    if os.path.exists(SUMMARY):
        try: existing = json.load(open(SUMMARY))
        except Exception: existing = []
    by_label = {row["label"]: row for row in existing if isinstance(row,dict) and "label" in row}

    for v in selected:
        print(f"--- {v['label']} ---", flush=True)
        try: r = run_variant(v)
        except Exception as e: r = {"label":v["label"],"ok":False,"reason":str(e),"settings":v["settings"]}
        if r.get("out_gcode"):
            try:
                gate, msg = run_gate(r["out_gcode"])
                r["gate"] = gate; r["gate_msg"] = msg
            except Exception as e:
                r["gate"] = "ERROR"; r["gate_msg"] = str(e)
        print(f"   ok={r.get('ok')} gate={r.get('gate','?')} fil={r.get('filament_used_mm','-')} pt={r.get('print_time','-')}", flush=True)
        if r.get("gate_msg"): print(f"   {r['gate_msg'][:180]}")
        by_label[v["label"]] = r

    ordered = [by_label[v["label"]] for v in VARIANTS if v["label"] in by_label]
    json.dump(ordered, open(SUMMARY,"w"), indent=2)
    n_ok    = sum(1 for r in ordered if r.get("ok"))
    n_pass  = sum(1 for r in ordered if r.get("gate")=="PASS")
    n_warn  = sum(1 for r in ordered if r.get("gate")=="WARN")
    n_fail  = sum(1 for r in ordered if r.get("gate")=="FAIL")
    print(f"\nSummary: {SUMMARY}")
    print(f"slice OK: {n_ok}/{len(ordered)}   gate PASS: {n_pass}   WARN: {n_warn}   FAIL: {n_fail}")

if __name__ == "__main__":
    main()
