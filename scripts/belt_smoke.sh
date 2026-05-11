#!/bin/bash
# scripts/belt_smoke.sh — Belt pipeline regression smoke test (belt-26j)
#
# Catches R11 z_mach regressions across the full pipeline in <2 min by
# running TWO fixtures through preprocess → slice → gate, and asserting
# the cross-stage invariants encoded in docs/architecture/pipeline_sim.py.
#
# Exit codes:
#   0 — every fixture PASS (gate=PASS, every invariant OK)
#   1 — any fixture FAIL (gate=FAIL, or an invariant violated)
#   2 — any fixture WARN (gate=WARN, no FAILs)
#
# Pre-commit integration (optional):
#   In .git/hooks/pre-commit, add:
#     scripts/belt_smoke.sh --fast || exit $?
#
# Manual run:
#   scripts/belt_smoke.sh                      # full (both fixtures)
#   scripts/belt_smoke.sh --fast               # one fixture only
#   scripts/belt_smoke.sh fixture1.3mf ...     # custom fixtures
#
# Fixtures default to two existing belt-preset 3MFs:
#   - inverted_L.3mf   (single cantilever — exercises R7/R11 first-layer Y)
#   - Test_Supports.3mf (multi-overhang  — exercises detection + injection)
#
# Why not arc_bridge.stl per the issue: wrapping a bare STL into a belt
# 3MF would itself be brittle scaffolding and add ~30 lines of XML emission.
# The two fixtures above hit the same R11/R7/I1-I4 surface and are already
# self-contained 3MFs with the IdeaFormer belt preset baked in. Swap-in is
# a one-line FIXTURES= edit.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PREPROCESS="$PROJECT_DIR/validation/support_preprocess.py"
GATE="$PROJECT_DIR/validation/belt_gcode_gate.py"
ORCA_BIN="${ORCA_BIN:-$PROJECT_DIR/build/src/Release/orca-slicer}"
WORKDIR="${BELT_SMOKE_WORKDIR:-/tmp/belt_smoke_$$}"

FAST_MODE=0
ARGS=()
for a in "$@"; do
    case "$a" in
        --fast) FAST_MODE=1 ;;
        -h|--help) sed -n '2,30p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) ARGS+=("$a") ;;
    esac
done

if [ ${#ARGS[@]} -gt 0 ]; then
    FIXTURES=("${ARGS[@]}")
else
    FIXTURES=(
        "$PROJECT_DIR/inverted_L.3mf"
        "$PROJECT_DIR/Test_Supports.3mf"
    )
    [ $FAST_MODE -eq 1 ] && FIXTURES=("${FIXTURES[0]}")
fi

# ── Pre-flight ──────────────────────────────────────────────────────────
for f in "$PREPROCESS" "$GATE" "$ORCA_BIN"; do
    [ -x "$f" ] || [ -f "$f" ] || { echo "ABORT: missing $f"; exit 1; }
done
for f in "${FIXTURES[@]}"; do
    [ -f "$f" ] || { echo "ABORT: fixture not found: $f"; exit 1; }
done

mkdir -p "$WORKDIR"
trap 'rm -rf "$WORKDIR"' EXIT

TOTAL_PASS=0
TOTAL_WARN=0
TOTAL_FAIL=0
START_TIME=$(date +%s)

echo "═══════════════════════════════════════════════════════════════"
echo "  BELT PIPELINE SMOKE TEST (belt-26j)"
echo "  Binary:    $ORCA_BIN"
echo "  Fixtures:  ${#FIXTURES[@]}"
echo "  Workdir:   $WORKDIR"
echo "═══════════════════════════════════════════════════════════════"

# Per-fixture pipeline
for FIXTURE in "${FIXTURES[@]}"; do
    NAME=$(basename "$FIXTURE" .3mf)
    FIX_DIR="$WORKDIR/$NAME"
    mkdir -p "$FIX_DIR"
    COMPOUND="$FIX_DIR/compound.3mf"
    GCODE_DIR="$FIX_DIR/gcode"
    mkdir -p "$GCODE_DIR"

    echo ""
    echo "─── Fixture: $NAME ────────────────────────────────────────────"

    F_PASS=0; F_WARN=0; F_FAIL=0
    check() {
        # $1=label, $2=PASS|WARN|FAIL, $3=detail
        case "$2" in
            PASS) echo "    ✓ $1 — $3"; F_PASS=$((F_PASS+1)) ;;
            WARN) echo "    ⚠ $1 — $3"; F_WARN=$((F_WARN+1)) ;;
            FAIL) echo "    ✗ $1 — $3"; F_FAIL=$((F_FAIL+1)) ;;
        esac
    }

    # ── Step 1: preprocess (proxy for inject_volumes from Plater.cpp) ───
    if python3 "$PREPROCESS" "$FIXTURE" -o "$COMPOUND" \
            > "$FIX_DIR/preprocess.log" 2>&1; then
        check "Stage 3+3b preprocess produces compound.3mf" PASS \
              "$(wc -c < "$COMPOUND" | tr -d ' ') bytes"
    else
        check "Stage 3+3b preprocess produces compound.3mf" FAIL \
              "see $FIX_DIR/preprocess.log"
        TOTAL_FAIL=$((TOTAL_FAIL + F_FAIL))
        continue
    fi

    # ── Invariant checks on compound.3mf (I1, I2, I4 from pipeline_sim) ─
    python3 - "$COMPOUND" "$FIXTURE" > "$FIX_DIR/invariants.txt" 2>&1 <<'PYINV' || true
