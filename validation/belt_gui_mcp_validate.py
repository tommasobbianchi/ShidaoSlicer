#!/usr/bin/env python3
"""
Belt GUI validator — MCP + SauronsEye only. No xdotool.

Pilota OrcaBelt su behemoth tramite MCP JSON-RPC (127.0.0.1:13619 via SSH
tunnel) e verifica il flusso GUI completo:

  1. Launch orca-belt wrapper (con un mesh placeholder per bypassare
     il dialog "restore unsaved project").
  2. Verifica profilo belt attivo (printer_structure == belt).
  3. Posiziona un oggetto keel-first sul belt (object_transform con
     pivot=bed-min, translate=[bed_center_x, 0, 0]).
  4. Screenshot isometrico Prepare → SauronsEye describe.
  5. Slice (con o senza supporti).
  6. Switch to Preview tab via viewport_select_tab (tab='Preview').
  7. Set preview layer al 50% + isometric + zoom_to_volumes.
  8. Screenshot Preview → SauronsEye describe.
  9. Pull gcode + run belt_gcode_gate.py.
 10. Summary JSON report.

Obiettivo #1: rilevare il crash descritto dall'utente ("premo Preview e
crasha"). Se Orca muore dopo viewport_select_tab, lo script lo nota.
Obiettivo #2: verificare gcode corretto + preview coerente.

Usage:
  python3 belt_gui_mcp_validate.py                   # run default test
  python3 belt_gui_mcp_validate.py --mesh /path.stl --supports
  python3 belt_gui_mcp_validate.py --profile "name" --keep-running
"""

from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional
import urllib.request as _u

# ── Endpoints (override via env) ──────────────────────────────────────────
BEHEMOTH_HOST = os.environ.get("BEHEMOTH_HOST", "<WORKSTATION_HOST>")
BEHEMOTH_USER = os.environ.get("BEHEMOTH_USER", "tommaso")
MCP_URL       = os.environ.get("MCP_URL",  "http://127.0.0.1:13619/mcp")
SAURON_URL    = os.environ.get("SAURON_URL", f"http://{BEHEMOTH_HOST}:8087/describe")

# ── Defaults ──────────────────────────────────────────────────────────────
DEFAULT_PROFILE = "IdeaFormer IR3 V2 0.4 nozzle"
DEFAULT_FILAMENT = "Generic PLA @IdeaFormer IR3 V2"
DEFAULT_PRINT    = "0.20mm Standard @IdeaFormer IR3 V2"
DEFAULT_MESH     = "/home/user/projects/ORCA_BELT/Supports_Test_small.stl"
PLACEHOLDER_MESH = "/home/user/projects/ORCA_BELT/validation/test_models/box_10x10x10.stl"

# ── Helpers ───────────────────────────────────────────────────────────────

class MCPError(Exception): pass

class MCP:
    """Thin JSON-RPC client for orca-mcp."""
    def __init__(self, url: str = MCP_URL):
        self.url = url
        self._id = 0
    def call(self, tool: str, args: Optional[dict] = None, timeout: int = 60) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id,
                   "method": "tools/call",
                   "params": {"name": tool, "arguments": args or {}}}
        data = json.dumps(payload).encode()
        req = _u.Request(self.url, data=data,
                         headers={"Content-Type": "application/json"})
        try:
            with _u.urlopen(req, timeout=timeout) as resp:
                doc = json.loads(resp.read())
        except Exception as e:
            raise MCPError(f"{tool}: transport error — {e}")
        r = doc.get("result", {})
        if r.get("isError"):
            raise MCPError(f"{tool}: {r}")
        texts = []
        for c in r.get("content", []):
            if c.get("type") == "text":
                t = c["text"]
                try: texts.append(json.loads(t))
                except: texts.append(t)
            elif c.get("type") == "image":
                texts.append({"__image_b64__": c["data"]})
        if not texts: return None
        return texts[0] if len(texts) == 1 else texts


