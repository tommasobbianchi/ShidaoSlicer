#!/usr/bin/env python3
"""
Tree-supports harness (A4 v1).

Runs validation/support_preprocess.py on the three tree fixtures and asserts
the per-fixture log signatures match expectations. Also runs a regression
check confirming that without --tree the default box-column path is taken.

Pure log-line scraping — keeps the test cheap and decoupled from 3MF
internals (those are exercised by the existing belt_pipeline_test).

Usage:
    python3 validation/tests/tree/test_tree.py

Returns 0 if every assertion passes, 1 otherwise.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PREPROC   = REPO_ROOT / "validation" / "support_preprocess.py"
FIXT_DIR  = Path(__file__).resolve().parent

TREE_LINE_RE = re.compile(
    r"Support tree \(local space\): (\d+) group\(s\) from (\d+) region\(s\)")
COUNTS_RE    = re.compile(r"trunk-only: (\d+), trunk\+leaf: (\d+)")
BOX_LINE_RE  = re.compile(r"Support boxes \(local space\): (\d+) region\(s\)")


def run(extra_args: list[str], fixture: str, out_3mf: str) -> str:
    cmd = ["python3", str(PREPROC),
           str(FIXT_DIR / fixture), "-o", out_3mf, *extra_args]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(
            f"preprocess failed (rc={res.returncode}):\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stdout tail: {res.stdout[-400:]}\n"
            f"  stderr tail: {res.stderr[-400:]}")
    return res.stdout


def expect_tree(stdout: str, groups: int, regions: int,
                trunk_only: int, with_leaf: int, label: str) -> None:
    m = TREE_LINE_RE.search(stdout)
    if not m:
        raise AssertionError(
            f"{label}: missing 'Support tree' line in stdout\n{stdout[-400:]}")
    g, r = int(m.group(1)), int(m.group(2))
    if (g, r) != (groups, regions):
        raise AssertionError(
            f"{label}: groups/regions mismatch -- "
            f"expected ({groups}, {regions}), got ({g}, {r})")
    m2 = COUNTS_RE.search(stdout)
    if not m2:
        raise AssertionError(
            f"{label}: missing 'trunk-only / trunk+leaf' line\n{stdout[-400:]}")
    to, wl = int(m2.group(1)), int(m2.group(2))
    if (to, wl) != (trunk_only, with_leaf):
        raise AssertionError(
            f"{label}: counts mismatch -- "
            f"expected trunk-only={trunk_only}, trunk+leaf={with_leaf}, "
            f"got trunk-only={to}, trunk+leaf={wl}")
    print(f"  PASS  {label}: groups={g} regions={r} "
          f"trunk-only={to} trunk+leaf={wl}")


def expect_box(stdout: str, regions: int, label: str) -> None:
    if "Support tree" in stdout:
        raise AssertionError(
            f"{label}: tree path was taken when --tree was NOT passed")
    m = BOX_LINE_RE.search(stdout)
    if not m:
        raise AssertionError(
            f"{label}: missing 'Support boxes' line\n{stdout[-400:]}")
    r = int(m.group(1))
    if r != regions:
        raise AssertionError(
            f"{label}: regions mismatch -- expected {regions}, got {r}")
    print(f"  PASS  {label}: box path, regions={r}")


def main() -> int:
    cases = [
        # Tree path checks
        ("single_overhang.stl", ["--tree"], "/tmp/tt_single.3mf",
         lambda out: expect_tree(out, 1, 1, 0, 1, "single_overhang --tree")),
        ("multi_far.stl",       ["--tree"], "/tmp/tt_far.3mf",
         lambda out: expect_tree(out, 2, 2, 0, 2, "multi_far --tree")),
        ("multi_close.stl",     ["--tree"], "/tmp/tt_close_def.3mf",
         lambda out: expect_tree(out, 2, 2, 0, 2,
                                 "multi_close --tree (default merge=2)")),
        ("multi_close.stl",     ["--tree", "--tree-merge-radius", "5"],
         "/tmp/tt_close_merge.3mf",
         lambda out: expect_tree(out, 1, 2, 0, 1,
                                 "multi_close --tree --tree-merge-radius=5")),
        # Regression: default must still be box columns
        ("single_overhang.stl", [], "/tmp/tt_box_default.3mf",
         lambda out: expect_box(out, 1, "single_overhang (default = box)")),
        ("multi_far.stl",       [], "/tmp/tt_box_far.3mf",
         lambda out: expect_box(out, 2, "multi_far (default = box)")),
    ]

    fails = 0
    for fixture, args, out_3mf, check in cases:
        try:
            stdout = run(args, fixture, out_3mf)
            check(stdout)
        except (AssertionError, RuntimeError) as e:
            print(f"  FAIL  {e}")
            fails += 1

    print()
    if fails:
        print(f"== {fails} of {len(cases)} cases FAILED")
        return 1
    print(f"== all {len(cases)} cases PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
