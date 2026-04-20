#!/usr/bin/env python3
"""
belt_cli_validate.py — Autonomous headless belt support validation.

Slices a 3MF via CLI, parses /tmp/belt_support_validation.txt,
evaluates geometric correctness of belt support placement.

Usage:
    python3 validation/belt_cli_validate.py [model.3mf] [--verbose]

Exit codes:
    0 = all checks PASS
    1 = one or more checks FAIL
    2 = CLI crash or no validation data
"""

import subprocess
import sys
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

SLICER = os.path.join(os.path.dirname(__file__), "..", "build", "src", "Release", "orca-slicer")
DEFAULT_MODEL = os.path.join(os.path.dirname(__file__), "..", "inverted_L.3mf")
VALIDATION_FILE = "/tmp/belt_support_validation.txt"


@dataclass
class LayerData:
    index: int
    z: float
    sup_area: float
    mod_area: float
    n_expolys: int
    sup_bb_min_y: float
    sup_bb_max_y: float
    sup_bb_min_x: float
    sup_bb_max_x: float
    mod_bb_min_x: float
    mod_bb_min_y: float
    mod_bb_max_x: float
    mod_bb_max_y: float


@dataclass
class ValidationResult:
    n_layers: int = 0
    n_support_layers: int = 0
    total_entities: int = 0
    layers: List[LayerData] = field(default_factory=list)

    # Checks
    support_exists: bool = False
    support_at_low_y: bool = False       # support bb_min_y near 0 (belt surface)
    support_below_model: bool = False    # support bb_max_y < model bb_min_y
    support_grows_monotonic: bool = False # support area increases
    continuity: bool = False
    cli_success: bool = False


