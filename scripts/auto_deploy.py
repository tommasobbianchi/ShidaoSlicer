import sys
import os
import subprocess
import time
import glob
import logging

# Add the script directory to sys.path so we can import klipper_remote
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from klipper_remote import KlipperPrinter, KlipperError
except ImportError as e:
    print(f"Error importing klipper_remote: {e}")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger()

# Constants
SSH_USER = "ideaformer"
SSH_PASS = "1234"
BUILD_DIR = "/home/user/projects/ORCA_BELT/build"
SLICER_BIN = f"{BUILD_DIR}/src/Debug/orca-slicer"
OUTPUT_GCODE = "cube_Zfixed.gcode"
STL_FILE = "tests/fixtures/anchor_cube.stl"

CONFIG_ARGS = [
    "--load-settings", "tests/fixtures/belt_machine.json",
    "--load-settings", "tests/fixtures/belt_process.json",
    "--load-filaments", "tests/fixtures/belt_filament.json"
]

def cleanup_old_files():
    for f in glob.glob("*.gcode"):
        try: os.remove(f)
        except: pass

def generate_gcode():
    logger.info("Generating G-code...")
    cmd = [SLICER_BIN, STL_FILE] + CONFIG_ARGS + ["--slice", "0", "--outputdir", "."]
    try:
        subprocess.check_call(cmd)
        files = glob.glob("*.gcode")
        if not files:
            logger.error("No G-code generated!")
            sys.exit(1)
        newest_file = max(files, key=os.path.getctime)
        if newest_file != OUTPUT_GCODE:
            if os.path.exists(OUTPUT_GCODE): os.remove(OUTPUT_GCODE)
            os.rename(newest_file, OUTPUT_GCODE)
    except subprocess.CalledProcessError as e:
        logger.error(f"Slicing failed: {e}")
        sys.exit(1)

def apply_dynamic_anchoring():
    """Finds GLOBAL MINIMUM of the entire model section to prevent range errors."""
    logger.info("🔧 Applying Bulletproof Global Anchoring...")
    
    with open(OUTPUT_GCODE, 'r') as f:
        lines = f.readlines()
        
    min_x, min_z = float('inf'), float('inf')
    scanning = False
    for line in lines:
        if "reset extruder positions" in line:
            scanning = True
            continue
        if scanning:
            # Check for G0/G1 moves that might be out of range
            if line.startswith("G0") or line.startswith("G1"):
                parts = line.split()
                for p in parts:
                    if p.startswith("X"):
                        try: min_x = min(min_x, float(p[1:]))
                        except: pass
                    if p.startswith("Z"):
                        try: min_z = min(min_z, float(p[1:]))
                        except: pass
            
    if min_x == float('inf') or min_z == float('inf'):
        logger.warning("Could not find any moves after start-code. Skipping.")
        return

    # Match IdeaMaker: Physical (0,0) is our anchor.
    target_phys_x = 0.0
    logger.info(f"🎯 Total Section Bounds: MinX={min_x}, MinZ={min_z}. Mapping to Physical [X={target_phys_x}, Z=0].")
    
    processed_lines = []
    anchor_applied = False
    for line in lines:
        if any(cmd in line for cmd in ["M201", "M203", "M205"]):
            continue
            
        if "reset extruder positions" in line and not anchor_applied:
            processed_lines.append(line)
            # Bridge to physical origin
            off_x = min_x - target_phys_x
            off_z = min_z
            processed_lines.append(f"G92 X{off_x} Z{off_z} ; BULLETPROOF ANCHOR: Lock current physical (0,0) to logical min\n")
            anchor_applied = True
        else:
            processed_lines.append(line)
            
    with open(OUTPUT_GCODE, 'w') as f:
        f.writelines(processed_lines)

def deploy_and_enqueue():
    logger.info("Connecting to printer...")
    try:
        printer = KlipperPrinter("<PRINTER_HOST>", ssh_user=SSH_USER, ssh_password=SSH_PASS)
        printer.upload_gcode(OUTPUT_GCODE)
        printer.enqueue_job(OUTPUT_GCODE)
        logger.info("SUCCESS: G-code enqueued.")
    except KlipperError as e:
        logger.error(f"Klipper Error: {e}")
        sys.exit(1)

def main():
    cleanup_old_files()
    generate_gcode()
    apply_dynamic_anchoring()
    deploy_and_enqueue()

if __name__ == "__main__":
    main()