def sauron_describe(png_path: str, app: str = "orca_slicer") -> dict:
    """POST PNG to SauronsEye /describe; return the JSON `description` block."""
    data = Path(png_path).read_bytes()
    boundary = "----BELT_BNDY"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="app"\r\n\r\n{app}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; '
        f'filename="frame.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = _u.Request(SAURON_URL, data=body,
                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with _u.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("description", {})
    except Exception as e:
        return {"error": str(e)}


def remote(cmd: str, timeout: int = 30) -> str:
    """Run `cmd` on behemoth via SSH; return stdout stripped."""
    r = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5",
         f"{BEHEMOTH_USER}@{BEHEMOTH_HOST}", cmd],
        capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def remote_fetch(remote_path: str, local_path: str) -> bool:
    """scp remote_path → local_path. Return True on success."""
    r = subprocess.run(
        ["scp", "-q", "-o", "ConnectTimeout=5",
         f"{BEHEMOTH_USER}@{BEHEMOTH_HOST}:{remote_path}", local_path],
        capture_output=True)
    return r.returncode == 0


# ── Phase functions ───────────────────────────────────────────────────────

def phase_launch(outdir: Path) -> dict:
    """Kill any stale orca, launch via wrapper with a placeholder mesh to
    bypass the 'restore unsaved project' dialog, wait for MCP port."""
    print("[P0] Launching orca-belt on behemoth…")
    remote('pkill -9 -f "orca-slicer --datadir" 2>/dev/null; sleep 3')
    # Launch with placeholder mesh → no restore dialog, UI goes straight to Prepare.
    launch_cmd = (
        f'setsid bash -c "DISPLAY=:1 '
        f'XAUTHORITY=/run/user/1000/gdm/Xauthority '
        f'~/bin/orca-belt {PLACEHOLDER_MESH} </dev/null '
        f'>/tmp/orcabelt.log 2>&1 &"'
    )
    remote(launch_cmd, timeout=10)

    # Wait for MCP port 13619 on behemoth (tunneled locally).
    deadline = time.time() + 60
    while time.time() < deadline:
        if remote('ss -ltn 2>/dev/null | grep -q 13619 && echo UP') == "UP":
            break
        time.sleep(2)
    else:
        raise RuntimeError("MCP port 13619 did not bind within 60s")

    # Give the wx UI a few more seconds to finish rendering.
    time.sleep(8)

    # Ensure tunnel is alive.
    tunnel_ok = subprocess.run(
        ["ss", "-ltn"], capture_output=True, text=True).stdout.find("13619") >= 0
    if not tunnel_ok:
        print("[P0] Re-establishing SSH tunnel 13619 → behemoth…")
        subprocess.run([
            "ssh", "-fN", "-L", "127.0.0.1:13619:127.0.0.1:13619",
            f"{BEHEMOTH_USER}@{BEHEMOTH_HOST}"], timeout=10)
        time.sleep(2)

    pid = remote('pgrep -f "orca-slicer --datadir" | head -1')
    print(f"[P0] Orca PID={pid}, MCP up, UI settled")
    return {"pid": pid, "launched": True}


def phase_profile(mcp: MCP, profile: str,
                  filament: str, print_name: str) -> dict:
    """Load printer / filament / print presets; confirm belt flag."""
    print(f"[P1] Loading profile '{profile}'…")
    for name in (profile, print_name, filament):
        try:
            mcp.call("config_load_profile", {"name": name}, timeout=20)
        except Exception as e:
            print(f"[P1][warn] config_load_profile '{name}' failed: {e}")

    cfg = mcp.call("config_get", {"keys": [
        "printer_structure", "printer_is_belt", "belt_angle",
        "belt_inclined_gcode", "enable_support", "layer_height",
        "printer_model"]})
    is_belt = cfg.get("printer_structure") == "belt" and \
              str(cfg.get("printer_is_belt")) in ("1", "True", "true")
    print(f"[P1] printer={cfg.get('printer_model')} "
          f"structure={cfg.get('printer_structure')} "
          f"is_belt={cfg.get('printer_is_belt')} "
          f"belt_angle={cfg.get('belt_angle')} "
          f"enable_support={cfg.get('enable_support')}")
    if not is_belt:
        raise RuntimeError("Active profile is NOT a belt printer")
    return cfg