import json, re, sys, zipfile
from xml.etree import ElementTree as ET

compound, original = sys.argv[1], sys.argv[2]

def read_zip_member(z, name):
    try:    return z.read(name).decode("utf-8", errors="replace")
    except KeyError: return ""

# ---- Parse <part> entries; identify support/wedge by exact name match.
def parse_parts(zf):
    txt = read_zip_member(zf, "Metadata/model_settings.config")
    parts = []
    for part_m in re.finditer(r'<part[^>]*\bid="(\d+)"[^>]*>(.*?)</part>',
                              txt, re.DOTALL):
        pid, body = part_m.group(1), part_m.group(2)
        mat = re.search(r'<metadata\s+key="matrix"\s+value="([^"]+)"', body)
        nam = re.search(r'<metadata\s+key="name"\s+value="([^"]+)"', body)
        if mat and nam:
            try:
                vec = [float(x) for x in mat.group(1).split()]
            except ValueError:
                continue
            parts.append({"id": pid, "name": nam.group(1),
                          "matrix_str": mat.group(1).strip(),
                          "matrix": vec})
    return parts

with zipfile.ZipFile(compound) as zf:
    parts = parse_parts(zf)
    proj  = read_zip_member(zf, "Metadata/project_settings.config")

# ---- I1: matrices align across model + support + wedge (FP tolerance 1e-3 mm)
def mat_eq(a, b, tol=1e-3):
    return len(a) == len(b) and all(abs(x - y) < tol for x, y in zip(a, b))

INJECTED_NAMES = {"support", "support_wedge"}
model_parts = [p for p in parts if p["name"] not in INJECTED_NAMES]
inj_parts   = [p for p in parts if p["name"] in INJECTED_NAMES]

if not parts:
    print("I1 FAIL no <part> entries in compound model_settings.config")
elif not inj_parts:
    print("I1 WARN no injected (support/wedge) parts — ok ONLY if input had "
          "no overhangs; nothing to compare")
elif not model_parts:
    print("I1 FAIL injected parts present but no model part found")
else:
    base = model_parts[0]["matrix"]
    bad = [p for p in inj_parts if not mat_eq(p["matrix"], base)]
    if not bad:
        names = ", ".join(p["name"] for p in inj_parts)
        print(f"I1 PASS model + {len(inj_parts)} injected parts ({names}) "
              f"share matrix within 1e-3 mm of '{model_parts[0]['name']}'")
    else:
        diffs = ", ".join(
            f"{p['name']} Δmax="
            f"{max(abs(x-y) for x,y in zip(p['matrix'], base)):.4g}"
            for p in bad)
        print(f"I1 FAIL {len(bad)}/{len(inj_parts)} injected parts diverge "
              f"from model matrix (belt-zyt regression class): {diffs}")

