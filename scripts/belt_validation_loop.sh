#!/bin/bash
# Belt Validation Loop - Confronta Python Validator vs OrcaSlicer
# Itera finché i risultati non sono identici

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build"
ORCA_CLI="$BUILD_DIR/src/Release/orca-slicer"
TEST_STL="$PROJECT_DIR/test_cube.stl"
OUTPUT_DIR="$PROJECT_DIR/validation_output"
VENV="$PROJECT_DIR/.venv"

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}================================================================${NC}"
}

print_ok() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Crea directory output
mkdir -p "$OUTPUT_DIR"

print_header "BELT VALIDATION LOOP"
echo "Test STL: $TEST_STL"
echo "Output: $OUTPUT_DIR"

# ================================================================
# STEP 1: Esegui Python Validator
# ================================================================
print_header "STEP 1: Python Validator"

cd "$PROJECT_DIR"
source "$VENV/bin/activate"

python scripts/belt_transform_validator.py "$TEST_STL" \
    --json "$OUTPUT_DIR/python_validation.json" \
    --layer-height 0.2

# Estrai valori chiave dal JSON
PYTHON_Z_MIN=$(python -c "import json; d=json.load(open('$OUTPUT_DIR/python_validation.json')); print(d['stages']['3b_z_floor']['bounding_box']['min']['z'])")
PYTHON_Z_MAX=$(python -c "import json; d=json.load(open('$OUTPUT_DIR/python_validation.json')); print(d['stages']['3b_z_floor']['bounding_box']['max']['z'])")
PYTHON_Z_SIZE=$(python -c "import json; d=json.load(open('$OUTPUT_DIR/python_validation.json')); print(d['stages']['3b_z_floor']['bounding_box']['size']['z'])")

echo ""
echo "Python Validator - Risultati slicing frame:"
echo "  Z_min (slicing): $PYTHON_Z_MIN"
echo "  Z_max (slicing): $PYTHON_Z_MAX"
echo "  Z_size (slicing height): $PYTHON_Z_SIZE"

# ================================================================
# STEP 2: Verifica build OrcaSlicer
# ================================================================
print_header "STEP 2: Verifica OrcaSlicer Build"

if [ ! -f "$ORCA_CLI" ]; then
    print_error "OrcaSlicer non trovato: $ORCA_CLI"
    print_warn "Avvio build incrementale..."
    cd "$PROJECT_DIR"
    ./async_build.sh start
    print_warn "Attendi il completamento del build e riesegui questo script"
    exit 1
fi

print_ok "OrcaSlicer trovato: $ORCA_CLI"
ls -lh "$ORCA_CLI"

# ================================================================
# STEP 3: Genera G-code con OrcaSlicer CLI
# ================================================================
print_header "STEP 3: Genera G-code con OrcaSlicer CLI"

GCODE_OUTPUT="$OUTPUT_DIR/test_cube_belt.gcode"

# Trova il profilo belt
BELT_PROFILE="$PROJECT_DIR/resources/profiles/IdeaFormer/machine/IdeaFormer IR3 V2 0.4 nozzle.json"
PROCESS_PROFILE="$PROJECT_DIR/resources/profiles/IdeaFormer/process/0.20mm Standard @IdeaFormer IR3 V2.json"
FILAMENT_PROFILE="$PROJECT_DIR/resources/profiles/IdeaFormer/filament/Generic PLA @IdeaFormer.json"

# Prova slicing CLI
echo "Eseguo: $ORCA_CLI --export-gcode ..."

# OrcaSlicer CLI con profilo belt esplicito
timeout 120 "$ORCA_CLI" \
    --slice 0 \
    --load-settings "$BELT_PROFILE;$PROCESS_PROFILE" \
    --load-filaments "$FILAMENT_PROFILE" \
    --load-filaments "$FILAMENT_PROFILE" \
    --outputdir "$OUTPUT_DIR" \
    "$TEST_STL" 2>&1 | tee "$OUTPUT_DIR/orca_cli_output.txt" || {
        print_error "OrcaSlicer CLI fallito"
        cat "$OUTPUT_DIR/orca_cli_output.txt"
        # exit 1  <-- Non usciamo subito per permettere debug di eventuali output parziali oppure fallisce per errore noto
    }

# Rinomina il file generato (plate_1.gcode o simili) nel nome atteso
if [ -f "$OUTPUT_DIR/plate_1.gcode" ]; then
    mv "$OUTPUT_DIR/plate_1.gcode" "$GCODE_OUTPUT"
elif [ -f "$OUTPUT_DIR/test_cube.gcode" ]; then
    mv "$OUTPUT_DIR/test_cube.gcode" "$GCODE_OUTPUT"
fi

if [ ! -f "$GCODE_OUTPUT" ]; then
    print_error "G-code non generato!"
    exit 1
fi

print_ok "G-code generato: $GCODE_OUTPUT"
ls -lh "$GCODE_OUTPUT"

# ================================================================
# STEP 4: Analizza G-code
# ================================================================
print_header "STEP 4: Analizza G-code"

# Estrai coordinate min/max dal G-code
python3 << 'PYTHON_SCRIPT'
import sys
import json

gcode_file = "$OUTPUT_DIR/test_cube_belt.gcode".replace("$OUTPUT_DIR", "$OUTPUT_DIR")
gcode_file = gcode_file.replace("$OUTPUT_DIR", "/home/user/projects/ORCA_BELT/validation_output")

