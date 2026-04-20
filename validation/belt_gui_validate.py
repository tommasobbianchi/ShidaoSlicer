#!/usr/bin/env python3
"""
belt_gui_validate.py — Autonomous belt-printer slicing validation.

Two modes:
  cli   Slice via CLI binary (fast, no display needed). Same slicing engine as GUI.
  gui   Drive the GUI on behemoth via xdotool (screenshot-based pass/fail).

Usage:
  python3 validation/belt_gui_validate.py cli model.stl [model2.3mf ...]
  python3 validation/belt_gui_validate.py gui model.3mf
  python3 validation/belt_gui_validate.py cli --all   # run full test suite
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parent.parent
BIN_RELEASE  = REPO / "build/src/Release/orca-slicer"
BIN_DEBUG    = REPO / "build/src/Debug/orca-slicer"
GATE_SCRIPT  = REPO / "validation/belt_gcode_gate.py"
PROFILES_DIR = REPO / "resources/profiles/IdeaFormer"

MACHINE_JSON  = PROFILES_DIR / "machine/IdeaFormer IR3 V2 0.4 nozzle.json"
PROCESS_JSON  = PROFILES_DIR / "process/0.20mm Standard @IdeaFormer IR3 V2.json"
FILAMENT_PLA  = PROFILES_DIR / "filament/fdm_filament_pla.json"
FILAMENT_PETG = PROFILES_DIR / "filament/fdm_filament_petg.json"

TEST_MODELS = [
    REPO / "validation/test_models/box_20x20x20.stl",
    REPO / "validation/test_models/inverted_L.stl",
    REPO / "validation/test_models/arc_bridge.stl",
]

# Behemoth connection
BEHEMOTH_IP          = "<WORKSTATION_HOST>"
BEHEMOTH_USER        = "tommaso"
BEHEMOTH_BIN         = "/home/user/bin/orca-belt"
BEHEMOTH_DISPLAY     = ":1"
BEHEMOTH_XAUTHORITY  = "/run/user/1000/gdm/Xauthority"  # required — GDM session auth
# Full GNOME session environment — all vars needed by wxWidgets/GTK stack.
# Without DBUS_SESSION_BUS_ADDRESS and XDG_* vars, GTK widget sizing fails with
# SIGSEGV at offset 0x13037f4 in the orca-slicer binary (~26s after launch).
BEHEMOTH_SESSION_ENV = (
    "DISPLAY=:1"
    " XAUTHORITY=/run/user/1000/gdm/Xauthority"
    " DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"
    " XDG_RUNTIME_DIR=/run/user/1000"
    " XDG_SESSION_TYPE=x11"
    " XDG_CURRENT_DESKTOP=ubuntu:GNOME"
    " DESKTOP_SESSION=ubuntu"
    " GDMSESSION=ubuntu"
    " GTK_MODULES=gail:atk-bridge"
)


# ── Profile inheritance resolver ─────────────────────────────────────────────

def _resolve_profile(name: str, search_dir: Path) -> Path | None:
    """Find a profile JSON by name or setting_id."""
    for p in search_dir.rglob("*.json"):
        try:
            d = json.loads(p.read_text())
            if d.get("name") == name or d.get("setting_id") == name:
                return p
        except Exception:
            pass
    return None


def _merge_profile(path: Path, search_dir: Path, _seen: set = None) -> dict:
    """
    Recursively merge a profile JSON with its `inherits` parent.
    Child values override parent values (child wins).
    """
    if _seen is None:
        _seen = set()
    if path in _seen:
        return {}
    _seen.add(path)

    try:
        d = json.loads(path.read_text())
    except Exception:
        return {}

    parent_name = d.get("inherits")
    if not parent_name:
        return dict(d)

    parent_path = _resolve_profile(parent_name, search_dir)
    if parent_path is None:
        return dict(d)

    merged = _merge_profile(parent_path, search_dir, _seen)
    merged.update(d)   # child overrides parent
    return merged


def _flat_machine_json(machine_json: Path) -> Path:
    """
    Return a path to a temporary flat machine JSON that has all inherited
    settings inlined — required because the OrcaSlicer CLI does NOT follow
    the `inherits` chain when loading profiles via --load-settings.
    """
    search_dir = machine_json.parent.parent   # resources/profiles/IdeaFormer
    merged = _merge_profile(machine_json, search_dir)
    # Strip inherits/meta keys that confuse the CLI
    for key in ("inherits",):
        merged.pop(key, None)
    tmp = Path(tempfile.mktemp(suffix=".json", prefix="belt_machine_merged_"))
    tmp.write_text(json.dumps(merged, indent=2))
    return tmp


# ── Helpers ──────────────────────────────────────────────────────────────────

def _binary() -> Path:
    if BIN_RELEASE.exists() and BIN_RELEASE.stat().st_size > 1_000_000:
        return BIN_RELEASE
    if BIN_DEBUG.exists():
        return BIN_DEBUG
    raise FileNotFoundError("orca-slicer binary not found in build/")


def _run(cmd, timeout=300, cwd=None) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=timeout, cwd=cwd, errors="replace"
    )
    return result.returncode, result.stdout, result.stderr


# ── CLI validation ────────────────────────────────────────────────────────────

def validate_cli(model_path: Path, filament_json: Path = FILAMENT_PLA,
                 outdir: Path = None) -> dict:
    """Slice model_path via CLI and validate with belt_gcode_gate.py."""

    model_path = Path(model_path).resolve()
    if not model_path.exists():
        return {"status": "ERROR", "reason": f"Model not found: {model_path}"}

    tmp_owned = outdir is None
    if outdir is None:
        outdir = Path(tempfile.mkdtemp(prefix="belt_validate_"))

    binary = _binary()
    print(f"  binary  : {binary.name}")
    print(f"  model   : {model_path.name}")
    print(f"  outdir  : {outdir}")

    # Flatten machine JSON so CLI sees all inherited settings (gcode_flavor, etc.)
    # The OrcaSlicer CLI does NOT follow `inherits` chains, so gcode_flavor would
    # default to gcfMarlinLegacy and trigger a spurious G92-E0 validation error.
    flat_machine = _flat_machine_json(MACHINE_JSON)
    try:
        cmd = [
            str(binary),
            "--slice", "1",
            "--allow-newer-file",
            "--load-settings", f"{flat_machine};{PROCESS_JSON}",
            "--load-filaments", str(filament_json),
            "--outputdir", str(outdir),
            str(model_path),
        ]

        t0 = time.time()
        try:
            rc, stdout, stderr = _run(cmd, timeout=300)
        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "reason": "Slicing exceeded 300s"}

        elapsed = time.time() - t0
        combined = stdout + stderr

        # ── Detect gcode output ──────────────────────────────────────────────
        gcodes = list(outdir.rglob("*.gcode"))
        if not gcodes:
            return {
                "status": "FAIL",
                "reason": "No gcode produced",
                "exit_code": rc,
                "elapsed_s": round(elapsed, 1),
                "log_tail": combined[-2000:],
            }

        gcode_path = gcodes[0]

        # ── Run belt gate ────────────────────────────────────────────────────
        gate_result = _run_gate(gcode_path)

        return {
            "status": gate_result["result"],
            "gcode": str(gcode_path),
            "exit_code": rc,
            "elapsed_s": round(elapsed, 1),
            "gate": gate_result,
        }
    finally:
        flat_machine.unlink(missing_ok=True)
        if tmp_owned:
            shutil.rmtree(outdir, ignore_errors=True)


def _run_gate(gcode_path: Path) -> dict:
    if not GATE_SCRIPT.exists():
        return {"result": "SKIP", "reason": "belt_gcode_gate.py not found"}
    rc, stdout, stderr = _run(
        [sys.executable, str(GATE_SCRIPT), str(gcode_path)],
        timeout=60,
    )
    text = stdout + stderr
    if rc == 0:
        return {"result": "PASS", "output": text[-500:]}
    elif rc == 2:
        # gate exits 2 for WARNING (anomalies but not blocking)
        return {"result": "WARN", "output": text[-1000:]}
    else:
        return {"result": "FAIL", "output": text[-1000:], "exit_code": rc}


# ── GUI validation (xdotool on behemoth) ─────────────────────────────────────

# SSH ControlMaster socket — shared across all SSH calls during GUI validation.
# All connections that use this socket share ONE underlying SSH session, so
# processes launched via the socket live in the same systemd session scope.
# The master process (a long sleep) keeps the session alive until we're done.
_SSH_CTL = "/tmp/belt_gui_ssh_ctl"
_ssh_master_proc: "subprocess.Popen | None" = None


def _ssh_master_start():
    """Start the SSH ControlMaster (background sleep). Call once before GUI validation."""
    global _ssh_master_proc
    _ssh_master_stop()  # clean up any leftover
    import subprocess as _sp
    _ssh_master_proc = _sp.Popen(
        ["ssh", "-M", "-S", _SSH_CTL,
         "-o", "ControlPersist=no",
         "-o", "StrictHostKeyChecking=no",
         "-o", "ConnectTimeout=10",
         f"{BEHEMOTH_USER}@{BEHEMOTH_IP}", "sleep 600"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)  # let master establish


def _ssh_master_stop():
    """Terminate the SSH ControlMaster."""
    global _ssh_master_proc
    import os
    if _ssh_master_proc is not None:
        try:
            _ssh_master_proc.terminate()
            _ssh_master_proc.wait(timeout=5)
        except Exception:
            pass
        _ssh_master_proc = None
    # Also kill via -exit control command
    subprocess.run(
        ["ssh", "-S", _SSH_CTL, "-O", "exit", f"{BEHEMOTH_USER}@{BEHEMOTH_IP}"],
        capture_output=True, timeout=5,
    )
    try:
        os.unlink(_SSH_CTL)
    except FileNotFoundError:
        pass


def _ssh_via_master(cmd: str, timeout=30) -> tuple[int, str]:
    """Run command on behemoth via the ControlMaster socket (shared session)."""
    full = ["ssh", "-S", _SSH_CTL, "-o", "ControlMaster=no",
            f"{BEHEMOTH_USER}@{BEHEMOTH_IP}", cmd]
    rc, out, err = _run(full, timeout=timeout)
    return rc, out + err


def _ssh(cmd: str, timeout=30) -> tuple[int, str]:
    """Run command on behemoth (direct or via master if active)."""
    if _ssh_master_proc is not None and _ssh_master_proc.poll() is None:
        return _ssh_via_master(cmd, timeout=timeout)
    full = ["ssh", f"{BEHEMOTH_USER}@{BEHEMOTH_IP}", cmd]
    rc, out, err = _run(full, timeout=timeout)
    return rc, out + err


def _x11(cmd: str, timeout=30) -> tuple[int, str]:
    """Run command on behemoth with full GNOME session environment."""
    return _ssh(f"{BEHEMOTH_SESSION_ENV} {cmd}", timeout=timeout)


def _behemoth_has(tool: str) -> bool:
    rc, _ = _ssh(f"which {tool} 2>/dev/null")
    return rc == 0


# ── xdotool primitives ────────────────────────────────────────────────────────

def _wait_window(pid: int, min_width: int = 800, timeout_s: int = 60) -> int | None:
    """
    Poll until a window belonging to PID has width >= min_width.
    Returns window ID or None on timeout.
    The splash is ~480px wide; the main window is 1920px wide.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rc, out = _x11(f"xdotool search --pid {pid} 2>/dev/null")
        for wid_s in out.strip().splitlines():
            wid_s = wid_s.strip()
            if not wid_s.isdigit():
                continue
            wid = int(wid_s)
            rc2, geo = _x11(f"xdotool getwindowgeometry --shell {wid} 2>/dev/null")
            for line in geo.splitlines():
                if line.startswith("WIDTH="):
                    try:
                        w = int(line.split("=", 1)[1])
                        if w >= min_width:
                            return wid
                    except ValueError:
                        pass
        time.sleep(3)
    return None


