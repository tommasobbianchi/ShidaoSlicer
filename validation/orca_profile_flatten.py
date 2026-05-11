#!/usr/bin/env python3
"""
orca_profile_flatten — resolve the `inherits` chain in OrcaSlicer machine,
process, or filament JSON presets.

The OrcaSlicer CLI does NOT follow `inherits` chains when loading profiles
via `--load-settings` / `--load-filaments`. Critical fields that live in
the parent JSON (e.g. machine_start_gcode, gcode_flavor, layer_height
defaults) are silently dropped from the generated G-code.

For a belt printer this is a SAFETY ISSUE: without machine_start_gcode the
extruder fires its first move without a M109 wait → cold extrude → driver
risk. Discovered and filed as belt-g4a 2026-05-11 while running belt-q46
A4 prints (autonomous validation accidentally bypassed the heat-wait and
was caught only by an extruder-temperature watchdog at 133 s pre-print).

Usage:
    # As a module
    from validation.orca_profile_flatten import flatten_profile
    flat_path = flatten_profile("resources/profiles/IdeaFormer/machine/IdeaFormer IR3 V2 0.4 nozzle.json")
    # → /tmp/orca_flat_<uuid>.json with `inherits` resolved.

    # As a CLI
    python3 validation/orca_profile_flatten.py path/to/preset.json
    # → prints flat JSON path
    python3 validation/orca_profile_flatten.py path/to/preset.json -o flat.json
    # → writes to flat.json

Related: validation/belt_gui_validate.py previously had its own
_merge_profile / _flat_machine_json (mem #473, fixed gcode_flavor regression
2026-03-28). This module is the canonical home; belt_gui_validate.py
re-exports for backwards compatibility.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


def _resolve_profile(name: str, search_dir: Path) -> Path | None:
    """Find a profile JSON by its `name` or `setting_id` field."""
    for p in search_dir.rglob("*.json"):
        try:
            d = json.loads(p.read_text())
            if d.get("name") == name or d.get("setting_id") == name:
                return p
        except Exception:
            pass
    return None


def _merge_profile(path: Path, search_dir: Path,
                   _seen: set | None = None) -> dict:
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
    merged.update(d)  # child overrides parent
    return merged


def flatten_profile(profile_json: Path | str,
                    output: Path | str | None = None) -> Path:
    """
    Resolve the `inherits` chain in profile_json and write a flat JSON
    suitable for `orca-slicer --load-settings` / `--load-filaments`.

    Args:
        profile_json: source machine/process/filament JSON (any depth in
            resources/profiles/<vendor>/<kind>/).
        output: explicit destination path; if None, a temp file is used.

    Returns:
        Path to the flat JSON.
    """
    profile_json = Path(profile_json).resolve()
    if not profile_json.exists():
        raise FileNotFoundError(profile_json)

    # search_dir = vendor root (e.g. resources/profiles/IdeaFormer/)
    search_dir = profile_json.parent.parent
    merged = _merge_profile(profile_json, search_dir)

    # Strip meta keys that confuse the CLI's flat-config loader.
    for key in ("inherits",):
        merged.pop(key, None)

    if output is None:
        output = Path(tempfile.mktemp(prefix="orca_flat_", suffix=".json"))
    else:
        output = Path(output)

    output.write_text(json.dumps(merged, indent=2))
    return output


def _audit(flat: Path) -> dict:
    """Quick safety audit of the flat JSON — returns dict with key fields."""
    d = json.loads(flat.read_text())
    out = {"keys": len(d)}
    for k in ("machine_start_gcode", "machine_end_gcode",
              "printer_structure", "gcode_flavor", "printer_model",
              "filament_type", "nozzle_temperature_initial_layer"):
        v = d.get(k)
        if isinstance(v, list):
            v = v[0] if v else None
        if isinstance(v, str) and len(v) > 60:
            v = v[:57] + "..."
        out[k] = v
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("profile", help="Path to machine/process/filament JSON")
    p.add_argument("-o", "--output", help="Output path (default: temp file)")
    p.add_argument("--audit", action="store_true",
                   help="Print key fields after flattening")
    args = p.parse_args()

    flat = flatten_profile(args.profile, args.output)
    print(flat)
    if args.audit:
        print("--- audit ---")
        for k, v in _audit(flat).items():
            print(f"  {k} = {v!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