def phase_clear_plate(mcp: MCP) -> None:
    """Remove all objects from the plate (the placeholder and any leftovers)."""
    print("[P1b] Clearing plate…")
    while True:
        try:
            r = mcp.call("model_list_objects")
            objs = r.get("objects", []) if isinstance(r, dict) else []
        except Exception:
            break
        if not objs:
            break
        idx = objs[0].get("index", 0)
        mcp.call("model_delete_object", {"index": idx})


def phase_load_and_place(mcp: MCP, mesh_path: str) -> dict:
    """Load mesh via MCP, position at keel (bed-min) keel-first (Y_min=0)."""
    print(f"[P2] Loading mesh: {mesh_path}")
    mcp.call("model_load_file", {"path": mesh_path}, timeout=60)
    # After our MCP load_file auto keel-align patch, the mesh already sits
    # at world (X=bed_center, Y_min=0, Z_min=0). Re-apply explicitly for
    # safety using pivot='bed-min' → places the bbox min corner at the
    # given world coords (we pick X at bed center, Y=0 keel, Z=0 surface).
    r = mcp.call("model_list_objects")
    objs = r.get("objects", [])
    if not objs:
        raise RuntimeError("No object loaded")
    idx = objs[0]["index"]

    # Query bed center X from full config (belt beds are long in Y).
    # Orca belt bed defaults to X[0, 250] → center 125.
    bed_x_center = 125.0

    print(f"[P2] Placing object via pivot='bed-min' translate=[{bed_x_center},0,0]")
    mcp.call("object_transform", {
        "index": idx,
        "pivot": "bed-min",
        "translate": [bed_x_center, 0.0, 0.0]})

    r = mcp.call("model_list_objects")
    bb = r["objects"][0]["bounding_box"]
    print(f"[P2] World bbox after placement: min={bb['min']} max={bb['max']}")
    return {"index": idx, "bbox": bb}


def phase_configure_supports(mcp: MCP, on: bool) -> None:
    """Set enable_support via config_set."""
    want = 1 if on else 0
    print(f"[P3] enable_support → {want}")
    try:
        mcp.call("config_set", {"settings": {"enable_support": want}})
    except Exception as e:
        print(f"[P3][warn] config_set failed: {e}")


def phase_prepare_view(mcp: MCP, outdir: Path, label: str) -> dict:
    """Switch to 3D tab, isometric camera, zoom_to_volumes, screenshot+describe."""
    print(f"[P4] Prepare view ({label})…")
    mcp.call("viewport_select_tab", {"tab": "3D"})
    time.sleep(0.3)
    mcp.call("viewport_select_view", {"view": "iso"})
    mcp.call("viewport_zoom_to_volumes")
    time.sleep(0.5)
    return _capture(mcp, outdir / f"prepare_{label}.png", label=f"prepare_{label}")


def phase_slice(mcp: MCP, timeout_s: int = 180) -> dict:
    """Trigger slice, wait for completion via slice_status."""
    print("[P5] slice_and_stats…")
    try:
        r = mcp.call("slice_and_stats", timeout=30)
        print(f"[P5] slice initiated: {r}")
    except MCPError as e:
        raise RuntimeError(f"slice_and_stats failed: {e}")

    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        try:
            s = mcp.call("slice_status", timeout=8)
        except Exception as e:
            # MCP may briefly become unresponsive during slicing — retry.
            time.sleep(3)
            continue
        if not isinstance(s, dict):
            time.sleep(2); continue
        last_status = s
        if s.get("finished"):
            print(f"[P5] slice finished: print_time={s.get('print_time')} "
                  f"filament_mm={s.get('filament_used_mm')}")
            return s
        time.sleep(3)
    raise RuntimeError(f"Slice did not finish within {timeout_s}s — last={last_status}")