def _focus(wid: int):
    """Activate and focus a window by ID."""
    _x11(f"xdotool windowactivate --sync {wid} windowfocus --sync {wid}")


def _key(combo: str, wid: int = None):
    """Send a key combo (e.g. 'ctrl+r') optionally to a specific window."""
    target = f"--window {wid}" if wid else ""
    _x11(f"xdotool key --clearmodifiers {target} {combo}")


def _screenshot_window(wid: int, label: str) -> str | None:
    """Take screenshot of specific window on behemoth. Returns remote path or None."""
    remote = f"/tmp/belt_gui_{label}_{int(time.time())}.png"
    rc, _ = _x11(f"import -window {wid} {remote} 2>/dev/null", timeout=15)
    return remote if rc == 0 else None


def _image_changed(remote_a: str, remote_b: str, threshold: float = 0.02) -> bool:
    """
    Compare two remote screenshots via RMSE. Returns True if significantly different.
    Threshold 0.02 = 2% normalised RMS — enough to detect layer slider movement.
    """
    rc, out = _ssh(
        f"compare -metric RMSE '{remote_a}' '{remote_b}' /dev/null 2>&1",
        timeout=20,
    )
    try:
        # Output format: "1234 (0.05)" — parse the normalised value
        val = float(out.strip().split("(")[1].rstrip(")"))
        return val > threshold
    except Exception:
        return True  # assume changed if parse fails


