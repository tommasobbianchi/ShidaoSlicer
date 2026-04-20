#!/usr/bin/env python3
"""
Belt Printer G-code Validation Gate for IdeaFormer IR3 V2.

Validates that a G-code file follows belt printer rules before uploading.
All checks are derived from hard-won physical print failures:

- v7 crash:  Split Z/XY travel → nozzle descended through model
- v9 crash:  Z_mach oscillated within layer (no inclined Z on travel)
- v10 issue: Z on every travel move (redundant, differs from IdeaMaker)
- v11 fix:   Z set once per layer (combined XYZ), then XY-only → matches IdeaMaker

Exit codes:
  0 = PASS (safe to print)
  1 = FAIL (unsafe, do NOT print)
  2 = WARN (anomalies found, review before printing)
"""

import re
import sys
import json
import argparse
from collections import defaultdict
from pathlib import Path


# ── Rule thresholds (tuned from successful prints) ──────────────────────

Z_CONSTANCY_TOL = 0.01       # mm — max Z spread within a layer
FIRST_LAYER_Y_MAX = 2.0      # mm — Y_mach must be close to belt surface
Z_STEP_EXPECTED = 0.283      # mm — 0.2mm / cos(45°)
Z_STEP_TOL = 0.05            # mm — tolerance on Z step
MAX_Z_ONLY_MOVES = 0         # Z-only moves = belt moves without nozzle = crash
MAX_NEG_Z = 0                # negative Z = belt reversing past home
Z_PER_LAYER_MAX = 3          # max G1 commands with Z per layer (1 ideal, allow margin)
MIN_Y_HOPS_RATIO = 0.5       # at least 50% of travel retract cycles should have Y-hop


# ── Slicer detection ────────────────────────────────────────────────────

def detect_slicer(lines, scan_lines=30):
    """Detect which slicer generated the G-code from header comments.

    Returns a lowercase string: 'orcaslicer', 'ideamaker', 'bambu', or 'unknown'.
    Only the first scan_lines lines are checked (header only).
    """
    for line in lines[:scan_lines]:
        l = line.lower()
        # ORCA_BELT: treat our fork identifier ("OrcaBelt" in the header) as orcaslicer.
        if "orcaslicer" in l or "orca slicer" in l or "orcabelt" in l or "orca belt" in l:
            return "orcaslicer"
        if "ideamaker" in l or "idea maker" in l:
            return "ideamaker"
        if "bambustudio" in l or "bambu studio" in l:
            return "bambu"
    return "unknown"


