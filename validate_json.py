
import json
import traceback

def get_type(val):
    if isinstance(val, str): return "string"
    if isinstance(val, list): return "array"
    if isinstance(val, dict): return "object"
    if isinstance(val, bool): return "boolean"
    if isinstance(val, (int, float)): return "number"
    if val is None: return "null"
    return "unknown"

def compare_json(file_test, file_ref, label):
    print(f"Comparing {label}...")
    try:
        with open(file_test, 'r') as f:
            j_test = json.load(f)
    except Exception as e:
        print(f"  Error loading {file_test}: {e}")
        return

    try:
        with open(file_ref, 'r') as f:
            j_ref = json.load(f)
    except Exception as e:
        print(f"  Error loading {file_ref}: {e}")
        return

    # Check for fields present in both
    for key, val_ref in j_ref.items():
        if key in j_test:
            val_test = j_test[key]
            type_ref = get_type(val_ref)
            type_test = get_type(val_test)
            
            # Allow int/float interchangeability for "number"
            if type_ref == "number" and type_test == "number": continue
            
            if type_ref != type_test:
                print(f"  MISMATCH in {key}: Ref is {type_ref}, Test is {type_test}")
                print(f"    Ref Val: {str(val_ref)[:50]}")
                print(f"    Test Val: {str(val_test)[:50]}")

    print(f"  Finished {label}.\n")

base_dir = "resources/profiles"

# 1. Vendor Index
compare_json(f"{base_dir}/IdeaFormer.json", f"{base_dir}/BBL.json", "Vendor Index")

# 2. Machine Model
compare_json(f"{base_dir}/IdeaFormer/machine/IdeaFormer IR3 V2.json", 
             f"{base_dir}/BBL/machine/Bambu Lab A1 mini.json", "Machine Model")

# 3. Machine Preset
compare_json(f"{base_dir}/IdeaFormer/machine/IdeaFormer IR3 V2 0.4 nozzle.json", 
             f"{base_dir}/BBL/machine/Bambu Lab A1 mini 0.4 nozzle.json", "Machine Preset")

# 4. Process Preset
compare_json(f"{base_dir}/IdeaFormer/process/0.20mm Standard @IdeaFormer IR3 V2.json", 
             f"{base_dir}/BBL/process/0.20mm Standard @BBL A1M.json", "Process Preset")

# 5. Filament Preset
compare_json(f"{base_dir}/IdeaFormer/filament/Generic PLA @IdeaFormer.json", 
             f"{base_dir}/BBL/filament/Bambu PLA Basic @BBL X1C.json", "Filament Preset")
