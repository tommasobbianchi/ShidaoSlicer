import subprocess
import os
import json
import math
import sys

# Configuration
SLICER_PATH = "./build/src/Release/orca-slicer"
IF_NOT_RELEASE = "./build/src/orca-slicer"
if not os.path.exists(SLICER_PATH):
    SLICER_PATH = IF_NOT_RELEASE

MODEL_PATH = "tests/data/20mm_cube.obj"
GCODE_PATH = "tests/test_support.gcode"

# Create JSON config
belt_config = {
    "belt_printer": "1",
    "belt_angle": "45.0",
    "belt_axis": "Y",
    "initial_layer_speed": "30",
    "outer_wall_speed": "60",
    "inner_wall_speed": "60",
    "travel_speed": "100",
    "layer_height": "0.2",
    "initial_layer_print_height": "0.2",
    "nozzle_diameter": ["0.4"],
    "filament_diameter": ["1.75"],
    "gcode_flavor": "klipper",
    "default_acceleration": "1000",
    "initial_layer_acceleration": "500",
    "printable_area": ["0,0", "200,0", "200,200", "0,200"],
    "filament_max_volumetric_speed": ["15"],
    "enable_pressure_advance": ["1"],
    "pressure_advance": ["0.04"],
    "initial_layer_infill_speed": "30",
    "wall_loops": "2",
    "fill_density": "10%",
    "top_shell_layers": "3",
    "bottom_shell_layers": "3",
    "initial_layer_print_temp": ["215"],
    "print_temp": ["210"],
    "bed_temperature": ["60"],
    "filament_type": ["PLA"],
    # Support settings
    "support_material": "1",
    "support_material_auto": "1",
    "support_type": "normal",
    "support_threshold_angle": "45",
}

# Add some required fields for Orca CLI
extra_settings = {
    "print_settings_id": "BeltTest",
    "printer_settings_id": "BeltPrinter",
    "filament_settings_id": ["BeltFilament"],
}
belt_config.update(extra_settings)

def save_json_config(config, name, base_type):
    full_config = {
        "type": base_type,
        "from": "system",
        "name": name,
    }
    # Add mandatory fields for machine
    if base_type == "machine":
        full_config.update({
            "printer_model": "Bambu Lab X1 Carbon",
            "printer_variant": "0.4",
            "default_print_profile": "0.20mm Standard @BBL X1C"
        })
    elif base_type == "process":
         full_config.update({
            "compatible_printers_condition": ""
        })
    elif base_type == "filament":
        full_config.update({
            "filament_id": "G001"
        })

    full_config.update(config)
    
    # Stringify everything
    final_config = {}
    for k, v in full_config.items():
        if isinstance(v, list):
            final_config[k] = ";".join(map(str, v))
        elif isinstance(v, bool):
            final_config[k] = "1" if v else "0"
        else:
            final_config[k] = str(v)
            
    path = f"tests/belt_support_{base_type}.json"
    with open(path, 'w') as f:
        json.dump(final_config, f, indent=4)
    return path

# Split configuration
machine_settings = {k: v for k, v in belt_config.items() if k in [
    "belt_printer", "belt_angle", "printable_area", "printable_height", 
    "nozzle_diameter", "gcode_flavor", "machine_start_gcode", "machine_end_gcode"
]}
process_settings = {k: v for k, v in belt_config.items() if k in [
    "layer_height", "initial_layer_print_height", "initial_layer_speed", 
    "line_width", "sparse_infill_density", "support_material", "support_material_auto", 
    "support_type", "support_threshold_angle"
]}
filament_settings = {k: v for k, v in belt_config.items() if k in [
    "nozzle_temperature", "nozzle_temperature_initial_layer"
]}

# Add other necessary settings to satisfy some checks if needed
process_settings.update({
    "wall_loops": "2",
    "top_shell_layers": "3",
    "bottom_shell_layers": "3",
    "sparse_infill_pattern": "grid",
    "skirt_loops": "0",
    "brim_width": "0"
})

filament_settings.update({
    "filament_type": "PLA",
    "filament_vendor": "Generic",
    "filament_cost": "20",
    "filament_density": "1.24"
})

machine_path = save_json_config(machine_settings, "Belt Machine", "machine")
process_path = save_json_config(process_settings, "Belt Process", "process")
filament_path = save_json_config(filament_settings, "Belt Filament", "filament")

print(f"Slicing {MODEL_PATH} with belt configs...")
# Run slicer

print(f"Slicing {MODEL_PATH} with belt configs...")
# Run slicer
cmd = [
    SLICER_PATH,
    "--debug", "5",
    "--load-settings", machine_path,
    "--load-settings", process_path,
    "--load-settings", filament_path,
    "--slice", "0",
    "--outputdir", "tests",
    MODEL_PATH
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Slicing failed!")
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)
except Exception as e:
    print(f"Error running slicer: {e}")
    sys.exit(1)

# Determine generated G-code path
# Slicer might output to plate_1.gcode or 20mm_cube.gcode
possible_names = ["plate_1.gcode", "20mm_cube.gcode", "test_support.gcode"]
found_path = None
for name in possible_names:
    p = os.path.join("tests", name)
    if os.path.exists(p):
        found_path = p
        break

if not found_path:
    print(f"G-code file not found! Checked: {possible_names}")
    print("Files in tests/:")
    print(os.listdir("tests"))
    sys.exit(1)

GCODE_PATH = found_path
print(f"Analyzing {GCODE_PATH} for support material...")
support_lines = 0
with open(GCODE_PATH, 'r') as f:
    for line in f:
        # Check for support type comments
        # Usually "; TYPE:Support material" or similar
        if "; TYPE:Support" in line:
            support_lines += 1
            print(f"Found support line: {line.strip()}")

if support_lines == 0:
    print("SUCCESS: No support material generated for cube on belt.")
else:
    print(f"FAILURE: {support_lines} lines of support material found.")
    # Assuming the cube is placed correctly on the belt, there should be none.
    sys.exit(1)