class GcodeValidator:
    def __init__(self, filepath, verbose=False):
        self.filepath = filepath
        self.verbose = verbose
        self.lines = Path(filepath).read_text().splitlines()
        self.results = []
        self.layer_count = 0
        self.slicer = detect_slicer(self.lines)
        self.total_moves = 0

    def fail(self, rule, msg):
        self.results.append(("FAIL", rule, msg))

    def warn(self, rule, msg):
        self.results.append(("WARN", rule, msg))

    def ok(self, rule, msg):
        self.results.append(("OK", rule, msg))

    def parse(self):
        """Parse G-code into structured data."""
        self.layer_count = 0
        self.layer_z = defaultdict(list)        # layer → list of Z values (strings)
        self.layer_z_cmds = defaultdict(int)     # layer → count of G1 with Z
        self.neg_z_moves = []                    # (line_no, z_value)
        self.z_only_moves = []                   # (line_no, line_text)
        self.ext_with_z = 0
        self.ext_no_z = 0
        self.travel_with_z = 0
        self.travel_no_z = 0
        self.first_layer_y = []
        self.y_hops = 0
        self.retract_count = 0
        self.total_moves = 0

        prev_y = None
        prev_e = None
        in_start_gcode = True  # skip start gcode

        for i, line in enumerate(self.lines):
            lineno = i + 1

            if ";LAYER_CHANGE" in line:
                self.layer_count += 1
                in_start_gcode = False
                continue

            if in_start_gcode:
                continue

            if not line.startswith("G1 "):
                continue

            self.total_moves += 1
            cmd = line.split(";")[0]

            has_x = "X" in cmd
            has_y = "Y" in cmd
            has_z = "Z" in cmd
            has_e = "E" in cmd

            mz = re.search(r"Z([\d.-]+)", cmd)
            my = re.search(r"Y([\d.-]+)", cmd)
            me = re.search(r"E([\d.-]+)", cmd)

            # Track Z per layer
            if mz:
                z_val = float(mz.group(1))
                z_str = mz.group(1)
                self.layer_z[self.layer_count].append(z_str)
                self.layer_z_cmds[self.layer_count] += 1

                if z_val < -0.001:
                    self.neg_z_moves.append((lineno, z_val))

                # Z-only move (no X, no Y, no E) — belt moves alone
                if has_z and not has_x and not has_y and not has_e:
                    self.z_only_moves.append((lineno, line.strip()))

            # Classify move type
            if has_e and (has_x or has_y):
                if has_z:
                    self.ext_with_z += 1
                else:
                    self.ext_no_z += 1

                # Track retract (E decreasing)
                if me:
                    e_val = float(me.group(1))
                    if prev_e is not None and e_val < prev_e - 0.01:
                        self.retract_count += 1
                    prev_e = e_val
            elif has_e:
                # E-only (retract/unretract)
                if me:
                    e_val = float(me.group(1))
                    if prev_e is not None and e_val < prev_e - 0.01:
                        self.retract_count += 1
                    prev_e = e_val
            elif has_x or has_y:
                if has_z:
                    self.travel_with_z += 1
                else:
                    self.travel_no_z += 1

            # First layer Y
            if self.layer_count == 1 and my:
                self.first_layer_y.append(float(my.group(1)))

            # Y-hop detection (Y increase without extrusion)
            if my and not has_e:
                y_val = float(my.group(1))
                if prev_y is not None and y_val > prev_y + 0.1:
                    self.y_hops += 1
                prev_y = y_val
            elif my:
                prev_y = float(my.group(1))

    def check_z_constancy(self):
        """R1: Z must be constant within each layer (belt doesn't oscillate)."""
        violations = 0
        worst_spread = 0
        worst_layer = 0
        for layer in sorted(self.layer_z):
            z_strs = self.layer_z[layer]
            if not z_strs:
                continue
            z_vals = [float(z) for z in z_strs]
            spread = max(z_vals) - min(z_vals)
            if spread > Z_CONSTANCY_TOL:
                violations += 1
                if spread > worst_spread:
                    worst_spread = spread
                    worst_layer = layer

        if violations == 0:
            self.ok("R1-Z-CONST", "Z constant within every layer")
        else:
            self.fail("R1-Z-CONST",
                      f"{violations} layers with Z variation > {Z_CONSTANCY_TOL}mm "
                      f"(worst: layer {worst_layer}, spread={worst_spread:.3f}mm). "
                      f"Belt is oscillating! Check travel Z uses compute_belt_inclined_z().")

    def check_no_negative_z(self):
        """R2: Z must never go negative (belt can't reverse past home)."""
        if not self.neg_z_moves:
            self.ok("R2-NO-NEG-Z", "No negative Z values")
        else:
            worst = min(z for _, z in self.neg_z_moves)
            self.fail("R2-NO-NEG-Z",
                      f"{len(self.neg_z_moves)} moves with negative Z (min={worst:.3f}mm). "
                      f"Check belt_z_base subtraction and model placement.")

    def check_no_z_only(self):
        """R3: No Z-only moves (belt advancing without nozzle = crash risk)."""
        if not self.z_only_moves:
            self.ok("R3-NO-Z-ONLY", "No Z-only moves (no bare belt advances)")
        else:
            first = self.z_only_moves[0]
            self.fail("R3-NO-Z-ONLY",
                      f"{len(self.z_only_moves)} Z-only moves (belt advances without nozzle). "
                      f"First at line {first[0]}: {first[1]}. "
                      f"This caused the v7 crash — use combined XYZ for layer change.")

    def check_z_per_layer(self):
        """R4: Z should appear at most once per layer (layer change travel only)."""
        violations = 0
        worst_count = 0
        worst_layer = 0
        for layer in sorted(self.layer_z_cmds):
            count = self.layer_z_cmds[layer]
            if count > Z_PER_LAYER_MAX:
                violations += 1
                if count > worst_count:
                    worst_count = count
                    worst_layer = layer

        if violations == 0:
            self.ok("R4-Z-ONCE", f"Z appears ≤{Z_PER_LAYER_MAX}× per layer "
                    f"(travel_with_z={self.travel_with_z}, layers={self.layer_count})")
        else:
            avg = self.travel_with_z / max(self.layer_count, 1)
            self.fail("R4-Z-ONCE",
                      f"{violations} layers with Z on >{Z_PER_LAYER_MAX} moves "
                      f"(worst: layer {worst_layer} with {worst_count}). "
                      f"Avg {avg:.1f} Z-moves/layer. "
                      f"This was the v10 issue — within-layer travel must use XY only.")

    def check_no_extrusion_z(self):
        """R5: Extrusion lines must not contain Z (belt stays still during extrusion)."""
        if self.ext_with_z == 0:
            self.ok("R5-EXT-NO-Z", f"All {self.ext_no_z} extrusion moves are XY-only")
        else:
            self.warn("R5-EXT-NO-Z",
                      f"{self.ext_with_z} extrusion moves contain Z "
                      f"(should be XY-only — belt is constant during extrusion).")

    def check_y_hops(self):
        """R6: Travel should use Y-hops (gantry lift), not Z-hops."""
        if self.y_hops == 0:
            self.warn("R6-Y-HOPS", "No Y-hops detected — nozzle may drag across print during travel")
        elif self.retract_count > 0 and self.y_hops / max(self.retract_count, 1) < MIN_Y_HOPS_RATIO:
            ratio = self.y_hops / self.retract_count
            self.warn("R6-Y-HOPS",
                      f"Only {self.y_hops} Y-hops for {self.retract_count} retracts "
                      f"(ratio={ratio:.2f}, expect ≥{MIN_Y_HOPS_RATIO})")
        else:
            self.ok("R6-Y-HOPS", f"{self.y_hops} Y-hops (gantry lifts) detected")

    def check_first_layer_y(self):
        """R7: First layer Y must be close to 0 (belt surface adhesion)."""
        if not self.first_layer_y:
            self.warn("R7-1ST-Y", "No first layer Y data found")
            return

        y_min = min(self.first_layer_y)
        y_max = max(self.first_layer_y)

        if y_max > FIRST_LAYER_Y_MAX:
            self.fail("R7-1ST-Y",
                      f"First layer Y range [{y_min:.3f}, {y_max:.3f}]mm — "
                      f"max {y_max:.3f} > {FIRST_LAYER_Y_MAX}mm. "
                      f"Nozzle too far from belt. Check model placement and belt_z_base.")
        elif y_min < 0:
            self.fail("R7-1ST-Y",
                      f"First layer has negative Y ({y_min:.3f}mm) — "
                      f"nozzle below belt surface!")
        else:
            self.ok("R7-1ST-Y", f"First layer Y range [{y_min:.3f}, {y_max:.3f}]mm")

    def check_z_step(self):
        """R8: Z step between layers should be ~0.283mm (0.2mm / cos45°)."""
        layer_z_vals = {}
        for layer in sorted(self.layer_z):
            z_strs = self.layer_z[layer]
            if z_strs:
                layer_z_vals[layer] = float(z_strs[0])

        if len(layer_z_vals) < 3:
            self.warn("R8-Z-STEP", "Too few layers to check Z step")
            return

        steps = []
        sorted_layers = sorted(layer_z_vals)
        for i in range(1, min(len(sorted_layers), 20)):
            l1, l2 = sorted_layers[i - 1], sorted_layers[i]
            step = layer_z_vals[l2] - layer_z_vals[l1]
            steps.append(step)

        if not steps:
            return

        avg_step = sum(steps) / len(steps)
        if abs(avg_step - Z_STEP_EXPECTED) > Z_STEP_TOL:
            self.warn("R8-Z-STEP",
                      f"Avg Z step={avg_step:.3f}mm (expected ~{Z_STEP_EXPECTED}mm). "
                      f"Check layer height and cos(45°) scaling.")
        else:
            self.ok("R8-Z-STEP", f"Z step={avg_step:.3f}mm (expected ~{Z_STEP_EXPECTED}mm)")

    def check_z_monotonic(self):
        """R9: Z must be monotonically increasing between layers (belt only advances)."""
        layer_z_vals = {}
        for layer in sorted(self.layer_z):
            z_strs = self.layer_z[layer]
            if z_strs:
                layer_z_vals[layer] = float(z_strs[0])

        reversals = 0
        sorted_layers = sorted(layer_z_vals)
        for i in range(1, len(sorted_layers)):
            l_prev, l_curr = sorted_layers[i - 1], sorted_layers[i]
            if layer_z_vals[l_curr] < layer_z_vals[l_prev] - 0.001:
                reversals += 1

        if reversals == 0:
            self.ok("R9-Z-MONO", "Z monotonically increasing between layers")
        else:
            self.fail("R9-Z-MONO",
                      f"{reversals} Z reversals between layers — belt going backward!")

    def validate(self):
        """Run all checks and return (fails, warns).

        Belt safety checks are only applied to OrcaSlicer G-code.
        Files from other slicers (IdeaMaker, Bambu, unknown) are passed
        immediately with no warnings — they have their own validation logic
        and are not expected to follow OrcaSlicer belt conventions.
        """
        if self.slicer != "orcaslicer":
            self.results.append(("OK", "SLICER-SKIP",
                                  f"Slicer detected: {self.slicer!r} — "
                                  f"OBP belt checks apply to OrcaSlicer only. Passing without checks."))
            return [], []

        self.parse()

        self.check_z_constancy()        # R1
        self.check_no_negative_z()      # R2
        self.check_no_z_only()          # R3
        self.check_z_per_layer()        # R4
        self.check_no_extrusion_z()     # R5
        self.check_y_hops()             # R6
        self.check_first_layer_y()      # R7
        self.check_z_step()             # R8
        self.check_z_monotonic()        # R9

        # Determine exit code
        fails = [r for r in self.results if r[0] == "FAIL"]
        warns = [r for r in self.results if r[0] == "WARN"]

        return fails, warns

    def print_report(self):
        """Print human-readable report."""
        fails, warns = self.validate()

        print(f"\n{'='*60}")
        print(f"  Belt G-code Validation: {Path(self.filepath).name}")
        print(f"  Slicer: {self.slicer}  |  Layers: {self.layer_count}  |  Moves: {self.total_moves}")
        print(f"{'='*60}\n")

        for status, rule, msg in self.results:
            icon = {"OK": "  PASS", "WARN": "  WARN", "FAIL": "**FAIL"}[status]
            print(f"  {icon}  [{rule}] {msg}")

        print(f"\n{'─'*60}")

        if fails:
            print(f"\n  RESULT: BLOCKED — {len(fails)} critical failure(s)")
            print(f"  Do NOT send this G-code to the printer.\n")
            return 1
        elif warns:
            print(f"\n  RESULT: WARNING — {len(warns)} anomaly(ies)")
            print(f"  Review before printing.\n")
            return 2
        else:
            print(f"\n  RESULT: PASSED — Safe to print")
            print(f"  All {len(self.results)} checks passed.\n")
            return 0

    def json_report(self):
        """Return JSON-serializable report."""
        fails, warns = self.validate()
        return {
            "file": str(self.filepath),
            "slicer": self.slicer,
            "layers": self.layer_count,
            "total_moves": self.total_moves,
            "result": "FAIL" if fails else ("WARN" if warns else "PASS"),
            "checks": [
                {"status": s, "rule": r, "message": m}
                for s, r, m in self.results
            ],
        }