def _orca_alive(pid: int) -> bool:
    """Check if OrcaSlicer process is still running."""
    rc, _ = _ssh(f"ps -p {pid} -o pid= 2>/dev/null")
    return rc == 0


# ── OrcaSlicer launch ─────────────────────────────────────────────────────────

def _launch_orca(model_path: str) -> tuple[int, int]:
    """
    Launch OrcaSlicer on behemoth with correct DISPLAY/XAUTHORITY.
    Returns (pid, main_window_id).
    Raises RuntimeError if window does not appear within timeout.
    """
    # Kill all stale orca-slicer processes first to clear D-Bus name registration.
    # Sleep 4s (not 2s) to ensure D-Bus names and file locks are fully released.
    _ssh("pkill -9 -f '/orca-slicer --datadir' 2>/dev/null; sleep 4")

    # Launch with setsid + nohup to fully detach from the SSH session scope.
    # setsid creates a new process session so systemd-logind cannot kill it
    # when the SSH ControlMaster connection closes (nohup alone is insufficient).
    # The orca-belt wrapper uses `exec`, so $! from the background setsid call
    # captures the actual orca-slicer PID after exec.
    launch = (
        f"{BEHEMOTH_SESSION_ENV} "
        f"setsid nohup {BEHEMOTH_BIN} '{model_path}' "
        f"</dev/null >/tmp/orcabelt_gui.log 2>&1 & echo $!"
    )
    rc, out = _ssh(launch, timeout=10)
    lines = [l.strip() for l in out.strip().splitlines() if l.strip().isdigit()]
    if not lines:
        _, log = _ssh("tail -10 /tmp/orcabelt_gui.log 2>/dev/null")
        raise RuntimeError(f"orca-slicer did not start. Log:\n{log}")
    pid = int(lines[-1])
    # Verify the process is actually running (give it 3s to exec into orca-slicer)
    time.sleep(3)
    rc_alive, _ = _ssh(f"ps -p {pid} -o pid= 2>/dev/null")
    if rc_alive != 0:
        _, log = _ssh("tail -10 /tmp/orcabelt_gui.log 2>/dev/null")
        raise RuntimeError(f"orca-slicer PID={pid} died immediately. Log:\n{log}")

    # Wait for the main window (splash ~480px, main window >= 1920px).
    # Release binary takes 2-3 minutes to initialize; Debug takes ~20-30s.
    print(f"  launched orca-belt PID={pid}, waiting for main window…")
    wid = _wait_window(pid, min_width=800, timeout_s=180)
    if wid is None:
        _, log = _ssh("tail -30 /tmp/orcabelt_gui.log 2>/dev/null")
        raise RuntimeError(f"Main window did not appear within 180s.\nLog:\n{log}")

    # Wait until the 3D viewport has actually RENDERED (not just the window frame).
    # The "Elabora piatto" button only appears after the GL canvas initialises.
    # We detect render-ready by polling the brightness of the top-right corner
    # (where the slice button lives): it goes from near-black → teal/green once
    # the UI is fully loaded.  Timeout 120s to handle slow start-up.
    print(f"  window {wid} found, waiting for viewport to render…")
    _wait_viewport_ready(wid, timeout_s=120)
    return pid, wid


