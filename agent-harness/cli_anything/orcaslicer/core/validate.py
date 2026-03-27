"""Belt G-code validation — wraps validation/belt_gcode_gate.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


# Default gate script location
DEFAULT_GATE_SCRIPT = str(
    Path(__file__).resolve().parents[4] / "validation" / "belt_gcode_gate.py"
)


def get_gate_script() -> str:
    """Get the belt_gcode_gate.py path."""
    return os.environ.get("BELT_GATE_SCRIPT", DEFAULT_GATE_SCRIPT)


def validate_gcode(gcode_path: str | Path) -> dict[str, Any]:
    """Run belt G-code validation gate.

    Args:
        gcode_path: Path to G-code file.

    Returns:
        Dict with keys: result (PASS/WARN/FAIL), checks (list), layers, total_moves.
    """
    gcode_path = Path(gcode_path)
    if not gcode_path.exists():
        return {
            "result": "FAIL",
            "error": f"G-code file not found: {gcode_path}",
            "checks": [],
        }

    gate_script = get_gate_script()
    if not Path(gate_script).exists():
        # Fall back: try importing directly
        return _validate_inline(gcode_path)

    try:
        result = subprocess.run(
            [sys.executable, gate_script, "--json", str(gcode_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        report = json.loads(result.stdout)
        return report
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        return {
            "result": "FAIL",
            "error": f"Validation script error: {e}",
            "checks": [],
        }


def _validate_inline(gcode_path: Path) -> dict[str, Any]:
    """Inline validation when gate script is not available.

    Imports GcodeValidator directly from the validation module.
    """
    validation_dir = Path(__file__).resolve().parents[4] / "validation"
    sys.path.insert(0, str(validation_dir.parent))

    try:
        from validation.belt_gcode_gate import GcodeValidator
        validator = GcodeValidator(str(gcode_path))
        return validator.json_report()
    except ImportError:
        return {
            "result": "FAIL",
            "error": "Cannot find belt_gcode_gate.py — set BELT_GATE_SCRIPT env var",
            "checks": [],
        }
    finally:
        if str(validation_dir.parent) in sys.path:
            sys.path.remove(str(validation_dir.parent))


def preflight_check(gcode_path: str | Path) -> dict[str, Any]:
    """Pre-upload safety checks derived from known belt printer failure modes.

    Checks the G-code header for settings that are known to cause print failures
    on belt printers, independently of the belt_gcode_gate.py rules.

    Rules:
      P1-SUPPORT: enable_support must be 0. Built-in OrcaSlicer support generates
                  virtual-space columns that land in wrong physical positions on belt.
      P2-WALL-SEQ: wall_sequence must not be 'outer wall/inner wall'. Outer-wall-first
                   causes overhanging perimeters to print in wrong belt-space position
                   because seam placement ignores belt direction.

    Returns:
        Dict with keys: result (PASS/FAIL), issues (list of dicts with rule/message).
    """
    gcode_path = Path(gcode_path)
    if not gcode_path.exists():
        return {"result": "FAIL", "issues": [{"rule": "PREFLIGHT", "message": f"File not found: {gcode_path}"}]}

    # OrcaSlicer writes settings as "; key = value" comments at the END of the file
    # (after all gcode), not in the header. Scan the whole file collecting them.
    header_settings: dict[str, str] = {}
    try:
        with open(gcode_path, errors="replace") as f:
            for line in f:
                if line.startswith("; ") and " = " in line:
                    key, _, val = line[2:].strip().partition(" = ")
                    header_settings[key.strip()] = val.strip()
    except OSError as e:
        return {"result": "FAIL", "issues": [{"rule": "PREFLIGHT", "message": f"Cannot read file: {e}"}]}

    issues = []

    # P1: enable_support must be 0
    support_val = header_settings.get("enable_support", "0")
    if support_val != "0":
        issues.append({
            "rule": "P1-SUPPORT",
            "message": (
                f"enable_support={support_val} — OrcaSlicer built-in support is not "
                "compatible with belt printers. Generates virtual-space columns that "
                "print in wrong physical positions. Use support_preprocess.py instead."
            ),
        })

    # P2: wall_sequence must not be outer-first
    wall_seq = header_settings.get("wall_sequence", "")
    if wall_seq == "outer wall/inner wall":
        issues.append({
            "rule": "P2-WALL-SEQ",
            "message": (
                "wall_sequence='outer wall/inner wall' — outer-wall-first causes "
                "overhanging perimeters to print ahead of the model in belt direction. "
                "Seam placement does not account for belt axis."
            ),
        })

    return {
        "result": "FAIL" if issues else "PASS",
        "issues": issues,
        "settings_found": len(header_settings),
    }


def is_safe_to_upload(report: dict[str, Any]) -> bool:
    """Check if a validation report indicates safe-to-upload status."""
    return report.get("result") == "PASS"


def format_report(report: dict[str, Any], verbose: bool = False) -> str:
    """Format a validation report as human-readable text."""
    lines = []
    result = report.get("result", "UNKNOWN")
    layers = report.get("layers", "?")
    moves = report.get("total_moves", "?")

    lines.append(f"Result: {result}")
    lines.append(f"Layers: {layers}  |  Moves: {moves}")

    if "error" in report:
        lines.append(f"Error: {report['error']}")

    for check in report.get("checks", []):
        status = check.get("status", "?")
        rule = check.get("rule", "?")
        msg = check.get("message", "")
        icon = {"OK": "PASS", "WARN": "WARN", "FAIL": "FAIL"}.get(status, status)
        lines.append(f"  {icon}  [{rule}] {msg}")

    return "\n".join(lines)
