#!/usr/bin/env python3
"""
Belt Transform Validator - Validazione Matematica Trasformazioni Belt Printer

Questo script replica ESATTAMENTE le trasformazioni applicate in OrcaSlicer
per il belt slicing, permettendo di verificare i risultati senza dipendere dalla GUI.

Trasformazioni applicate (come in Print.hpp trafo_centered()):
1. Centratura del modello
2. Y↔Z swap (scambio assi)
3. Shear 45° (taglio per slicing a 45 gradi)

Uso:
    python belt_transform_validator.py <file.stl> [--layer-height 0.2] [--gcode file.gcode]
"""

import argparse
import json
import sys
import os
from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np

# Prova ad importare stl, altrimenti usa un parser STL semplificato
try:
    from stl import mesh
    HAS_STL = True
except ImportError:
    HAS_STL = False
    print("⚠️  numpy-stl non trovato, uso parser STL ASCII semplificato")


@dataclass
class BoundingBox:
    """Bounding box 3D"""
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float
    
    @property
    def size_x(self) -> float:
        return self.max_x - self.min_x
    
    @property
    def size_y(self) -> float:
        return self.max_y - self.min_y
    
    @property
    def size_z(self) -> float:
        return self.max_z - self.min_z
    
    @property
    def center(self) -> Tuple[float, float, float]:
        return (
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
            (self.min_z + self.max_z) / 2
        )
    
    def to_dict(self) -> dict:
        return {
            "min": {"x": self.min_x, "y": self.min_y, "z": self.min_z},
            "max": {"x": self.max_x, "y": self.max_y, "z": self.max_z},
            "size": {"x": self.size_x, "y": self.size_y, "z": self.size_z},
            "center": {"x": self.center[0], "y": self.center[1], "z": self.center[2]}
        }
    
    def __str__(self) -> str:
        return (f"  X: [{self.min_x:.3f} → {self.max_x:.3f}] (size: {self.size_x:.3f})\n"
                f"  Y: [{self.min_y:.3f} → {self.max_y:.3f}] (size: {self.size_y:.3f})\n"
                f"  Z: [{self.min_z:.3f} → {self.max_z:.3f}] (size: {self.size_z:.3f})")


def load_stl_vertices(filename: str) -> np.ndarray:
    """Carica i vertici da un file STL (binary o ASCII)"""
    if HAS_STL:
        stl_mesh = mesh.Mesh.from_file(filename)
        # Estrai tutti i vertici unici
        vertices = stl_mesh.vectors.reshape(-1, 3)
        return np.unique(vertices, axis=0)
    else:
        # Parser STL ASCII semplificato
        vertices = []
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('vertex'):
                    parts = line.split()
                    if len(parts) >= 4:
                        vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
        return np.array(vertices)


def compute_bounding_box(vertices: np.ndarray) -> BoundingBox:
    """Calcola il bounding box dai vertici"""
    return BoundingBox(
        min_x=float(np.min(vertices[:, 0])),
        max_x=float(np.max(vertices[:, 0])),
        min_y=float(np.min(vertices[:, 1])),
        max_y=float(np.max(vertices[:, 1])),
        min_z=float(np.min(vertices[:, 2])),
        max_z=float(np.max(vertices[:, 2]))
    )


def apply_yz_swap(vertices: np.ndarray) -> np.ndarray:
    """
    Applica lo swap Y↔Z (come in trafo_centered() di Print.hpp)
    
    Matrice di swap:
    | 1  0  0 |
    | 0  0  1 |  (Y diventa Z, Z diventa Y)
    | 0  1  0 |
    """
    swap_matrix = np.array([
        [1, 0, 0],
        [0, 0, 1],
        [0, 1, 0]
    ], dtype=float)
    
    return vertices @ swap_matrix.T


