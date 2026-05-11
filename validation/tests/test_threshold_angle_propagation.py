#!/usr/bin/env python3
"""
Regression test for belt-a6m: support_threshold_angle propagates end-to-end
from the 3MF's Metadata/project_settings.config through the preprocessor's
detect_overhangs().

History: commit 0e7cb0fa7d wired Plater::export_3mf to serialize the edited
print preset into tmp_in.3mf, and support_preprocess.read_3mf_support_settings
to read support_threshold_angle out. This test guards against future
regressions in that chain.

Three independent checks:
  1. read_3mf_support_settings round-trips threshold_angle from a 3MF
     where project_settings.config was rewritten with an arbitrary value.
  2. The preprocessor's effective config matches that override (its log
     reports the value from "3MF" as the source).
  3. detect_overhangs() honours the threshold on a synthetic sphere mesh —
     count of flagged faces decreases monotonically as threshold rises.
     (Stock fixtures like inverted_L / Test_Supports are axis-aligned;
     their undersides have dot=1.0 with gravity, so they pass any
     threshold — that's a geometry artifact, not a propagation failure.)

Exit codes: 0 = PASS, 1 = FAIL.
"""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
import contextlib
from pathlib import Path

import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "Test_Supports.3mf"
PREPROCESS = REPO / "validation" / "support_preprocess.py"

sys.path.insert(0, str(REPO / "validation"))
from support_preprocess import read_3mf_support_settings, detect_overhangs  # noqa: E402


def _stage_variant(src: Path, dst: Path, threshold: float) -> None:
    shutil.copy(src, dst)
    with zipfile.ZipFile(dst, "r") as zin:
        data = {n: zin.read(n) for n in zin.namelist()}
    cfg = json.loads(data["Metadata/project_settings.config"].decode())
    cfg["support_threshold_angle"] = str(threshold)
    data["Metadata/project_settings.config"] = json.dumps(cfg, indent=2).encode()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, blob in data.items():
            zout.writestr(n, blob)


def _check_3mf_roundtrip(tmp: Path) -> list[str]:
    fails = []
    print("== Step 1: read_3mf_support_settings round-trip ==")
    for th in (15.0, 30.0, 45.0, 60.0):
        v = tmp / f"variant_th{int(th)}.3mf"
        _stage_variant(FIXTURE, v, th)
        got = read_3mf_support_settings(v).get("threshold_angle")
        status = "PASS" if got == th else "FAIL"
        print(f"  th={th:>5.1f}° → read back = {got!r}  [{status}]")
        if status == "FAIL":
            fails.append(f"step1 th={th}")
    return fails


def _check_preprocessor_log(tmp: Path) -> list[str]:
    fails = []
    print("\n== Step 2: preprocessor effective config matches override ==")
    for th in (15.0, 30.0, 45.0, 60.0):
        v = tmp / f"variant_th{int(th)}.3mf"
        out = tmp / f"out_th{int(th)}.3mf"
        r = subprocess.run(
            ["python3", str(PREPROCESS), str(v), "-o", str(out),
             "--wedge-layers", "0"],
            capture_output=True, text=True, timeout=180,
        )
        # Effective config block reports the chosen threshold_angle
        eff_val = None
        in_eff = False
        for line in r.stdout.splitlines():
            if "Effective config:" in line:
                in_eff = True
                continue
            if in_eff and line.strip().startswith("threshold_angle"):
                try:
                    eff_val = float(line.split("=", 1)[1].strip())
                except Exception:
                    pass
                break
        marker_3mf = (f"threshold_angle = {th}" in r.stdout
                      and "(from 3MF)" in r.stdout)
        status = "PASS" if (marker_3mf and eff_val == th) else "FAIL"
        print(f"  th={th:>5.1f}° → log_has_override={marker_3mf}  "
              f"eff={eff_val!r}  [{status}]")
        if status == "FAIL":
            fails.append(f"step2 th={th}")
    return fails


def _check_detector_responds_to_threshold() -> list[str]:
    fails = []
    print("\n== Step 3: detect_overhangs() count decreases as threshold rises ==")
    print("  fixture: synthetic sphere (continuous overhang angles)")
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=10.0)
    mesh.apply_translation([0, 0, 12.0])  # clear floor_z
    counts = {}
    for th in (5, 15, 30, 45, 60, 80):
        with contextlib.redirect_stdout(io.StringIO()):
            mask = detect_overhangs(mesh, threshold_angle=float(th),
                                    floor_z=0.1, min_area=0.5)
        counts[th] = int(mask.sum())
        print(f"  th={th:>3}° → {counts[th]:>4} overhang faces flagged")
    pairs = list(counts.items())
    for i in range(len(pairs) - 1):
        if pairs[i][1] < pairs[i + 1][1]:
            fails.append(f"step3 non-monotone at th={pairs[i][0]}→{pairs[i+1][0]}")
            print(f"  FAIL non-monotone: th={pairs[i][0]}={pairs[i][1]} "
                  f"< th={pairs[i+1][0]}={pairs[i+1][1]}")
    if pairs[0][1] == pairs[-1][1]:
        fails.append("step3 no differentiation")
        print(f"  FAIL: th={pairs[0][0]}° and th={pairs[-1][0]}° "
              f"both yield {pairs[0][1]} faces")
    return fails


def main() -> int:
    if not FIXTURE.exists():
        print(f"FAIL: fixture missing — {FIXTURE}")
        return 2
    if not PREPROCESS.exists():
        print(f"FAIL: preprocessor missing — {PREPROCESS}")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="belt_a6m_"))
    print(f"Staging in {tmp}\n")

    fails = []
    fails += _check_3mf_roundtrip(tmp)
    fails += _check_preprocessor_log(tmp)
    fails += _check_detector_responds_to_threshold()

    print()
    if fails:
        print(f"OVERALL: FAIL ({len(fails)} sub-checks failed)")
        for f in fails:
            print(f"  • {f}")
        print(f"  artifacts kept at: {tmp}")
        return 1
    print("OVERALL: PASS — threshold_angle propagates and discriminates "
          "(belt-a6m closed in 0e7cb0fa7d)")
    shutil.rmtree(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