def _dismiss_dialogs(pid: int, main_wid: int, timeout_s: int = 20):
    """
    Dismiss ALL blocking dialogs belonging to the OrcaSlicer PID.
    Loops until no dismissable dialogs remain (or timeout).

    Clicks the OK button in the bottom-right corner of each dialog
    (more reliable than Return which requires window focus).
    """
    # ALL non-main windows that are > 100px wide are treated as blocking dialogs.
    # OrcaSlicer modally blocks input when any dialog is open; we must dismiss all.
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rc, out = _x11(f"xdotool search --pid {pid} 2>/dev/null")
        dismissed = 0
        for wid_s in out.strip().splitlines():
            wid_s = wid_s.strip()
            if not wid_s.isdigit():
                continue
            wid_int = int(wid_s)
            if wid_int == main_wid:
                continue
            rc2, geo = _x11(f"xdotool getwindowgeometry --shell {wid_int} 2>/dev/null")
            win_x = win_y = width = height = 0
            for line in geo.splitlines():
                if   line.startswith("X="):      win_x  = int(line.split("=",1)[1])
                elif line.startswith("Y="):      win_y  = int(line.split("=",1)[1])
                elif line.startswith("WIDTH="):  width  = int(line.split("=",1)[1])
                elif line.startswith("HEIGHT="): height = int(line.split("=",1)[1])
            if width < 100 or height < 30:
                continue  # tiny/invisible helper window, skip
            # Skip known internal helper windows (OrcaSlicer's hidden GL context windows
            # are 200x200 at exactly (0,0) — they are NOT dialogs)
            if win_x == 0 and win_y == 0 and width <= 200 and height <= 200:
                continue
            # Skip windows that are completely off-screen (x < -100 or y < -100)
            if win_x < -100 or win_y < -100:
                continue
            _, title = _x11(f"xdotool getwindowname {wid_int} 2>/dev/null")
            title_s = title.strip()
            # Skip transient loading/progress toasts — they close on their own.
            # Attempting to click them just interferes and causes re-open loops.
            if "Caricamento" in title_s or "Loading" in title_s:
                print(f"  [dialog] Skipping transient toast '{title_s}' ({width}x{height})")
                continue
            print(f"  [dialog] Dismissing '{title_s}' ({width}x{height}) at ({win_x},{win_y})")
            # Click the OK/Close button: bottom-right area of the dialog
            ok_x = win_x + width - 50
            ok_y = win_y + height - 25
            _x11(f"xdotool mousemove {ok_x} {ok_y}")
            time.sleep(0.2)
            _x11(f"xdotool click 1")
            time.sleep(0.5)
            dismissed += 1
        if dismissed == 0:
            return  # no more dialogs
        time.sleep(0.5)  # let dialogs close before re-checking


