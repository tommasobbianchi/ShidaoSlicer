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
BEHEMOTH_IP   = "<WORKSTATION_HOST>"
BEHEMOTH_USER = "tommaso"
BEHEMOTH_BIN  = "/home/user/bin/orca-belt"
BEHEMOTH_DISPLAY = ":1"


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

def _ssh(cmd: str, timeout=30) -> tuple[int, str]:
    full = ["ssh", f"{BEHEMOTH_USER}@{BEHEMOTH_IP}", cmd]
    rc, out, err = _run(full, timeout=timeout)
    return rc, out + err


def _behemoth_has(tool: str) -> bool:
    rc, _ = _ssh(f"which {tool} 2>/dev/null")
    return rc == 0


def validate_gui(model_path: Path, wait_load_s: int = 120) -> dict:
    """
    GUI smoke-test on behemoth:
      1. Kill any running orca-slicer
      2. Launch orca-belt with model_path (via SSHFS mount)
      3. Poll for backup dir creation in /tmp/orcaslicer_model/ (= model loaded)
      4. Take screenshot
      5. Kill GUI
      6. Run belt gate against CLI-generated gcode (same slicing engine)

    OrcaSlicer does not reliably auto-slice when launched headless over SSH,
    so we separate GUI health-check (launch + model load) from gcode validation
    (done via CLI, identical engine).
    """

    if not _behemoth_has("import"):
        return {"status": "ERROR", "reason": "imagemagick not installed on behemoth. Run: sudo apt install imagemagick"}

    model_path = Path(model_path).resolve()
    behemoth_model = str(model_path)

    print(f"  model   : {model_path.name}")
    print(f"  display : {BEHEMOTH_DISPLAY}")

    # 1. Kill stale orca-slicer
    _ssh("pkill -f orca-slicer 2>/dev/null; sleep 1")

    # Snapshot existing backup dirs to detect newly created ones
    _, existing_dirs_raw = _ssh(
        "find /tmp/orcaslicer_model -mindepth 2 -maxdepth 2 -type d 2>/dev/null"
    )
    existing_dirs = set(existing_dirs_raw.strip().splitlines())

    # 2. Launch orca-belt
    launch_cmd = (
        f"DISPLAY={BEHEMOTH_DISPLAY} nohup {BEHEMOTH_BIN} "
        f"'{behemoth_model}' </dev/null >/tmp/orcabelt_gui.log 2>&1 &"
    )
    _ssh(launch_cmd, timeout=10)
    print(f"  launched orca-belt, waiting up to {wait_load_s}s for model load…")

    # 3. Poll for new backup dir (= OrcaSlicer created its session + loaded model)
    deadline = time.time() + wait_load_s
    gui_loaded = False

    while time.time() < deadline:
        time.sleep(5)
        rc, out = _ssh(
            "find /tmp/orcaslicer_model -mindepth 2 -maxdepth 2 -type d 2>/dev/null"
        )
        if rc == 0:
            current_dirs = set(out.strip().splitlines())
            if current_dirs - existing_dirs:
                gui_loaded = True
                break

    # 4. Screenshot
    screenshot = _take_screenshot()

    # 5. Kill GUI
    _ssh("pkill -f orca-slicer 2>/dev/null")

    if not gui_loaded:
        _, gui_log = _ssh("tail -20 /tmp/orcabelt_gui.log 2>/dev/null")
        return {
            "status": "FAIL",
            "reason": f"GUI did not load model within {wait_load_s}s",
            "gui_log_tail": gui_log,
            "screenshot": screenshot,
        }

    # 6. Validate gcode via CLI (same slicing engine — headless auto-slice unreliable)
    print("  GUI loaded OK — validating gcode via CLI (same engine)…")
    cli_result = validate_cli(model_path)
    return {
        "gui_status": "LOADED",
        "status": cli_result.get("status", "ERROR"),
        "screenshot": screenshot,
        "gate": cli_result.get("gate"),
        "elapsed_s": cli_result.get("elapsed_s"),
        "gcode": cli_result.get("gcode"),
    }


def _take_screenshot() -> str | None:
    """Take screenshot on behemoth, save to /tmp, return path or None."""
    ts = int(time.time())
    remote_path = f"/tmp/belt_validate_{ts}.png"
    rc, _ = _ssh(
        f"DISPLAY={BEHEMOTH_DISPLAY} import -window root {remote_path} 2>/dev/null",
        timeout=15,
    )
    return remote_path if rc == 0 else None


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
            if status == "WARN":
                reason = result.get("gate", {}).get("output", "")
                print(f"  warnings: {reason[:300]}")
        else:
            failed += 1
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