def apply_shear_45(vertices: np.ndarray) -> np.ndarray:
    """
    Applica lo shear a 45° (come in trafo_centered() di Print.hpp)
    
    Per belt printer con angolo 45°, lo shear è:
    Z_new = Z + Y * tan(45°) = Z + Y
    
    Matrice shear:
    | 1  0  0 |
    | 0  1  0 |
    | 0  1  1 |  (Z = Z + Y)
    """
    shear_matrix = np.array([
        [1, 0, 0],
        [0, 1, 0],
        [0, 1, 1]  # Z += Y (tan(45°) = 1)
    ], dtype=float)
    
    return vertices @ shear_matrix.T


def apply_inverse_shear(vertices: np.ndarray) -> np.ndarray:
    """
    Applica lo shear inverso (come in GCodeWriter.cpp)
    Z_new = Z - Y * tan(45°) = Z - Y
    """
    inv_shear_matrix = np.array([
        [1, 0, 0],
        [0, 1, 0],
        [0, -1, 1]  # Z -= Y
    ], dtype=float)
    
    return vertices @ inv_shear_matrix.T


def apply_inverse_zy_swap(vertices: np.ndarray) -> np.ndarray:
    """
    Applica lo swap inverso Z↔Y (per G-code output)
    È la stessa matrice dello swap Y↔Z (è simmetrica)
    """
    return apply_yz_swap(vertices)