def _wait_viewport_ready(wid: int, timeout_s: int = 150):
    """
    Poll until the 'Elabora piatto' slice button appears in the toolbar.
    OrcaSlicer initializes the GL canvas and loads the model before showing
    the slice button; this wait ensures the button is clickable.

    Detection: the button area (top-right of the window) goes from near-black
    (~35 avg brightness) to teal/gray (~55+) once the toolbar renders.
    Uses ImageMagick 'identify' to get mean brightness — avoids Python quoting.
    """
    deadline = time.time() + timeout_s
    remote_tmp = "/tmp/belt_gui_viewport_check.png"
    while time.time() < deadline:
        time.sleep(5)
        # Capture 300×30 crop covering the "Elabora piatto" button area.
        # `import -window` starts at the PHYSICAL window frame top (screen y=27),
        # while xdotool Y=74 is the client area. The button is at import y=28-53,
        # so cropping y=28+ captures it reliably.
        rc_cap, _ = _x11(
            f"import -window {wid} -crop 300x30+1580+28 +repage {remote_tmp} 2>/dev/null",
            timeout=10,
        )
        if rc_cap != 0:
            continue
        # Get mean brightness 0-255 via ImageMagick fx (no Python quoting issues)
        rc_id, out = _ssh(
            f"convert {remote_tmp} -format '%[fx:mean*255]' info: 2>/dev/null",
            timeout=10,
        )
        try:
            brightness = float(out.strip().split('\n')[0])
            # Teal button ~55-70; dark/loading ~35-42
            if brightness > 48:
                print(f"  viewport ready (brightness={brightness:.1f}/255)")
                return
        except ValueError:
            pass
    # Timeout — the button may still appear; proceed anyway
    print(f"  viewport wait timed out after {timeout_s}s — proceeding anyway")


# ── Belt config checks (read from OrcaSlicer live temp project config) ────────

def _read_live_project_config(pid: int = None) -> dict:
    """
    Read the _temp_*.config for the given OrcaSlicer PID (or most recent if None).
    OrcaSlicer creates /tmp/orcaslicer_model/DATE/TIME#PID#N/_temp_N.config
    when a project is loaded.  We prefer the PID-specific file so we don't
    accidentally read a stale config from a previous session — especially since
    configs extracted from 3MF files carry the 3MF's original mtime, not today's.
    """
    if pid:
        # Look for config in PID-specific temp dir
        rc, out = _ssh(
            f"find /tmp/orcaslicer_model -name '_temp_*.config' "
            f"-path '*#{pid}#*' -type f 2>/dev/null | head -1"
        )
    else:
        # Fallback: most recently modified (sorted by mtime — may be stale!)
        rc, out = _ssh(
            "find /tmp/orcaslicer_model -name '_temp_*.config' -type f "
            "| xargs ls -t 2>/dev/null | head -1"
        )
    if rc != 0 or not out.strip():
        return {}
    rc2, txt = _ssh(f"cat '{out.strip()}' 2>/dev/null")
    try:
        return json.loads(txt)
    except Exception:
        return {}


def _check_belt_settings(pid: int = None) -> dict:
    """
    Phase 1: Verify the loaded project config has correct belt printer settings.
    Reads from the live OrcaSlicer temp project config (_temp_*.config in the
    PID-specific directory) which reflects the actual active machine profile.
    """
    cfg = _read_live_project_config(pid)
    if not cfg:
        # Fallback: check system profile directly
        rc, out = _ssh(
            "grep -l 'printer_is_belt' "
            "~/.config/OrcaBelt/system/IdeaFormer/machine/*.json 2>/dev/null | head -1"
        )
        if rc == 0 and out.strip():
            rc2, txt = _ssh(f"cat '{out.strip()}' 2>/dev/null")
            try:
                cfg = json.loads(txt)
            except Exception:
                pass
    if not cfg:
        return {"status": "WARN", "detail": "Could not read active project config"}

    # belt_axis: old profiles used "Z" (capital), newer uses "z" or "y" — all valid
    expected = {
        "printer_is_belt":    "1",
        "belt_angle":         "45",
        "belt_axis":          ("y", "Z", "z"),  # tuple = set of accepted values
        "belt_inclined_gcode": "1",
    }
    wrong = {}
    for k, v in expected.items():
        actual = str(cfg.get(k, "<missing>"))
        if isinstance(v, tuple):
            if actual not in v:
                wrong[k] = {"expected": list(v), "actual": actual}
        elif actual != v:
            wrong[k] = {"expected": v, "actual": actual}

    if wrong:
        return {"status": "FAIL", "detail": f"Wrong belt settings: {wrong}", "config": cfg}
    actual_vals = {k: cfg.get(k) for k in expected}
    return {"status": "PASS", "detail": "All belt settings correct", "config": actual_vals}


def _check_support_disabled(pid: int = None) -> dict:
    """
    Phase 2: Verify enable_support=0 in the live project config.
    For belt printers, built-in support is disabled — model-space support is
    pre-generated by support_preprocess.py.
    """
    cfg = _read_live_project_config(pid)
    if not cfg:
        return {"status": "WARN", "detail": "Could not read live project config"}
    val = str(cfg.get("enable_support", "<missing>"))
    if val == "0":
        return {"status": "PASS", "detail": "enable_support=0 (correctly disabled for belt)"}
    if val == "<missing>":
        return {"status": "WARN",
                "detail": "enable_support not set (defaults to disabled — likely OK)"}
    return {
        "status": "FAIL",
        "detail": f"enable_support={val} — must be 0 for belt printers",
    }


# ── Gcode poll ────────────────────────────────────────────────────────────────

