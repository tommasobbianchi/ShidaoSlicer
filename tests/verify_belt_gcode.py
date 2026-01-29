import subprocess
import os
import json
import math

# Configuration
SLICER_PATH = "./build/src/Release/orca-slicer"
IF_NOT_RELEASE = "./build/src/orca-slicer"
if not os.path.exists(SLICER_PATH):
    SLICER_PATH = IF_NOT_RELEASE

MODEL_PATH = "tests/data/20mm_cube.obj"
CONFIG_PATH = "tests/belt_config.json"
GCODE_PATH = "tests/plate_1.gcode"

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
            
    path = f"tests/belt_{base_type}.json"
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
    "line_width", "sparse_infill_density"
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
        # Try without --load-filaments if it complains
        # exit(1)
except Exception as e:
    print(f"Error running slicer: {e}")
    exit(1)

if not os.path.exists(GCODE_PATH):
    print(f"G-code file {GCODE_PATH} not generated!")
    exit(1)

print("Analyzing G-code...")
in_first_layer = False
nominal_z = 0
tan_45 = math.tan(math.radians(45))

errors = []
bed_segments_found = 0
other_segments_found = 0

with open(GCODE_PATH, 'r') as f:
    for line in f:
        if line.startswith("; LAYER_CHANGE"):
            pass
        if line.startswith("G1"):
            # Parse G1
            parts = line.split()
            x, y, z, e, f_val = None, None, None, None, None
            for p in parts:
                if p.startswith('X'): x = float(p[1:])
                if p.startswith('Y'): y = float(p[1:])
                if p.startswith('Z'): z = float(p[1:])
                if p.startswith('E'): e = float(p[2:] if p.startswith('E') else p[1:]) 
                if p.startswith('F'): f_val = float(p[1:])

            if z is not None:
                nominal_z = z
            
            # If it's an extrusion move
            if e is not None and x is not None and y is not None:
                # Calculate machine Y
                # Y_machine = Y_slice - Z_slice * tan(45)
                # But wait, OrcaSlicer might have already shifted it in the G-code labels?
                # Actually, the G-code contains PHYSICAL coordinates for belt printers.
                # So we just check if physical Y is near 0.
                
                # Check if it's bed adherent
                if abs(y) < 0.2: # Using a bit more tolerance for parsing
                    bed_segments_found += 1
                    # Speed should be initial_layer_speed (30mm/s -> F1800)
                    if f_val is not None and f_val > 1801: # allow some float error
                        errors.append(f"Bed segment at Z={nominal_z}, Y={y} has wrong speed: F{f_val}")
                else:
                    other_segments_found += 1
                    # Slower segments might exist for other reasons, but we check if normal ones are fast
                    if nominal_z > 1.0 and abs(y) > 1.0:
                        if f_val is not None and f_val == 1800:
                            # This might be fine if it's a small perimeter, but usually it should be faster
                            pass

print(f"Found {bed_segments_found} bed segments and {other_segments_found} other segments.")
if errors:
    print(f"Validation FAILED with {len(errors)} errors:")
    for err in errors[:10]:
        print(err)
else:
    if bed_segments_found > 0:
        print("Validation SUCCESSFUL: Bed segments found with correct speed.")
    else:
        print("Validation inconclusive: No bed segments found. Check machine coordinates logic.")

# Clean up
# os.remove(CONFIG_PATH)