def phase_preview_view(mcp: MCP, outdir: Path, layer_percent: int = 50,
                       label: str = "preview") -> dict:
    """Switch to Preview tab (critical — this is where the user reports crash),
    set layer slider to `layer_percent`, isometric + zoom, capture."""
    print(f"[P6] Switching to Preview tab (this is the reported crash site)…")
    # CRITICAL: if orca crashes here we want to know IMMEDIATELY
    pid_before = remote('pgrep -f "orca-slicer --datadir" | head -1')

    try:
        mcp.call("viewport_select_tab", {"tab": "Preview"}, timeout=15)
    except Exception as e:
        pid_after = remote('pgrep -f "orca-slicer --datadir" | head -1')
        if not pid_after:
            raise RuntimeError(f"Orca CRASHED on viewport_select_tab(Preview). "
                               f"pid_before={pid_before}, pid_after=GONE. "
                               f"MCP error: {e}")
        raise

    # Verify still alive after tab switch
    time.sleep(2)
    pid_after = remote('pgrep -f "orca-slicer --datadir" | head -1')
    if not pid_after or pid_after != pid_before:
        raise RuntimeError(f"Orca CRASHED after viewport_select_tab(Preview). "
                           f"pid_before={pid_before} pid_after={pid_after}")

    print(f"[P6] Preview tab active; setting layer to {layer_percent}%…")
    mcp.call("viewport_set_preview_layer", {"percent": layer_percent})
    mcp.call("viewport_select_view", {"view": "iso"})
    mcp.call("viewport_zoom_to_volumes")
    time.sleep(0.5)
    return _capture(mcp, outdir / f"{label}.png", label=label)


def phase_fetch_gcode(outdir: Path) -> Optional[str]:
    """Find newest gcode on behemoth, scp to outdir."""
    gc = remote(
        'find /tmp/orcaslicer_model -name "*.gcode" '
        '-printf "%T@ %p\\n" 2>/dev/null | sort -n | tail -1 | cut -d" " -f2-')
    if not gc:
        print("[P7] No gcode found")
        return None
    local = outdir / "slice.gcode"
    ok = remote_fetch(gc, str(local))
    if not ok:
        # path may contain # — try quoted
        ok = remote_fetch(f"'{gc}'", str(local))
    if ok and local.exists():
        print(f"[P7] Gcode fetched: {local} ({local.stat().st_size} bytes)")
        return str(local)
    print(f"[P7] scp failed for {gc}")
    return None


def phase_gate(gcode_path: str) -> dict:
    """Run belt_gcode_gate.py; parse the summary."""
    print(f"[P8] Running belt_gcode_gate.py on {gcode_path}")
    gate = Path(__file__).parent / "belt_gcode_gate.py"
    r = subprocess.run(
        ["python3", str(gate), gcode_path],
        capture_output=True, text=True, timeout=60)
    out = r.stdout
    # Parse result line
    verdict = "?"
    for line in out.splitlines():
        if line.strip().startswith("RESULT:"):
            verdict = line.strip().replace("RESULT:", "").strip()
            break
    # Count PASS/WARN/FAIL
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for line in out.splitlines():
        s = line.strip()
        for k in counts:
            if s.startswith(k) or f"  {k}  [" in line:
                counts[k] += 1
                break
    print(f"[P8] Gate verdict: {verdict} — {counts}")
    return {"verdict": verdict, "counts": counts, "stdout": out}


# ── Capture helper ────────────────────────────────────────────────────────

