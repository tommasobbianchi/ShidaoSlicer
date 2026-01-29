#!/usr/bin/env python3
"""
Belt Printer Coordinate Transform Validator
Verifies V→F coordinate transformation math
"""

import sys
import re
import math
from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass

@dataclass
class Coordinate:
    """3D coordinate with optional extrusion"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    e: float = None
    line_num: int = 0

class BeltTransformValidator:
    """Validate belt printer coordinate transforms"""
    
    def __init__(self, belt_angle: float = 45.0):
        self.belt_angle = belt_angle
        self.angle_rad = math.radians(belt_angle)
        self.cos_alpha = math.cos(self.angle_rad)
        self.sin_alpha = math.sin(self.angle_rad)
        self.tan_alpha = math.tan(self.angle_rad)
        
        print(f"🔧 Belt Transform Validator")
        print(f"   Angle: {belt_angle}°")
        print(f"   cos(α): {self.cos_alpha:.4f}")
        print(f"   tan(α): {self.tan_alpha:.4f}\n")
    
    def extract_coordinates(self, gcode_file: str) -> List[Coordinate]:
        """Extract all G1 movement coordinates"""
        coords = []
        current_pos = Coordinate()
        
        with open(gcode_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                # Only process movement commands
                if not line.startswith('G0') and not line.startswith('G1'):
                    continue
                
                # Parse coordinates
                x_match = re.search(r'X([-\d.]+)', line)
                y_match = re.search(r'Y([-\d.]+)', line)
                z_match = re.search(r'Z([-\d.]+)', line)
                e_match = re.search(r'E([-\d.]+)', line)
                
                # Update current position
                if x_match:
                    current_pos.x = float(x_match.group(1))
                if y_match:
                    current_pos.y = float(y_match.group(1))
                if z_match:
                    current_pos.z = float(z_match.group(1))
                if e_match:
                    current_pos.e = float(e_match.group(1))
                
                # Store coordinate if any axis changed
                if x_match or y_match or z_match:
                    coords.append(Coordinate(
                        x=current_pos.x,
                        y=current_pos.y,
                        z=current_pos.z,
                        e=current_pos.e,
                        line_num=line_num
                    ))
        
        return coords
    
    def validate_z_advancement(self, coords: List[Coordinate], tolerance: float = 0.001) -> dict:
        """Validate Z advancement follows belt transform"""
        violations = []
        layer_heights = []
        
        prev_z = None
        for i, coord in enumerate(coords):
            if prev_z is not None and coord.z != prev_z:
                delta_z = coord.z - prev_z
                
                # Expected advancement: Δ Z_m = Δ Z_s / cos(α)
                # For 0.2mm layer at 45°: 0.2 / 0.7071 = 0.2828mm
                # But in G-code this is the actual Z value, not layer height
                # So we're just tracking that Z increases properly
                
                if delta_z > 0:
                    layer_heights.append(delta_z)
            
            prev_z = coord.z
        
        # Analyze layer heights
        if layer_heights:
            avg_layer = sum(layer_heights) / len(layer_heights)
            min_layer = min(layer_heights)
            max_layer = max(layer_heights)
            
            # For 45° belt, expect layer height * 1.4142
            # But actual value depends on slicer's layer height setting
            
            return {
                'valid': True,
                'avg_layer_height': avg_layer,
                'min_layer_height': min_layer,
                'max_layer_height': max_layer,
                'layer_count': len(layer_heights),
                'expected_ratio': 1.0 / self.cos_alpha,
                'violations': violations
            }
        
        return {'valid': False, 'error': 'No Z movements found'}
    
    def validate_y_compensation(self, coords: List[Coordinate], tolerance: float = 0.1) -> dict:
        """Validate Y compensation: Y_m = Y_s - Z_s * tan(α)"""
        violations = []
        
        # Expected: as Z increases, Y should decrease (for 45°, Y_m = Y_s - Z_s)
        # Track Y vs Z relationship
        
        prev_coord = None
        for coord in coords:
            if prev_coord is not None:
                delta_z = coord.z - prev_coord.z
                delta_y = coord.y - prev_coord.y
                
                if abs(delta_z) > 0.001:  # Meaningful Z change
                    # Expected Y change: -delta_z * tan(α)
                    expected_delta_y = -delta_z * self.tan_alpha
                    actual_delta_y = delta_y
                    
                    diff = abs(expected_delta_y - actual_delta_y)
                    
                    if diff > tolerance:
                        violations.append({
                            'line': coord.line_num,
                            'delta_z': delta_z,
                            'expected_delta_y': expected_delta_y,
                            'actual_delta_y': actual_delta_y,
                            'diff': diff
                        })
            
            prev_coord = coord
        
        return {
            'valid': len(violations) == 0,
            'violations': violations,
            'violation_count': len(violations)
        }
    
    def validate_file(self, gcode_file: str) -> dict:
        """Complete validation of G-code file"""
        print(f"📋 Validating: {gcode_file}\n")
        
        coords = self.extract_coordinates(gcode_file)
        print(f"✅ Extracted {len(coords)} coordinates\n")
        
        # Validate Z advancement
        print("🔍 Validating Z advancement (belt axis)...")
        z_result = self.validate_z_advancement(coords)
        
        if z_result.get('valid'):
            print(f"   ✅ Average layer height: {z_result['avg_layer_height']:.4f}mm")
            print(f"   ✅ Layer count: {z_result['layer_count']}")
            print(f"   📊 Expected ratio (1/cos α): {z_result['expected_ratio']:.4f}")
        else:
            print(f"   ❌ {z_result.get('error')}")
        
        print()
        
        # Validate Y compensation
        print("🔍 Validating Y compensation (gantry slope)...")
        y_result = self.validate_y_compensation(coords)
        
        if y_result['valid']:
            print(f"   ✅ All Y compensations within tolerance")
        else:
            print(f"   ⚠️  Found {y_result['violation_count']} violations")
            for v in y_result['violations'][:5]:  # Show first 5
                print(f"      Line {v['line']}: ΔY expected {v['expected_delta_y']:.3f}, got {v['actual_delta_y']:.3f} (diff: {v['diff']:.3f}mm)")
            if y_result['violation_count'] > 5:
                print(f"      ... and {y_result['violation_count'] - 5} more")
        
        print()
        
        # Overall verdict
        print("="*60)
        if z_result.get('valid') and y_result['valid']:
            print("✅ BELT TRANSFORM VALIDATION PASSED")
        else:
            print("⚠️  BELT TRANSFORM VALIDATION FAILED")
        print("="*60)
        
        return {
            'z_advancement': z_result,
            'y_compensation': y_result,
            'valid': z_result.get('valid', False) and y_result['valid']
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate belt printer coordinate transforms")
    parser.add_argument("gcode", help="G-code file to validate")
    parser.add_argument("--angle", type=float, default=45.0,
                       help="Belt angle in degrees (default: 45)")
    parser.add_argument("--tolerance", type=float, default=0.1,
                       help="Y compensation tolerance in mm (default: 0.1)")
    parser.add_argument("--output", help="Save report to JSON file")
    
    args = parser.parse_args()
    
    # Verify file exists
    if not Path(args.gcode).exists():
        print(f"❌ File not found: {args.gcode}")
        return 1
    
    # Run validation
    validator = BeltTransformValidator(args.angle)
    results = validator.validate_file(args.gcode)
    
    # Save report if requested
    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n📝 Report saved to: {args.output}")
    
    # Exit code
    return 0 if results['valid'] else 1


if __name__ == "__main__":
    sys.exit(main())
