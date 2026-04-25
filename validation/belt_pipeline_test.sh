#!/bin/bash
# Belt Pipeline Regression Test
#
# Full end-to-end: preprocess supports → slice → validate gcode
# Tests that supports touch ground, gcode has no Z oscillations,
# no negative Z, gantry hops present, extrusions are XY-only.
#
# Usage:
#   bash validation/belt_pipeline_test.sh [model.3mf]
#   Default model: inverted_L.3mf

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

ORCA_CLI="$PROJECT_DIR/agent-harness/.venv/bin/cli-anything-orcaslicer"
PREPROCESS="$SCRIPT_DIR/support_preprocess.py"
VALIDATE="$SCRIPT_DIR/belt_gcode_gate.py"
ORCA_BIN="$PROJECT_DIR/build/src/Release/orca-slicer"
WORKDIR="/tmp/belt_pipeline_test_$$"
INPUT="${1:-$PROJECT_DIR/inverted_L.3mf}"

PASS=0
FAIL=0
WARN=0

check() {
    local name="$1" result="$2"
    if [ "$result" = "PASS" ]; then
        echo "  ✓ $name"
        PASS=$((PASS + 1))
    elif [ "$result" = "WARN" ]; then
        echo "  ⚠ $name"
        WARN=$((WARN + 1))
    else
        echo "  ✗ $name"
        FAIL=$((FAIL + 1))
    fi
}

cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

mkdir -p "$WORKDIR"

echo "═══════════════════════════════════════════════════"
echo "  BELT PIPELINE REGRESSION TEST"
echo "  Model: $(basename "$INPUT")"
echo "  Work:  $WORKDIR"
echo "═══════════════════════════════════════════════════"

# ── Step 1: Preprocess supports ──────────────────────────────────────────
echo ""
echo "── Step 1: Preprocess supports (standard gravity) ──"
cp "$INPUT" "$WORKDIR/input.3mf"
python3 "$PREPROCESS" "$WORKDIR/input.3mf" -o "$WORKDIR/compound.3mf" --json \
    > "$WORKDIR/preprocess.json" 2>&1