# ---- I2: support reaches as low as the model in shared local frame.
#       I1 already ensures support+wedge share the model's <part> matrix,
#       so comparing local z_min of support vs model is the right gauge.
#       Use exact filename match — substring is unsafe ("Test_Supports" has
#       "supports" in it).
INJECTED_FILES = {"3D/Objects/support_part.model",
                  "3D/Objects/support_wedge.model"}

def mesh_z_min(zf, names):
    zmin = None
    for n in names:
        try:
            xml = zf.read(n).decode("utf-8", errors="replace")
        except KeyError:
            continue
        zs = [float(m) for m in
              re.findall(r'<vertex[^>]*\bz="([-\d.eE+]+)"', xml)]
        if zs:
            zmin_here = min(zs)
            zmin = zmin_here if zmin is None else min(zmin, zmin_here)
    return zmin

try:
    with zipfile.ZipFile(compound) as zf:
        all_objects = [n for n in zf.namelist()
                       if n.startswith("3D/Objects/") and n.endswith(".model")]
        sup_names = [n for n in all_objects if n in INJECTED_FILES]
        mdl_names = [n for n in all_objects if n not in INJECTED_FILES]
        sup_z = mesh_z_min(zf, sup_names)
        mdl_z = mesh_z_min(zf, mdl_names)
except Exception as e:
    print(f"I2 FAIL exception reading meshes: {e}")
    sup_z, mdl_z = "ERR", "ERR"

if sup_z == "ERR":
    pass
elif sup_z is None:
    print("I2 WARN no support mesh in compound (ok ONLY if input had no overhangs)")
elif mdl_z is None:
    print("I2 FAIL model mesh not located in compound — cannot compare")
else:
    delta = sup_z - mdl_z   # negative or near-zero = good (support reaches keel)
    if delta < 0.05:
        print(f"I2 PASS support local-z_min ({sup_z:.3f}) ≤ model local-z_min "
              f"({mdl_z:.3f}) + 0.05; delta={delta:+.3f}mm — keel touches base")
    elif delta < 0.5:
        print(f"I2 WARN support local-z_min ({sup_z:.3f}) above model's by "
              f"{delta:+.3f}mm (>0.05 ≤ 0.5) — weak first-layer adhesion risk")
    else:
        print(f"I2 FAIL support local-z_min ({sup_z:.3f}) above model's by "
              f"{delta:+.3f}mm (>0.5) — support hangs in air, not bedded")

# ---- I4: enable_support=0 in compound's project_settings (Stage 3 post-inject)
m = re.search(r'"enable_support"\s*:\s*"([01]?)"', proj)
if not m:
    print("I4 WARN enable_support key absent from compound project_settings")
else:
    v = m.group(1)
    if v == "0":
        print("I4 PASS enable_support=0 in compound (native gen suppressed)")
    else:
        print(f"I4 FAIL enable_support={v!r} in compound — native support "
              "generator will fire on injected volumes (broken on belt)")