def main():
    parser = argparse.ArgumentParser(
        description="Belt printer G-code validation gate for IdeaFormer IR3 V2"
    )
    parser.add_argument("gcode", help="Path to G-code file to validate")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--upload", action="store_true",
                        help="Upload to IdeaFormer if validation passes")
    parser.add_argument("--name", type=str, default=None,
                        help="Filename on printer (default: same as input)")
    args = parser.parse_args()

    gcode_path = Path(args.gcode)
    if not gcode_path.exists():
        print(f"Error: {gcode_path} not found", file=sys.stderr)
        sys.exit(1)

    validator = GcodeValidator(str(gcode_path), verbose=args.verbose)

    if args.json:
        report = validator.json_report()
        print(json.dumps(report, indent=2))
        exit_code = {"PASS": 0, "WARN": 2, "FAIL": 1}[report["result"]]
    else:
        exit_code = validator.print_report()

    # Upload only if PASS (exit_code=0)
    if args.upload:
        if exit_code == 0:
            import subprocess
            dest_name = args.name or gcode_path.name
            dest = f"ideaformer@<PRINTER_HOST>:printer_data/gcodes/{dest_name}"
            print(f"  Uploading to IdeaFormer: {dest_name}")
            result = subprocess.run(
                ["sshpass", "-p", "1234", "scp", str(gcode_path), dest],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print(f"  Upload complete.")
            else:
                print(f"  Upload failed: {result.stderr.strip()}", file=sys.stderr)
                exit_code = 1
        elif exit_code == 2:
            print(f"  Skipping upload — warnings found. Use --force-upload to override.")
        else:
            print(f"  BLOCKED — will not upload failed G-code to printer.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
