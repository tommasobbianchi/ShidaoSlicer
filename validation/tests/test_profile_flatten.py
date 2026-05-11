#!/usr/bin/env python3
"""
belt-g4a regression — orca_profile_flatten must resolve machine_start_gcode
and gcode_flavor from the IdeaFormer JSON inheritance chain.

Without this resolution, OrcaSlicer CLI slices emit Marlin-default start
sequences (M201/M203/M204/M205 + M190 + M104 without M109 wait). The first
extrusion fires with a cold extruder → driver risk.

This test asserts:
  1. flatten_profile on IR3 V2 0.4 nozzle.json yields machine_start_gcode
     containing the canonical IdeaFormer belt-start template marker.
  2. The flattened output also carries gcode_flavor=klipper and
     printer_structure=belt (downstream R7/R11 gate depends on belt mode).
  3. Negative: a JSON without inherits returns its raw keys unchanged.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "validation"))
from orca_profile_flatten import flatten_profile  # noqa: E402


def main() -> int:
    machine = REPO / "resources/profiles/IdeaFormer/machine/IdeaFormer IR3 V2 0.4 nozzle.json"
    if not machine.exists():
        print(f"FAIL: machine JSON missing — {machine}")
        return 2

    flat = flatten_profile(machine)
    d = json.loads(flat.read_text())

    fails = []

    # 1. machine_start_gcode populated with IdeaFormer marker
    start = d.get("machine_start_gcode") or ""
    if isinstance(start, list):
        start = start[0] if start else ""
    if "IdeaFormer IR3 V2 Belt Printer Start" not in start:
        fails.append(f"machine_start_gcode missing IdeaFormer marker; got={start[:80]!r}")
    else:
        print(f"  PASS machine_start_gcode contains IdeaFormer Belt Printer Start")

    # 2a. gcode_flavor = klipper (parent inheritance)
    flavor = d.get("gcode_flavor")
    if flavor != "klipper":
        fails.append(f"gcode_flavor expected 'klipper', got {flavor!r}")
    else:
        print(f"  PASS gcode_flavor = klipper (inherited from fdm_ideaformer_common)")

    # 2b. printer_structure = belt
    ps = d.get("printer_structure")
    if ps != "belt":
        fails.append(f"printer_structure expected 'belt', got {ps!r}")
    else:
        print(f"  PASS printer_structure = belt")

    # 3. Negative: a root (no-inherits) profile preserves its keys
    common = REPO / "resources/profiles/IdeaFormer/machine/fdm_machine_common.json"
    if common.exists():
        raw = json.loads(common.read_text())
        flat2 = flatten_profile(common)
        d2 = json.loads(flat2.read_text())
        # Should be identical minus "inherits" (which root doesn't have anyway)
        for k in ("name", "type"):
            if raw.get(k) != d2.get(k):
                fails.append(f"root profile {k} changed: {raw.get(k)!r} → {d2.get(k)!r}")
        if not fails:
            print("  PASS root profile (no inherits) preserves keys")
        flat2.unlink(missing_ok=True)

    flat.unlink(missing_ok=True)

    print()
    if fails:
        print(f"OVERALL: FAIL ({len(fails)} sub-checks)")
        for f in fails:
            print(f"  • {f}")
        return 1
    print("OVERALL: PASS — flatten_profile resolves IdeaFormer chain "
          "(belt-g4a regression guarded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
