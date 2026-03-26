"""Invoke OrcaSlicer headless CLI for slicing."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_REPO = Path("/home/user/projects/ORCA_BELT")
_RELEASE = _REPO / "build/src/Release/orca-slicer"
_DEBUG   = _REPO / "build/src/Debug/orca-slicer"


def get_binary() -> str:
    """Get the OrcaSlicer binary path.

    Prefers ORCA_SLICER_BIN env var, then Release build, then Debug build.
    Release binary is skipped if it's 0 bytes (failed link).
    """
    if env := os.environ.get("ORCA_SLICER_BIN"):
        return env
    if _RELEASE.exists() and _RELEASE.stat().st_size > 0:
        return str(_RELEASE)
    if _DEBUG.exists() and _DEBUG.stat().st_size > 0:
        return str(_DEBUG)
    return str(_RELEASE)  # will fail with a clear error


def _parse_layer_count(combined_output: str) -> int | None:
    """Extract final layer count from ORCA_BELT debug log lines."""
    # "ORCA_BELT slice_volumes: after top-removal: N layers remain"
    m = re.search(r"ORCA_BELT slice_volumes: after top-removal: (\d+) layers", combined_output)
    if m:
        return int(m.group(1))
    return None


def _parse_gcode_layer_count(gcode_path: str) -> int | None:
    """Count layer change markers in a G-code file."""
    try:
        count = 0
        with open(gcode_path, "r", errors="replace") as f:
            for line in f:
                if line.startswith(";LAYER_CHANGE") or line.startswith("; layer"):
                    count += 1
        return count if count > 0 else None
    except OSError:
        return None


def slice_model(
    model_3mf: str | Path,
    output_dir: str | Path | None = None,
    load_settings: str | Path | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Slice a 3MF model using OrcaSlicer headless CLI.

    Args:
        model_3mf: Path to input .3mf file.
        output_dir: Directory for output G-code. Defaults to temp dir.
        load_settings: Optional JSON preset file to override settings.
        timeout: Max seconds to wait for slicing.

    Returns:
        Dict with keys: success, gcode_path, stdout, stderr, returncode, duration_s.
    """
    import time

    model_3mf = Path(model_3mf).resolve()
    if not model_3mf.exists():
        return {
            "success": False,
            "gcode_path": None,
            "error": f"Model file not found: {model_3mf}",
            "returncode": -1,
        }

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="orca_slice_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    binary = get_binary()
    if not Path(binary).exists():
        return {
            "success": False,
            "gcode_path": None,
            "error": f"OrcaSlicer binary not found: {binary}",
            "returncode": -1,
        }

    # Use --debug 3 (info level) to capture ORCA_BELT layer-count log lines
    cmd = [binary, "--debug", "3", "--slice", "1", "--outputdir", str(output_dir), str(model_3mf)]

    if load_settings:
        load_settings = Path(load_settings).resolve()
        cmd.extend(["--load-settings", str(load_settings)])

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "DISPLAY": ""},  # headless — no display needed
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "gcode_path": None,
            "error": f"Slicing timed out after {timeout}s",
            "returncode": -1,
            "duration_s": timeout,
        }

    duration = time.monotonic() - t0

    # Find output gcode (OrcaSlicer writes .gcode.tmp if it exits with error/warning)
    gcode_files = list(output_dir.glob("*.gcode")) or list(output_dir.glob("*.gcode.tmp"))
    gcode_path = str(gcode_files[0]) if gcode_files else None

    # Success = gcode was produced (OrcaSlicer exits non-zero even on warnings)
    success = gcode_path is not None

    # Extract layer count from ORCA_BELT debug output (stderr carries log lines)
    combined = result.stdout + result.stderr
    layer_count = _parse_layer_count(combined)
    if layer_count is None and gcode_path:
        layer_count = _parse_gcode_layer_count(gcode_path)

    return {
        "success": success,
        "gcode_path": gcode_path,
        "layer_count": layer_count,
        "output_dir": str(output_dir),
        "binary": binary,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "duration_s": round(duration, 2),
    }