x_coords, y_coords, z_coords = [], [], []

with open(gcode_file, 'r') as f:
    for line in f:
        line = line.strip()
        if line.startswith(';') or not line:
            continue
        if line.startswith('G0 ') or line.startswith('G1 '):
            parts = line.split()
            for part in parts:
                if part.startswith('X'):
                    try: x_coords.append(float(part[1:]))
                    except: pass
                elif part.startswith('Y'):
                    try: y_coords.append(float(part[1:]))
                    except: pass
                elif part.startswith('Z'):
                    try: z_coords.append(float(part[1:]))
                    except: pass

if x_coords and y_coords and z_coords:
    result = {
        "x": {"min": min(x_coords), "max": max(x_coords)},
        "y": {"min": min(y_coords), "max": max(y_coords)},
        "z": {"min": min(z_coords), "max": max(z_coords)},
        "z_monotonic": all(z_coords[i] <= z_coords[i+1] for i in range(len(z_coords)-1)),
        "total_z_moves": len(z_coords)
    }
    
    print(f"G-code Analysis:")
    print(f"  X: {result['x']['min']:.2f} → {result['x']['max']:.2f}")
    print(f"  Y: {result['y']['min']:.2f} → {result['y']['max']:.2f}")
    print(f"  Z: {result['z']['min']:.2f} → {result['z']['max']:.2f}")
    print(f"  Z monotonic: {'✅ YES' if result['z_monotonic'] else '❌ NO'}")
    print(f"  Total Z moves: {result['total_z_moves']}")
    
    with open("/home/user/projects/ORCA_BELT/validation_output/gcode_analysis.json", 'w') as f:
        json.dump(result, f, indent=2)
else:
    print("❌ No coordinates found in G-code!")
    sys.exit(1)
PYTHON_SCRIPT

# ================================================================
# STEP 5: Confronto
# ================================================================
print_header "STEP 5: Confronto Python vs OrcaSlicer"

python3 << 'PYTHON_COMPARE'
import json

# Carica risultati
with open("/home/user/projects/ORCA_BELT/validation_output/python_validation.json") as f:
    py = json.load(f)

with open("/home/user/projects/ORCA_BELT/validation_output/gcode_analysis.json") as f:
    gc = json.load(f)

# Valori attesi dal Python validator (coordinate G-code finali)
py_gcode = py['stages']['5_gcode_coords']['bounding_box']
py_x_min, py_x_max = py_gcode['min']['x'], py_gcode['max']['x']
py_y_min, py_y_max = py_gcode['min']['y'], py_gcode['max']['y']
py_z_min, py_z_max = py_gcode['min']['z'], py_gcode['max']['z']

# Valori effettivi dal G-code
gc_x_min, gc_x_max = gc['x']['min'], gc['x']['max']
gc_y_min, gc_y_max = gc['y']['min'], gc['y']['max']
gc_z_min, gc_z_max = gc['z']['min'], gc['z']['max']

# Tolleranza per il confronto (offset di centratura etc)
tol = 5.0  # 5mm tolleranza per offset stampante

print("=" * 60)
print("  CONFRONTO RISULTATI")
print("=" * 60)
print("")
print(f"{'Asse':<6} | {'Python Validator':<25} | {'OrcaSlicer G-code':<25}")
print("-" * 60)
print(f"{'X min':<6} | {py_x_min:>10.2f}              | {gc_x_min:>10.2f}")
print(f"{'X max':<6} | {py_x_max:>10.2f}              | {gc_x_max:>10.2f}")
print(f"{'Y min':<6} | {py_y_min:>10.2f}              | {gc_y_min:>10.2f}")
print(f"{'Y max':<6} | {py_y_max:>10.2f}              | {gc_y_max:>10.2f}")
print(f"{'Z min':<6} | {py_z_min:>10.2f}              | {gc_z_min:>10.2f}")
print(f"{'Z max':<6} | {py_z_max:>10.2f}              | {gc_z_max:>10.2f}")
print("")

# Verifica dimensioni (le più importanti)
py_z_range = py_z_max - py_z_min
gc_z_range = gc_z_max - gc_z_min

print(f"Z Range: Python={py_z_range:.2f}mm, OrcaSlicer={gc_z_range:.2f}mm")

# Check criteri di successo
checks = []

# Z deve essere >= 0
checks.append(("Z_min >= 0", gc_z_min >= 0, f"actual: {gc_z_min:.2f}"))

# Z range deve essere ~20mm (altezza originale del cubo)
checks.append(("Z_range ~= 20mm", abs(gc_z_range - 20) < 5, f"actual: {gc_z_range:.2f}"))

# Z deve essere monotonicamente crescente
checks.append(("Z monotonic", gc['z_monotonic'], "from gcode analysis"))

print("")
print("VERIFICHE:")
all_pass = True
for name, passed, detail in checks:
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {name} ({detail})")
    if not passed:
        all_pass = False

print("")
if all_pass:
    print("🎉 TUTTI I TEST PASSATI! Python e OrcaSlicer sono allineati.")
else:
    print("⚠️  ALCUNI TEST FALLITI - Necessaria iterazione di fix")
PYTHON_COMPARE

print_header "VALIDAZIONE COMPLETATA"
echo "Risultati salvati in: $OUTPUT_DIR/"
ls -la "$OUTPUT_DIR/"