def run_slicer(model_path: str, verbose: bool = False) -> bool:
    """Run the OrcaSlicer CLI and return True if it succeeded."""
    cmd = [SLICER, "--debug", "3", "--slice", "1", model_path]
    if verbose:
        print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if verbose:
            # Print belt-related log lines
            for line in result.stderr.split("\n"):
                if any(k in line.lower() for k in ["belt", "support", "layer"]):
                    print(f"  LOG: {line.strip()}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("ERROR: Slicer timed out after 120s")
        return False
    except FileNotFoundError:
        print(f"ERROR: Slicer not found at {SLICER}")
        return False


def parse_validation(path: str = VALIDATION_FILE) -> Optional[ValidationResult]:
    """Parse /tmp/belt_support_validation.txt into structured data."""
    if not os.path.exists(path):
        return None

    result = ValidationResult()
    # Option A format: sup_area=... mod_area=... sup_bb=[...] mod_bb=[...]
    line_pattern_a = re.compile(
        r"L(\d+)\s+z=\s*([\d.]+)\s+sup_area=\s*([\d.]+)\s+mod_area=\s*([\d.]+)\s+nex=(\d+)\s+"
        r"sup_bb=\[\s*([-\d.]+),\s*([-\d.]+)\]-\[\s*([-\d.]+),\s*([-\d.]+)\]\s+"
        r"mod_bb=\[\s*([-\d.]+),\s*([-\d.]+)\]-\[\s*([-\d.]+),\s*([-\d.]+)\]"
    )
    # 2D void-fill format: area=... nex=... intf=... bb=[...]
    line_pattern_vf = re.compile(
        r"L(\d+)\s+z=\s*([\d.]+)\s+area=\s*([\d.]+)\s+nex=(\d+)\s+intf=(\d+)\s+"
        r"bb=\[\s*([-\d.]+),\s*([-\d.]+)\]-\[\s*([-\d.]+),\s*([-\d.]+)\]"
    )

    with open(path) as f:
        for line in f:
            line = line.strip()

            # Parse header
            m = re.match(r"n_layers:\s*(\d+)", line)
            if m:
                result.n_layers = int(m.group(1))

            # Parse layer data — try Option A format first
            m = line_pattern_a.match(line)
            if m:
                ld = LayerData(
                    index=int(m.group(1)),
                    z=float(m.group(2)),
                    sup_area=float(m.group(3)),
                    mod_area=float(m.group(4)),
                    n_expolys=int(m.group(5)),
                    sup_bb_min_x=float(m.group(6)),
                    sup_bb_min_y=float(m.group(7)),
                    sup_bb_max_x=float(m.group(8)),
                    sup_bb_max_y=float(m.group(9)),
                    mod_bb_min_x=float(m.group(10)),
                    mod_bb_min_y=float(m.group(11)),
                    mod_bb_max_x=float(m.group(12)),
                    mod_bb_max_y=float(m.group(13)),
                )
                result.layers.append(ld)
            else:
                # Try 2D void-fill format
                m = line_pattern_vf.match(line)
                if m:
                    ld = LayerData(
                        index=int(m.group(1)),
                        z=float(m.group(2)),
                        sup_area=float(m.group(3)),
                        mod_area=0.0,
                        n_expolys=int(m.group(4)),
                        sup_bb_min_x=float(m.group(6)),
                        sup_bb_min_y=float(m.group(7)),
                        sup_bb_max_x=float(m.group(8)),
                        sup_bb_max_y=float(m.group(9)),
                        mod_bb_min_x=0.0,
                        mod_bb_min_y=0.0,
                        mod_bb_max_x=0.0,
                        mod_bb_max_y=0.0,
                    )
                    result.layers.append(ld)

            # Parse summary
            m = re.match(r"layers_with_fills:\s*(\d+)", line)
            if m:
                result.n_support_layers = int(m.group(1))
            m = re.match(r"total_entities:\s*(\d+)", line)
            if m:
                result.total_entities = int(m.group(1))
            if "continuity: PASS" in line:
                result.continuity = True

    return result


def evaluate(result: ValidationResult, verbose: bool = False) -> bool:
    """Run geometric checks on parsed validation data. Returns True if all pass."""
    checks = {}

    # Check 1: Support exists
    result.support_exists = len(result.layers) > 0 and result.total_entities > 0
    checks["support_exists"] = result.support_exists

    if not result.layers:
        if verbose:
            print("  No support layers found — all checks FAIL")
        return False

    # Check 2: Support starts at low Y_virt (near belt surface at Y=0)
    first_layer = result.layers[0]
    result.support_at_low_y = first_layer.sup_bb_min_y < 1.0  # within 1mm of belt
    checks["support_at_low_y"] = result.support_at_low_y

    # Check 3: Support is BELOW/BESIDE model
    # For void-fill: support starts at belt (Y=0) and doesn't extend past model top.
    # For Option A: support max_y < model min_y (support is strictly below).
    # Accept either: sup_max_y <= mod_min_y+1 (below) OR sup_min_y < 0.5 (touches belt).
    below_count = 0
    total_with_model = 0
    for ld in result.layers:
        if ld.mod_area > 0:
            total_with_model += 1
            below = ld.sup_bb_max_y <= ld.mod_bb_min_y + 1.0  # strictly below
            belt_void = ld.sup_bb_min_y < 0.5 and ld.sup_bb_max_y <= ld.mod_bb_max_y + 1.0  # void-fill
            if below or belt_void:
                below_count += 1
    if total_with_model > 0:
        below_ratio = below_count / total_with_model
        result.support_below_model = below_ratio > 0.8  # 80% of layers
        checks["support_below_model"] = result.support_below_model
        if verbose:
            print(f"  support_below_model: {below_count}/{total_with_model} = {below_ratio:.2f}")
    else:
        checks["support_below_model"] = False

    # Check 4: Support area grows monotonically (or near-monotonically)
    areas = [ld.sup_area for ld in result.layers]
    if len(areas) > 2:
        # Allow 5% local decreases (noise tolerance)
        violations = 0
        for i in range(1, len(areas)):
            if areas[i] < areas[i-1] * 0.95:
                violations += 1
        result.support_grows_monotonic = violations <= len(areas) * 0.1
        checks["support_grows_monotonic"] = result.support_grows_monotonic
        if verbose:
            print(f"  monotonic_violations: {violations}/{len(areas)}")

    # Check 5: Continuity (from validation file)
    checks["continuity"] = result.continuity

    # Check 6: Support X range matches model X range (within 2mm margin for void-fill)
    x_match_count = 0
    for ld in result.layers:
        if abs(ld.sup_bb_min_x - ld.mod_bb_min_x) < 2.0 and abs(ld.sup_bb_max_x - ld.mod_bb_max_x) < 2.0:
            x_match_count += 1
    x_match = x_match_count / len(result.layers) > 0.8 if result.layers else False
    checks["x_alignment"] = x_match

    # Print results
    all_pass = True
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if verbose or not passed:
            print(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    return all_pass


def main():
    model = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else DEFAULT_MODEL
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    model = os.path.abspath(model)
    if not os.path.exists(model):
        print(f"ERROR: Model not found: {model}")
        sys.exit(2)

    print(f"Model: {os.path.basename(model)}")
    print(f"Slicer: {SLICER}")

    # Step 1: Slice
    print("\n--- SLICING ---")
    cli_ok = run_slicer(model, verbose)
    if not cli_ok:
        print("RESULT: CLI_CRASH")
        sys.exit(2)
    print("CLI: OK (exit 0)")

    # Step 2: Parse validation
    print("\n--- PARSING ---")
    result = parse_validation()
    if result is None:
        print("ERROR: No validation file at", VALIDATION_FILE)
        sys.exit(2)
    print(f"Layers: {result.n_layers}, Support layers: {len(result.layers)}, Entities: {result.total_entities}")

    if result.layers:
        first = result.layers[0]
        last = result.layers[-1]
        print(f"First support: L{first.index} z={first.z:.2f} area={first.sup_area:.1f} bb_y=[{first.sup_bb_min_y:.2f},{first.sup_bb_max_y:.2f}]")
        print(f"Last  support: L{last.index} z={last.z:.2f} area={last.sup_area:.1f} bb_y=[{last.sup_bb_min_y:.2f},{last.sup_bb_max_y:.2f}]")

    # Step 3: Evaluate
    print("\n--- EVALUATION ---")
    all_pass = evaluate(result, verbose=True)

    print(f"\nRESULT: {'ALL_PASS' if all_pass else 'ISSUES_DETECTED'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