PYINV

    while IFS= read -r line; do
        case "$line" in
            "I1 PASS"*) check "I1 injected-volume matrices aligned" PASS "${line#I1 PASS }" ;;
            "I1 WARN"*) check "I1 injected-volume matrices aligned" WARN "${line#I1 WARN }" ;;
            "I1 FAIL"*) check "I1 injected-volume matrices aligned" FAIL "${line#I1 FAIL }" ;;
            "I2 PASS"*) check "I2 support keel reaches Z=0"          PASS "${line#I2 PASS }" ;;
            "I2 WARN"*) check "I2 support keel reaches Z=0"          WARN "${line#I2 WARN }" ;;
            "I2 FAIL"*) check "I2 support keel reaches Z=0"          FAIL "${line#I2 FAIL }" ;;
            "I4 PASS"*) check "I4 enable_support=0 post-inject"      PASS "${line#I4 PASS }" ;;
            "I4 WARN"*) check "I4 enable_support=0 post-inject"      WARN "${line#I4 WARN }" ;;
            "I4 FAIL"*) check "I4 enable_support=0 post-inject"      FAIL "${line#I4 FAIL }" ;;
        esac
    done < "$FIX_DIR/invariants.txt"

    # ── Step 2: slice ────────────────────────────────────────────────────
    SLICE_T0=$(date +%s)
    "$ORCA_BIN" --slice 1 --outputdir "$GCODE_DIR" "$COMPOUND" \
        > "$FIX_DIR/slice.log" 2>&1 || true
    SLICE_DT=$(( $(date +%s) - SLICE_T0 ))
    GCODE=$(find "$GCODE_DIR" -maxdepth 2 -name "*.gcode" -type f | head -1)
    if [ -n "$GCODE" ] && [ -s "$GCODE" ]; then
        check "Stage 4 slicer produces gcode" PASS \
              "$(basename "$GCODE") in ${SLICE_DT}s"
    else
        check "Stage 4 slicer produces gcode" FAIL \
              "no gcode in $GCODE_DIR after ${SLICE_DT}s — see $FIX_DIR/slice.log"
        TOTAL_FAIL=$((TOTAL_FAIL + F_FAIL))
        TOTAL_PASS=$((TOTAL_PASS + F_PASS))
        TOTAL_WARN=$((TOTAL_WARN + F_WARN))
        continue
    fi

    # ── Step 3: gate (R1-R11, the safety-critical layer; I3 covered by R11) ─
    # Gate defaults to --upload disabled, so just calling it is read-only.
    python3 "$GATE" "$GCODE" > "$FIX_DIR/gate.log" 2>&1
    GATE_EXIT=$?
    case $GATE_EXIT in
        0) check "Stage 5 gate (R1-R11; covers I3 inclined-Z)" PASS "PASS" ;;
        2) R11_BAD=$(grep -E "\[R11" "$FIX_DIR/gate.log" | grep -E "FAIL|BLOCK" || true)
           if [ -n "$R11_BAD" ]; then
               check "Stage 5 gate (R1-R11; covers I3 inclined-Z)" FAIL \
                     "R11 violation in WARN report: $R11_BAD"
           else
               check "Stage 5 gate (R1-R11; covers I3 inclined-Z)" WARN \
                     "WARN (R11 ok; non-fatal warnings — see $FIX_DIR/gate.log)"
           fi ;;
        *) FAIL_LINES=$(grep -E "\[R[0-9]+" "$FIX_DIR/gate.log" | grep FAIL | head -3 || true)
           check "Stage 5 gate (R1-R11; covers I3 inclined-Z)" FAIL \
                 "exit=$GATE_EXIT; $FAIL_LINES" ;;
    esac

    echo "    └─ fixture totals: $F_PASS PASS, $F_WARN WARN, $F_FAIL FAIL"
    TOTAL_PASS=$((TOTAL_PASS + F_PASS))
    TOTAL_WARN=$((TOTAL_WARN + F_WARN))
    TOTAL_FAIL=$((TOTAL_FAIL + F_FAIL))
done

ELAPSED=$(( $(date +%s) - START_TIME ))
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  TOTAL: $TOTAL_PASS PASS · $TOTAL_WARN WARN · $TOTAL_FAIL FAIL"
echo "  Time:  ${ELAPSED}s (budget 120s)"
if [ $TOTAL_FAIL -gt 0 ]; then
    echo "  RESULT: FAIL"
    EXIT_CODE=1
elif [ $TOTAL_WARN -gt 0 ]; then
    echo "  RESULT: WARN"
    EXIT_CODE=2
else
    echo "  RESULT: PASS"
    EXIT_CODE=0
fi
echo "═══════════════════════════════════════════════════════════════"
exit $EXIT_CODE