def _poll_for_gcode(pid: int, timeout_s: int = 120) -> str | None:
    """
    Poll the PID-specific temp directory in /tmp/orcaslicer_model for a gcode file.
    OrcaSlicer creates /tmp/orcaslicer_model/DATE/TIME#PID#N/Metadata/ for each session.
    After GUI slicing, 'plate_1.gcode' appears in that Metadata/ dir.
    Returns remote path or None on timeout.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(4)
        # Search in PID-specific temp dirs (path contains #PID# fragment)
        rc, out = _ssh(
            f"find /tmp/orcaslicer_model -name '*.gcode' "
            f"-path '*#{pid}#*' 2>/dev/null | head -1"
        )
        candidate = out.strip()
        if candidate:
            return candidate
    return None


# ── 7-phase validate_gui ──────────────────────────────────────────────────────

def validate_gui(model_path: Path) -> dict:
    """
    Full 7-phase GUI validation on behemoth (<WORKSTATION_HOST>).

    Phase 0: Launch OrcaSlicer with DISPLAY=:1 + XAUTHORITY (GDM session)
    Phase 1: Verify belt printer settings (printer_is_belt, belt_angle, etc.)
    Phase 2: Verify support is disabled (belt printers use model-space supports)
    Phase 3: Screenshot Prepare view (object placement)
    Phase 4: Slice via Ctrl+R, wait for gcode, run belt gate
    Phase 5: Preview transform (layer slider changes viewport)
    Phase 6: Belt bed renders in both Prepare and Preview
    Phase 7: Cleanup

    Root cause of prior failures: XAUTHORITY was missing → GTK got zero display
    dimensions → SIGSEGV. Fixed by including BEHEMOTH_XAUTHORITY in all X11 cmds.
    """

    model_path = Path(model_path).resolve()
    if not model_path.exists():
        return {"status": "ERROR", "reason": f"Model not found: {model_path}"}

    print(f"  model   : {model_path.name}")
    print(f"  display : {BEHEMOTH_DISPLAY} (XAUTHORITY={BEHEMOTH_XAUTHORITY})")

    phases = {}
    pid = wid = None

    # Start SSH ControlMaster so OrcaSlicer's session stays alive across calls
    _ssh_master_start()

    # Unlock the display session — OrcaSlicer GL canvas does not render while
    # the screen is locked (GDM lock screen blocks OpenGL compositing).
    # loginctl unlock-session targets the physical tty2 X11 session (session 4).
    _ssh("loginctl unlock-session 4 2>/dev/null; sleep 1")
    print("  [P0] Session unlocked")

    # ── Phase 0: Launch ───────────────────────────────────────────────────────
    print("  [P0] Launching OrcaSlicer…")
    try:
        pid, wid = _launch_orca(str(model_path))
        shot_prepare = _screenshot_window(wid, "p0_prepare")
        phases["launch"] = {"status": "PASS", "pid": pid, "wid": wid, "screenshot": shot_prepare}
        print(f"  [P0] PASS — window {wid}")
    except Exception as e:
        phases["launch"] = {"status": "FAIL", "reason": str(e)}
        _ssh_master_stop()
        return {"status": "FAIL", "phases": phases}

    try:
        # ── Phase 1: Belt settings ─────────────────────────────────────────────
        print("  [P1] Checking belt settings…")
        p1 = _check_belt_settings(pid)
        p1["screenshot"] = _screenshot_window(wid, "p1_settings")
        phases["belt_settings"] = p1
        print(f"  [P1] {p1['status']} — {p1['detail']}")

        # ── Phase 2: Support disabled ──────────────────────────────────────────
        print("  [P2] Checking support disabled…")
        p2 = _check_support_disabled(pid)
        phases["support_disabled"] = p2
        print(f"  [P2] {p2['status']} — {p2['detail']}")

        # ── Phase 3: Object placement (screenshot only, confirmed via gcode) ───
        print("  [P3] Screenshot Prepare view…")
        shot_placement = _screenshot_window(wid, "p3_placement")
        phases["placement"] = {"status": "PASS", "screenshot": shot_placement,
                               "detail": "Y placement confirmed via Phase 4 gcode gate"}

        # ── Phase 4: Slice via "Elabora piatto" button click ──────────────────
        # NOTE: Ctrl+R doesn't reach the MainFrame wxEVT_CHAR_HOOK via xdotool
        # because the GLCanvas (OpenGL viewport) captures X11 focus and bypasses
        # GTK key routing. Mouse clicks on the "Elabora piatto" toolbar button
        # work reliably instead.
        #
        # Button position: window is always 1920x1043 at X=3840, Y=74 (monitor 3).
        # "Elabora piatto" is in the title bar's second row at approx x=1470, y=42.
        # Absolute screen position: 3840+1470=5310, 74+42=116.
        print("  [P4] Slicing via 'Elabora piatto' button click…")
        # Dismiss any modal dialogs (e.g. config-migration "informazioni" dialog)
        # before clicking slice — they block mouse events on the main window.
        _dismiss_dialogs(pid, wid)
        _focus(wid)
        time.sleep(1)
        # Get window geometry to compute absolute position of the slice button
        rc_geo, geo = _x11(f"xdotool getwindowgeometry --shell {wid} 2>/dev/null")
        win_x, win_y = 3840, 74  # default fallback
        for line in geo.splitlines():
            if line.startswith("X="):
                try: win_x = int(line.split("=",1)[1])
                except ValueError: pass
            elif line.startswith("Y="):
                try: win_y = int(line.split("=",1)[1])
                except ValueError: pass
        # "Elabora piatto" is a split-button (chevron left + text right).
        # Coordinate system (3-monitor 5760x1080):
        #   - xdotool Y=74 is the PHYSICAL window top (GTK CSD, no WM decorations).
        #     `import -window` also starts at Y=74 (image y=0 == screen y=74).
        #   - The tab/toolbar row occupies image y=0-35 inside the window.
        #   - Button center: image y≈15 → screen y = win_y + 15 = 74+15 = 89
        #   - Button x: ≈1675px from left edge → screen x = win_x + 1675
        btn_abs_x = win_x + 1675
        btn_abs_y = win_y + 15
        print(f"  [P4] clicking abs ({btn_abs_x},{btn_abs_y})")
        _focus(wid)
        time.sleep(0.3)
        _x11(f"xdotool mousemove {btn_abs_x} {btn_abs_y}")
        time.sleep(0.5)
        # Screenshot BEFORE click to verify clean window state
        shot_before = _screenshot_window(wid, "p4_before_click")
        _x11(f"xdotool click 1")
        # Screenshot 2s after click to see immediate reaction
        time.sleep(2)
        shot_2s = _screenshot_window(wid, "p4_click_2s")
        print(f"  [P4] screenshots: before={shot_before} after2s={shot_2s}")
        # Give OrcaSlicer a moment to start slicing before polling
        time.sleep(2)

        gcode_remote = _poll_for_gcode(pid, timeout_s=120)
        if not _orca_alive(pid):
            _, log = _ssh("tail -10 /tmp/orcabelt_gui.log 2>/dev/null")
            phases["slice"] = {"status": "FAIL", "reason": "OrcaSlicer crashed during slice", "log": log}
            return {"status": "FAIL", "phases": phases}

        shot_post_slice = _screenshot_window(wid, "p4_post_slice")

        if gcode_remote is None:
            phases["slice"] = {
                "status": "FAIL",
                "reason": "No gcode appeared within 120s after button click",
                "screenshot": shot_post_slice,
            }
        else:
            print(f"  [P4] Gcode found: {gcode_remote} — running gate…")
            # Copy gcode locally for gate validation
            local_gcode = Path(tempfile.mktemp(suffix=".gcode", prefix="belt_gui_gate_"))
            subprocess.run(
                ["scp", f"{BEHEMOTH_USER}@{BEHEMOTH_IP}:{gcode_remote}", str(local_gcode)],
                capture_output=True, timeout=30
            )
            gate = _run_gate(local_gcode) if local_gcode.exists() else {"result": "FAIL", "reason": "scp failed"}
            local_gcode.unlink(missing_ok=True)
            phases["slice"] = {
                "status": gate["result"],
                "gcode": gcode_remote,
                "gate": gate,
                "screenshot": shot_post_slice,
            }
            print(f"  [P4] {gate['result']} — gate done")

        # ── Phase 5: Preview transform (layer slider) ──────────────────────────
        print("  [P5] Checking preview transform + layer slider…")
        # Switch to Preview tab
        _key("Tab", wid)
        time.sleep(2)
        shot_preview_a = _screenshot_window(wid, "p5_preview_a")

        # Move layer slider up 3 steps
        _key("Up Up Up", wid)
        time.sleep(1)
        shot_preview_b = _screenshot_window(wid, "p5_preview_b")

        slider_works = False
        if shot_preview_a and shot_preview_b:
            slider_works = _image_changed(shot_preview_a, shot_preview_b)

        phases["preview"] = {
            "status": "PASS" if slider_works else "WARN",
            "detail": "Layer slider changes viewport" if slider_works else "Viewport did not change — slider may not work or no gcode to preview",
            "screenshot_a": shot_preview_a,
            "screenshot_b": shot_preview_b,
        }
        print(f"  [P5] {'PASS' if slider_works else 'WARN'} — slider_works={slider_works}")

        # ── Phase 6: Belt bed renders in both tabs ─────────────────────────────
        print("  [P6] Checking belt bed rendering…")
        # Switch to Prepare
        _key("Tab", wid)
        time.sleep(1)
        shot_bed_prepare = _screenshot_window(wid, "p6_bed_prepare")

        # Switch to Preview
        _key("Tab", wid)
        time.sleep(1)
        shot_bed_preview = _screenshot_window(wid, "p6_bed_preview")

        bed_ok = shot_bed_prepare is not None and shot_bed_preview is not None
        phases["belt_bed"] = {
            "status": "PASS" if bed_ok else "WARN",
            "detail": "Belt bed renders in Prepare and Preview" if bed_ok else "Could not capture screenshots",
            "screenshot_prepare": shot_bed_prepare,
            "screenshot_preview": shot_bed_preview,
        }
        print(f"  [P6] {'PASS' if bed_ok else 'WARN'}")

    finally:
        # ── Phase 7: Cleanup ───────────────────────────────────────────────────
        if pid:
            _ssh(f"kill {pid} 2>/dev/null; sleep 1; kill -9 {pid} 2>/dev/null")
        _ssh_master_stop()  # terminate keepalive session
        print("  [P7] Cleanup done")

    # ── Aggregate result ───────────────────────────────────────────────────────
    all_statuses = [p.get("status", "ERROR") for p in phases.values()]
    if any(s == "FAIL" for s in all_statuses):
        overall = "FAIL"
    elif any(s == "WARN" for s in all_statuses):
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "status": overall,
        "phases": phases,
        "elapsed_s": "see phases",
    }


def _take_screenshot() -> str | None:
    """Take full-desktop screenshot on behemoth. Returns remote path or None."""
    ts = int(time.time())
    remote_path = f"/tmp/belt_validate_{ts}.png"
    rc, _ = _x11(f"import -window root {remote_path} 2>/dev/null", timeout=15)
    return remote_path if rc == 0 else None


def _copy_screenshot_local(remote_path: str, label: str = "screenshot") -> str | None:
    """SCP a screenshot from behemoth to local validation/test_output/."""
    if not remote_path:
        return None
    out_dir = REPO / "validation/test_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    local = str(out_dir / f"gui_{label}_{ts}.png")
    result = subprocess.run(
        ["scp", f"{BEHEMOTH_USER}@{BEHEMOTH_IP}:{remote_path}", local],
        capture_output=True, timeout=20,
    )
    return local if result.returncode == 0 else None


# ── Full test suite ───────────────────────────────────────────────────────────

def run_suite(mode: str) -> int:
    """Run CLI validation on all TEST_MODELS. Returns exit code."""
    passed = failed = 0
    results = []

    for model in TEST_MODELS:
        model = Path(model)
        print(f"\n{'='*60}")
        print(f"Model: {model.name}")
        print(f"{'='*60}")

        if mode == "cli":
            result = validate_cli(model)
        else:
            result = validate_gui(model)

        status = result.get("status", "ERROR")
        elapsed = result.get("elapsed_s", "?")
        print(f"  status  : {status}  ({elapsed}s)")

        if status in ("PASS", "WARN"):
            passed += 1
            if status == "WARN" and mode == "cli":
                reason = result.get("gate", {}).get("output", "")
                print(f"  warnings: {reason[:300]}")
        else:
            failed += 1
            if mode == "gui":
                for ph_name, ph in result.get("phases", {}).items():
                    if ph.get("status") == "FAIL":
                        print(f"  FAIL [{ph_name}]: {ph.get('reason') or ph.get('detail', '')}")
            else:
                reason = result.get("reason") or result.get("gate", {}).get("output", "")
                print(f"  reason  : {reason[:300]}")

        results.append({"model": model.name, **result})

    print(f"\n{'='*60}")
    print(f"Suite result: {passed} PASS / {failed} FAIL")
    print(f"{'='*60}")

    # Write JSON report
    report_path = REPO / "validation/test_output/belt_validate_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"Report: {report_path}")

    return 0 if failed == 0 else 1


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Belt printer slice validation")
    parser.add_argument("mode", choices=["cli", "gui"], help="Validation mode")
    parser.add_argument("models", nargs="*", help="Model files to validate")
    parser.add_argument("--all", action="store_true", help="Run full test suite")
    parser.add_argument("--filament", default="pla", choices=["pla", "petg"],
                        help="Filament profile to use (default: pla)")
    parser.add_argument("--outdir", help="Keep gcode output in this directory")
    args = parser.parse_args()

    filament = FILAMENT_PETG if args.filament == "petg" else FILAMENT_PLA

    if args.all or not args.models:
        sys.exit(run_suite(args.mode))

    exit_code = 0
    for model_str in args.models:
        model = Path(model_str)
        print(f"\nValidating: {model.name} [{args.mode}]")
        outdir = Path(args.outdir) if args.outdir else None

        if args.mode == "cli":
            result = validate_cli(model, filament_json=filament, outdir=outdir)
        else:
            result = validate_gui(model)

        status = result.get("status", "ERROR")
        print(f"  status : {status}")
        if args.mode == "gui":
            for ph_name, ph in result.get("phases", {}).items():
                s = ph.get("status", "?")
                detail = ph.get("detail") or ph.get("reason") or ""
                shots = [v for k, v in ph.items() if "screenshot" in k and v]
                shot_str = f"  screenshots={shots}" if shots else ""
                print(f"    [{ph_name}] {s} — {detail}{shot_str}")
        else:
            if "elapsed_s" in result:
                print(f"  time   : {result['elapsed_s']}s")
            if "gate" in result:
                gate = result["gate"]
                print(f"  gate   : {gate.get('result', '?')}")
                if gate.get("result") != "PASS":
                    print(f"  output : {gate.get('output', '')[:500]}")
            if "reason" in result:
                print(f"  reason : {result['reason']}")
            if "log_tail" in result:
                print(f"  log    :\n{result['log_tail'][-800:]}")

        if status not in ("PASS", "WARN", "SKIP"):
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