SUPPORT_COUNT=$(python3 -c "
import json, re
with open('$WORKDIR/preprocess.json') as f:
    text = f.read()
# Find the JSON block (starts with { on its own line)
m = re.search(r'^\{.*?\n\}', text, re.MULTILINE | re.DOTALL)
if m:
    d = json.loads(m.group())
    s = d.get('support')
    print(s['faces'] if s else 0)
else:
    print(0)
" 2>/dev/null || echo "0")
check "Support generated (faces=$SUPPORT_COUNT)" "$([ "${SUPPORT_COUNT:-0}" -gt 0 ] && echo PASS || echo FAIL)"

# ── Step 2: Verify supports touch Z=0 ───────────────────────────────────
echo ""
echo "── Step 2: Verify supports reach build plate ──"
python3 "$PREPROCESS" "$WORKDIR/input.3mf" --support-only -o "$WORKDIR/support.stl" \
    > /dev/null 2>&1

GROUND_CHECK=$(python3 -c "
import trimesh
s = trimesh.load('$WORKDIR/support.stl', force='mesh')
z_min = s.vertices[:, 2].min()
z_max = s.vertices[:, 2].max()
print(f'z_min={z_min:.4f} z_max={z_max:.3f}')
print('PASS' if z_min < 0.01 else 'FAIL')
" 2>/dev/null)
Z_INFO=$(echo "$GROUND_CHECK" | head -1)
Z_RESULT=$(echo "$GROUND_CHECK" | tail -1)
check "Support touches Z=0 ($Z_INFO)" "$Z_RESULT"

# ── Step 3: Verify enable_support=0 in compound ─────────────────────────
echo ""
echo "── Step 3: Verify compound 3MF settings ──"
ES=$("$ORCA_CLI" --json project get-setting "$WORKDIR/compound.3mf" enable_support 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['value'])" 2>/dev/null || echo "?")
check "enable_support=0 in compound (got=$ES)" "$([ "$ES" = "0" ] && echo PASS || echo FAIL)"

# ── Step 4: Slice ────────────────────────────────────────────────────────
echo ""
echo "── Step 4: Slice with OrcaSlicer (headless) ──"
"$ORCA_BIN" --slice 1 --outputdir "$WORKDIR" "$WORKDIR/compound.3mf" > "$WORKDIR/slice.log" 2>&1 || true
GCODE=$(find "$WORKDIR" -name "*.gcode" -type f | head -1)
if [ -n "$GCODE" ]; then
    GSIZE=$(wc -c < "$GCODE")
    check "Gcode produced ($(basename "$GCODE"), ${GSIZE} bytes)" "PASS"
else
    check "Gcode produced" "FAIL"
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  RESULT: FAIL (slicing failed)"
    echo "═══════════════════════════════════════════════════"
    exit 1
fi

# ── Step 5: Belt gcode validation ────────────────────────────────────────
echo ""
echo "── Step 5: Belt G-code validation (9 rules) ──"
python3 "$VALIDATE" "$GCODE" > "$WORKDIR/validate.log" 2>&1 || true

# Parse individual rule results from validation output
while IFS= read -r line; do
    RULE=$(echo "$line" | grep -oE '\[R[0-9]+-[A-Z0-9-]+\]' || true)
    [ -z "$RULE" ] && continue
    if echo "$line" | grep -q "PASS"; then
        check "Rule $RULE" "PASS"
    elif echo "$line" | grep -q "WARN"; then
        check "Rule $RULE" "WARN"
    elif echo "$line" | grep -q "FAIL"; then
        check "Rule $RULE" "FAIL"
    fi
done < "$WORKDIR/validate.log"

# ── Step 6: Gcode analysis ──────────────────────────────────────────────
echo ""
echo "── Step 6: G-code analysis ──"
python3 - "$GCODE" << 'PYANALYZE'
import sys, re

with open(sys.argv[1]) as f:
    lines = f.readlines()

z_values, neg_z, z_only, ext_z, z_reversals = [], 0, 0, 0, 0
first_ext_y = None

for line in lines:
    line = line.strip()
    if not line or line.startswith(";") or not re.match(r"G[01]\s", line):
        continue

    has_x = bool(re.search(r"[^A-Z]?X", line))
    has_y = bool(re.search(r"[^A-Z]?Y", line))
    has_e = bool(re.search(r"[^A-Z]?E", line))
    zm = re.search(r"Z([-\d.]+)", line)

    if zm:
        z = float(zm.group(1))
        z_values.append(z)
        if z < 0: neg_z += 1
        if not has_x and not has_y and not has_e: z_only += 1
    if has_e and zm: ext_z += 1
    if has_e and first_ext_y is None:
        ym = re.search(r"Y([-\d.]+)", line)
        if ym: first_ext_y = float(ym.group(1))

if len(z_values) > 2:
    for i in range(2, len(z_values)):
        if (z_values[i] - z_values[i-1]) * (z_values[i-1] - z_values[i-2]) < -0.001:
            z_reversals += 1

results = [
    ("No negative Z", "PASS" if neg_z == 0 else "FAIL", f"count={neg_z}"),
    ("No Z-only moves", "PASS" if z_only == 0 else "FAIL", f"count={z_only}"),
    ("No Z oscillation", "PASS" if z_reversals == 0 else "FAIL", f"reversals={z_reversals}"),
    ("Extrusions XY-only", "PASS" if ext_z == 0 else "WARN", f"ext_with_z={ext_z}"),
]
if first_ext_y is not None:
    results.append(("First extrusion Y≈0", "PASS" if first_ext_y < 2 else "FAIL", f"Y={first_ext_y:.3f}"))
if z_values:
    results.append(("Z range valid", "PASS" if min(z_values) >= 0 else "FAIL",
                     f"[{min(z_values):.3f}, {max(z_values):.3f}]"))

for name, result, detail in results:
    print(f"{result} {name} ({detail})")
PYANALYZE

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo "  RESULT: $PASS PASS, $WARN WARN, $FAIL FAIL"
if [ $FAIL -gt 0 ]; then
    echo "  STATUS: FAIL"
    exit 1
elif [ $WARN -gt 0 ]; then
    echo "  STATUS: WARN (review warnings)"
    exit 2
else
    echo "  STATUS: ALL PASS"
    exit 0
fi
echo "═══════════════════════════════════════════════════"