def _capture(mcp: MCP, path: Path, label: str = "") -> dict:
    """Screenshot via MCP (viewport mode) + fallback to full-screen scrot,
    then describe via SauronsEye. Returns {path, size, description}."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ok_mcp = False
    try:
        shot = mcp.call("screenshot", {"mode": "viewport"}, timeout=20)
        if isinstance(shot, dict) and "__image_b64__" in shot:
            import base64
            png = base64.b64decode(shot["__image_b64__"])
            path.write_bytes(png)
            ok_mcp = path.stat().st_size > 2000  # MCP often returns blank
    except Exception as e:
        print(f"[cap][warn] MCP screenshot failed: {e}")

    if not ok_mcp:
        # Fallback: grab the main Orca window via remote `import -window root`.
        # Covers case where the MCP screenshot returns an empty viewport.
        print(f"[cap] MCP shot empty/failed, falling back to server-side screencap")
        tmp = f"/tmp/cap_{int(time.time()*1000)}.png"
        remote(f'DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority '
               f'import -window root {tmp} 2>/dev/null', timeout=15)
        if remote_fetch(tmp, str(path)):
            remote(f'rm -f {tmp}')
        else:
            print(f"[cap][err] fallback screenshot failed")
            return {"path": str(path), "error": "capture_failed"}

    sz = path.stat().st_size if path.exists() else 0
    desc = sauron_describe(str(path)) if sz > 0 else {}
    warns = desc.get("warnings_or_errors", [])
    panels = desc.get("visible_panels", [])
    print(f"[cap] {label}: {sz}B panels={panels} warnings={warns}")
    return {"path": str(path), "size": sz, "description": desc}


# ── Runner ────────────────────────────────────────────────────────────────

def run(args):
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    report: dict = {"args": vars(args), "steps": [], "status": "?"}

    try:
        if not args.skip_launch:
            report["launch"] = phase_launch(outdir)
        mcp = MCP()

        # Profile
        report["profile"] = phase_profile(mcp, args.profile,
                                          args.filament, args.print_preset)
        # Clear plate (remove placeholder)
        phase_clear_plate(mcp)

        # Place target mesh
        report["object"] = phase_load_and_place(mcp, args.mesh)

        # Supports config
        phase_configure_supports(mcp, args.supports)
        report["supports"] = args.supports

        # Prepare screenshot (before slice)
        report["prepare_shot"] = phase_prepare_view(mcp, outdir, "before")

        # Slice
        report["slice_stats"] = phase_slice(mcp, timeout_s=args.slice_timeout)

        # Preview tab — critical check for reported crash
        report["preview_shot"] = phase_preview_view(mcp, outdir,
                                                    layer_percent=50,
                                                    label=f"preview_50pct")

        # Fetch gcode
        gc = phase_fetch_gcode(outdir)
        report["gcode_path"] = gc

        # Gate
        if gc:
            report["gate"] = phase_gate(gc)

        # Pass criteria: gate produced a verdict, no crash.
        gate_verdict = report.get("gate", {}).get("verdict", "")
        if "BLOCKED" in gate_verdict.upper():
            report["status"] = "FAIL_GATE_BLOCKED"
        elif gate_verdict == "?":
            report["status"] = "FAIL_NO_GATE"
        else:
            report["status"] = "OK"

    except Exception as e:
        import traceback
        report["status"] = "ERROR"
        report["error"] = str(e)
        report["traceback"] = traceback.format_exc()
        print(f"\n[ERROR] {e}\n{traceback.format_exc()}")

    # Save report
    (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"\n=== FINAL STATUS: {report['status']} ===")
    print(f"Report: {outdir / 'report.json'}")
    if not args.keep_running:
        print("[cleanup] killing orca-slicer on behemoth…")
        remote('pkill -9 -f "orca-slicer --datadir" 2>/dev/null')
    return 0 if report["status"] == "OK" else 1


def main():
    ap = argparse.ArgumentParser(
        description="Belt GUI end-to-end validator (MCP + SauronsEye)")
    ap.add_argument("--mesh", default=DEFAULT_MESH,
                    help="Absolute path (on behemoth) to the STL/3MF under test")
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--filament", default=DEFAULT_FILAMENT)
    ap.add_argument("--print-preset", default=DEFAULT_PRINT)
    ap.add_argument("--supports", action="store_true",
                    help="Enable supports (enable_support=1) before slicing")
    ap.add_argument("--slice-timeout", type=int, default=180,
                    help="Seconds to wait for slice_status to report finished")
    ap.add_argument("--output-dir", default="/tmp/belt_val",
                    help="Local directory for screenshots, report.json, gcode")
    ap.add_argument("--skip-launch", action="store_true",
                    help="Assume orca-belt is already running on behemoth")
    ap.add_argument("--keep-running", action="store_true",
                    help="Don't kill orca-belt on behemoth at the end")
    args = ap.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