def center_vertices(vertices: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Centra i vertici all'origine, ritorna (centered_vertices, offset)"""
    bbox = compute_bounding_box(vertices)
    offset = np.array([bbox.center[0], bbox.center[1], bbox.min_z])  # Z: solo floor at 0
    centered = vertices - offset
    # Assicura Z >= 0
    z_min = np.min(centered[:, 2])
    if z_min < 0:
        centered[:, 2] -= z_min
    return centered, offset


def simulate_slicing(vertices: np.ndarray, layer_height: float = 0.2) -> List[dict]:
    """
    Simula lo slicing orizzontale dei vertici trasformati
    Ritorna info per ogni layer
    """
    bbox = compute_bounding_box(vertices)
    layers = []
    
    z = 0.0
    layer_num = 0
    while z <= bbox.max_z + layer_height:
        # Trova i vertici in questo layer (con tolleranza)
        tolerance = layer_height / 2
        mask = np.abs(vertices[:, 2] - z) < tolerance
        layer_vertices = vertices[mask]
        
        if len(layer_vertices) > 0:
            layer_bbox = compute_bounding_box(layer_vertices)
            layers.append({
                "layer": layer_num,
                "z_height": round(z, 4),
                "vertex_count": len(layer_vertices),
                "x_range": [round(layer_bbox.min_x, 3), round(layer_bbox.max_x, 3)],
                "y_range": [round(layer_bbox.min_y, 3), round(layer_bbox.max_y, 3)]
            })
        
        z += layer_height
        layer_num += 1
    
    return layers


def parse_gcode_extents(gcode_file: str) -> dict:
    """
    Analizza un file G-code per estrarre le coordinate min/max
    """
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
                        try:
                            x_coords.append(float(part[1:]))
                        except ValueError:
                            pass
                    elif part.startswith('Y'):
                        try:
                            y_coords.append(float(part[1:]))
                        except ValueError:
                            pass
                    elif part.startswith('Z'):
                        try:
                            z_coords.append(float(part[1:]))
                        except ValueError:
                            pass
    
    if not x_coords or not y_coords or not z_coords:
        return {"error": "Nessuna coordinata trovata nel G-code"}
    
    return {
        "x": {"min": min(x_coords), "max": max(x_coords), "range": max(x_coords) - min(x_coords)},
        "y": {"min": min(y_coords), "max": max(y_coords), "range": max(y_coords) - min(y_coords)},
        "z": {"min": min(z_coords), "max": max(z_coords), "range": max(z_coords) - min(z_coords)},
        "total_moves": len(x_coords)
    }


def check_z_monotonic(gcode_file: str) -> dict:
    """Verifica se Z è monotonicamente crescente (come deve essere per belt printer)"""
    z_values = []
    
    with open(gcode_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            if line.startswith('G0 ') or line.startswith('G1 '):
                parts = line.split()
                for part in parts:
                    if part.startswith('Z'):
                        try:
                            z_values.append((line_num, float(part[1:])))
                        except ValueError:
                            pass
    
    violations = []
    for i in range(1, len(z_values)):
        if z_values[i][1] < z_values[i-1][1]:
            violations.append({
                "line": z_values[i][0],
                "z_prev": z_values[i-1][1],
                "z_curr": z_values[i][1],
                "delta": z_values[i][1] - z_values[i-1][1]
            })
    
    return {
        "total_z_moves": len(z_values),
        "is_monotonic": len(violations) == 0,
        "violations": violations[:10]  # Primi 10
    }


def print_header(text: str):
    """Stampa un header formattato"""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description='Belt Transform Validator')
    parser.add_argument('stl_file', help='File STL da analizzare')
    parser.add_argument('--layer-height', type=float, default=0.2, help='Altezza layer (default: 0.2mm)')
    parser.add_argument('--gcode', help='File G-code da confrontare')
    parser.add_argument('--json', help='Output JSON file')
    parser.add_argument('--belt-angle', type=float, default=45.0, help='Angolo belt (default: 45°)')
    args = parser.parse_args()
    
    if not os.path.exists(args.stl_file):
        print(f"❌ File non trovato: {args.stl_file}")
        sys.exit(1)
    
    print_header("BELT TRANSFORM VALIDATOR")
    print(f"📁 File: {args.stl_file}")
    print(f"📐 Layer height: {args.layer_height}mm")
    print(f"📐 Belt angle: {args.belt_angle}°")
    
    # Risultati per JSON
    results = {
        "input_file": args.stl_file,
        "layer_height": args.layer_height,
        "belt_angle": args.belt_angle,
        "stages": {}
    }
    
    # ============================================================
    # STAGE 0: Carica STL originale
    # ============================================================
    print_header("STAGE 0: STL Originale")
    
    vertices_original = load_stl_vertices(args.stl_file)
    print(f"🔢 Vertici caricati: {len(vertices_original)}")
    
    bbox_original = compute_bounding_box(vertices_original)
    print(f"\n📦 Bounding Box ORIGINALE:")
    print(bbox_original)
    
    results["stages"]["0_original"] = {
        "vertex_count": len(vertices_original),
        "bounding_box": bbox_original.to_dict()
    }
    
    # ============================================================
    # STAGE 1: Centratura (come trafo_centered inizio)
    # ============================================================
    print_header("STAGE 1: Dopo Centratura")
    
    vertices_centered, offset = center_vertices(vertices_original)
    bbox_centered = compute_bounding_box(vertices_centered)
    print(f"📦 Bounding Box dopo CENTRATURA:")
    print(bbox_centered)
    print(f"   Offset applicato: X={offset[0]:.3f}, Y={offset[1]:.3f}, Z={offset[2]:.3f}")
    
    results["stages"]["1_centered"] = {
        "bounding_box": bbox_centered.to_dict(),
        "offset": {"x": offset[0], "y": offset[1], "z": offset[2]}
    }
    
    # ============================================================
    # STAGE 2: Y↔Z Swap
    # ============================================================
    print_header("STAGE 2: Dopo Y↔Z Swap")
    
    vertices_swapped = apply_yz_swap(vertices_centered)
    bbox_swapped = compute_bounding_box(vertices_swapped)
    print(f"📦 Bounding Box dopo Y↔Z SWAP:")
    print(bbox_swapped)
    print(f"\n   ⚠️  Nota: l'asse Z originale ora è Y, e viceversa")
    
    results["stages"]["2_yz_swap"] = {
        "bounding_box": bbox_swapped.to_dict()
    }
    
    # ============================================================
    # STAGE 3: Shear 45° (Trasformazione Belt)
    # ============================================================
    print_header("STAGE 3: Dopo Shear 45°")
    
    vertices_sheared = apply_shear_45(vertices_swapped)
    bbox_sheared = compute_bounding_box(vertices_sheared)
    print(f"📦 Bounding Box dopo SHEAR 45° (PRIMA del fix):")
    print(bbox_sheared)
    print(f"\n   ⚠️  PROBLEMA: Z_min = {bbox_sheared.min_z:.2f} < 0!")
    
    results["stages"]["3_shear_45_before_fix"] = {
        "bounding_box": bbox_sheared.to_dict()
    }
    
    # ============================================================
    # STAGE 3b: Z Floor (FIX per Z negativi)
    # ============================================================
    print_header("STAGE 3b: Z Floor (FIX C++)")
    
    # Stesso fix del C++: trasla Z per portare Z_min a 0
    z_offset = -bbox_sheared.min_z  # Quanto serve per portare Z_min a 0
    vertices_floored = vertices_sheared.copy()
    vertices_floored[:, 2] += z_offset
    bbox_floored = compute_bounding_box(vertices_floored)
    
    print(f"   Z offset applicato: +{z_offset:.3f}mm")
    print(f"\n📦 Bounding Box dopo Z FLOOR (DOPO fix):")
    print(bbox_floored)
    print(f"\n   ✅ Z_min ora è {bbox_floored.min_z:.2f} (dovrebbe essere ~0)")
    print(f"\n   ℹ️  Questo è il sistema in cui avviene lo slicing XY")
    
    # Usa vertices_floored per il resto
    vertices_sheared = vertices_floored
    bbox_sheared = bbox_floored
    
    results["stages"]["3b_z_floor"] = {
        "z_offset": z_offset,
        "bounding_box": bbox_floored.to_dict()
    }
    
    # ============================================================
    # STAGE 4: Simulazione Slicing
    # ============================================================
    print_header("STAGE 4: Simulazione Slicing")
    
    layers = simulate_slicing(vertices_sheared, args.layer_height)
    expected_layers = int(bbox_sheared.size_z / args.layer_height) + 1
    
    print(f"📊 Layer teorici attesi: ~{expected_layers}")
    print(f"📊 Layer con vertici: {len(layers)}")
    print(f"📊 Altezza Z da sliccare: {bbox_sheared.size_z:.3f}mm")
    print(f"\n   Primi 5 layer:")
    for layer in layers[:5]:
        print(f"     Layer {layer['layer']:3d}: Z={layer['z_height']:6.2f}mm, "
              f"X=[{layer['x_range'][0]:7.2f}, {layer['x_range'][1]:7.2f}], "
              f"Y=[{layer['y_range'][0]:7.2f}, {layer['y_range'][1]:7.2f}]")
    
    if len(layers) > 5:
        last_layer = layers[-1]
        print(f"     ...")
        print(f"     Layer {last_layer['layer']:3d}: Z={last_layer['z_height']:6.2f}mm, "
              f"X=[{last_layer['x_range'][0]:7.2f}, {last_layer['x_range'][1]:7.2f}], "
              f"Y=[{last_layer['y_range'][0]:7.2f}, {last_layer['y_range'][1]:7.2f}]")
    
    results["stages"]["4_slicing"] = {
        "expected_layers": expected_layers,
        "actual_layers": len(layers),
        "z_height_total": bbox_sheared.size_z,
        "layers_sample": layers[:5] + (layers[-1:] if len(layers) > 5 else [])
    }
    
    # ============================================================
    # STAGE 5: Trasformazione Inversa (G-code output)
    # ============================================================
    print_header("STAGE 5: Trasformazione Inversa (G-code)")
    
    # Prima inverse shear, poi Z↔Y swap (ordine inverso)
    vertices_inv_shear = apply_inverse_shear(vertices_sheared)
    vertices_final = apply_inverse_zy_swap(vertices_inv_shear)
    bbox_final = compute_bounding_box(vertices_final)
    
    print(f"📦 Bounding Box FINALE (coordinate G-code fisiche):")
    print(bbox_final)
    print(f"\n   ℹ️  Queste sono le coordinate che dovrebbero apparire nel G-code")
    
    results["stages"]["5_gcode_coords"] = {
        "bounding_box": bbox_final.to_dict()
    }
    
    # ============================================================
    # VERIFICA: Confronto con originale
    # ============================================================
    print_header("VERIFICA: Coerenza Trasformazioni")
    
    # Le dimensioni dovrebbero essere preservate (permutate)
    orig_sizes = sorted([bbox_original.size_x, bbox_original.size_y, bbox_original.size_z])
    final_sizes = sorted([bbox_final.size_x, bbox_final.size_y, bbox_final.size_z])
    
    size_match = all(abs(a - b) < 0.01 for a, b in zip(orig_sizes, final_sizes))
    
    print(f"   Dimensioni originali (ordinate): {[f'{s:.2f}' for s in orig_sizes]}")
    print(f"   Dimensioni finali (ordinate):    {[f'{s:.2f}' for s in final_sizes]}")
    print(f"   ✅ Dimensioni preservate: {'SÌ' if size_match else 'NO ⚠️'}")
    
    results["verification"] = {
        "sizes_preserved": size_match,
        "original_sizes_sorted": orig_sizes,
        "final_sizes_sorted": final_sizes
    }
    
    # ============================================================
    # OPZIONALE: Confronto con G-code
    # ============================================================
    if args.gcode and os.path.exists(args.gcode):
        print_header("CONFRONTO: G-code Generato")
        
        gcode_extents = parse_gcode_extents(args.gcode)
        if "error" not in gcode_extents:
            print(f"📄 File: {args.gcode}")
            print(f"📊 Movimenti totali: {gcode_extents['total_moves']}")
            print(f"\n   Estensioni G-code:")
            print(f"     X: [{gcode_extents['x']['min']:.2f} → {gcode_extents['x']['max']:.2f}] range: {gcode_extents['x']['range']:.2f}")
            print(f"     Y: [{gcode_extents['y']['min']:.2f} → {gcode_extents['y']['max']:.2f}] range: {gcode_extents['y']['range']:.2f}")
            print(f"     Z: [{gcode_extents['z']['min']:.2f} → {gcode_extents['z']['max']:.2f}] range: {gcode_extents['z']['range']:.2f}")
            
            # Controllo Z monotonic
            z_check = check_z_monotonic(args.gcode)
            print(f"\n   🔍 Verifica Z monotonica:")
            print(f"     Movimenti Z: {z_check['total_z_moves']}")
            print(f"     Monotonica: {'✅ SÌ' if z_check['is_monotonic'] else '❌ NO'}")
            if not z_check['is_monotonic']:
                print(f"     Violazioni (prime 5):")
                for v in z_check['violations'][:5]:
                    print(f"       Linea {v['line']}: Z {v['z_prev']:.2f} → {v['z_curr']:.2f} (Δ={v['delta']:.2f})")
            
            results["gcode_comparison"] = {
                "extents": gcode_extents,
                "z_monotonic": z_check
            }
        else:
            print(f"⚠️  {gcode_extents['error']}")
    
    # ============================================================
    # OUTPUT JSON
    # ============================================================
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n💾 Risultati salvati in: {args.json}")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print_header("RIEPILOGO")
    print(f"""
    📐 MODELLO ORIGINALE:
       Dimensioni: {bbox_original.size_x:.2f} x {bbox_original.size_y:.2f} x {bbox_original.size_z:.2f} mm
       Altezza (Z): {bbox_original.size_z:.2f} mm
       
    📐 DOPO TRASFORMAZIONI (per slicing):
       Z range: {bbox_sheared.min_z:.2f} → {bbox_sheared.max_z:.2f} mm
       Altezza slicing: {bbox_sheared.size_z:.2f} mm
       Layer attesi: ~{expected_layers}
       
    📐 COORDINATE G-CODE FINALI:
       X: {bbox_final.min_x:.2f} → {bbox_final.max_x:.2f} mm
       Y: {bbox_final.min_y:.2f} → {bbox_final.max_y:.2f} mm  
       Z: {bbox_final.min_z:.2f} → {bbox_final.max_z:.2f} mm
    """)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
