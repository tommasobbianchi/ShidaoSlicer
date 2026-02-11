#!/usr/bin/env python3
"""
G-code Comparison Tool for Belt Printer Validation
Compares OrcaSlicer output against IdeaMaker reference
"""

import sys
import re
from pathlib import Path
from typing import List, Tuple, Dict
from dataclasses import dataclass

@dataclass
class GCodeLine:
    """Parsed G-code line"""
    line_num: int
    raw: str
    command: str = ""
    params: Dict[str, float] = None
    comment: str = ""
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}

class GCodeParser:
    """Parse G-code files for comparison"""
    
    @staticmethod
    def parse_line(line: str, line_num: int) -> GCodeLine:
        """Parse single G-code line"""
        # Split command and comment
        parts = line.split(';', 1)
        command_part = parts[0].strip()
        comment_part = parts[1].strip() if len(parts) > 1 else ""
        
        # Extract command
        tokens = command_part.split()
        command = tokens[0] if tokens else ""
        
        # Extract parameters
        params = {}
        for token in tokens[1:]:
            if len(token) > 1 and token[0].isalpha():
                param_name = token[0]
                try:
                    param_value = float(token[1:])
                    params[param_name] = param_value
                except ValueError:
                    pass  # Skip non-numeric parameters
        
        return GCodeLine(
            line_num=line_num,
            raw=line.rstrip(),
            command=command,
            params=params,
            comment=comment_part
        )
    
    @staticmethod
    def parse_file(filepath: str) -> List[GCodeLine]:
        """Parse entire G-code file"""
        lines = []
        with open(filepath, 'r') as f:
            for i, line in enumerate(f, 1):
                lines.append(GCodeParser.parse_line(line, i))
        return lines

class GCodeComparator:
    """Compare two G-code files"""
    
    def __init__(self, tolerance: float = 0.01, extrusion_tolerance: float = 0.001):
        self.tolerance = tolerance
        self.extrusion_tolerance = extrusion_tolerance
        self.stats = {
            'total_lines': 0,
            'matching': 0,
            'different': 0,
            'coordinate_diffs': 0,
            'extrusion_diffs': 0,
            'speed_diffs': 0,
            'temp_diffs': 0,
            'critical_errors': []
        }
    
    def compare_params(self, ref_params: Dict[str, float], test_params: Dict[str, float]) -> Tuple[bool, List[str]]:
        """Compare parameter dictionaries"""
        differences = []
        
        # Check all parameters in reference
        for param, ref_value in ref_params.items():
            if param not in test_params:
                differences.append(f"Missing parameter {param}")
                continue
            
            test_value = test_params[param]
            
            # Different tolerances for different parameters
            if param == 'E':  # Extrusion
                tolerance = self.extrusion_tolerance
            elif param in ['X', 'Y', 'Z']:  # Coordinates
                tolerance = self.tolerance
            else:  # F (feed rate), etc.
                tolerance = self.tolerance
            
            diff = abs(ref_value - test_value)
            if diff > tolerance:
                differences.append(f"{param}: {ref_value:.4f} vs {test_value:.4f} (diff: {diff:.4f})")
                
                # Track statistics
                if param in ['X', 'Y', 'Z']:
                    self.stats['coordinate_diffs'] += 1
                elif param == 'E':
                    self.stats['extrusion_diffs'] += 1
                elif param == 'F':
                    self.stats['speed_diffs'] += 1
        
        # Check for extra parameters in test
        for param in test_params:
            if param not in ref_params:
                differences.append(f"Extra parameter {param}={test_params[param]}")
        
        return len(differences) == 0, differences
    
    def compare_lines(self, ref_line: GCodeLine, test_line: GCodeLine) -> Tuple[bool, str]:
        """Compare two G-code lines"""
        # Ignore pure comment lines
        if not ref_line.command and not test_line.command:
            return True, "Both comments"
        
        # Command must match
        if ref_line.command != test_line.command:
            return False, f"Command mismatch: {ref_line.command} vs {test_line.command}"
        
        # Special handling for temperature commands
        if ref_line.command in ['M104', 'M109', 'M140', 'M190']:
            if 'S' in ref_line.params and 'S' in test_line.params:
                if ref_line.params['S'] != test_line.params['S']:
                    self.stats['temp_diffs'] += 1
                    return False, f"Temperature mismatch: {ref_line.params['S']}°C vs {test_line.params['S']}°C"
        
        # Compare parameters
        match, diffs = self.compare_params(ref_line.params, test_line.params)
        if not match:
            return False, "; ".join(diffs)
        
        return True, "Match"
    
    def compare_files(self, ref_file: str, test_file: str, ignore_comments: bool = True) -> Dict:
        """Compare two G-code files"""
        print(f"📊 Comparing G-code files:")
        print(f"   Reference: {ref_file}")
        print(f"   Test:      {test_file}\n")
        
        ref_lines = GCodeParser.parse_file(ref_file)
        test_lines = GCodeParser.parse_file(test_file)
        
        # Filter out pure comments if requested
        if ignore_comments:
            ref_lines = [l for l in ref_lines if l.command]
            test_lines = [l for l in test_lines if l.command]
        
        self.stats['total_lines'] = max(len(ref_lines), len(test_lines))
        
        differences = []
        
        # Line-by-line comparison
        max_lines = max(len(ref_lines), len(test_lines))
        for i in range(max_lines):
            if i >= len(ref_lines):
                differences.append({
                    'line': i + 1,
                    'type': 'extra_test',
                    'test': test_lines[i].raw
                })
                self.stats['different'] += 1
                continue
            
            if i >= len(test_lines):
                differences.append({
                    'line': i + 1,
                    'type': 'missing_test',
                    'ref': ref_lines[i].raw
                })
                self.stats['different'] += 1
                continue
            
            ref_line = ref_lines[i]
            test_line = test_lines[i]
            
            match, reason = self.compare_lines(ref_line, test_line)
            
            if match:
                self.stats['matching'] += 1
            else:
                self.stats['different'] += 1
                differences.append({
                    'line': i + 1,
                    'type': 'mismatch',
                    'ref': ref_line.raw,
                    'test': test_line.raw,
                    'reason': reason
                })
                
                # Critical errors
                if 'Command mismatch' in reason or 'Temperature mismatch' in reason:
                    self.stats['critical_errors'].append({
                        'line': i + 1,
                        'reason': reason
                    })
        
        return {
            'stats': self.stats,
            'differences': differences
        }
    
    def print_report(self, results: Dict):
        """Print comparison report"""
        stats = results['stats']
        diffs = results['differences']
        
        print("="*60)
        print("📊 COMPARISON RESULTS")
        print("="*60)
        
        print(f"\n✅ Matching lines:    {stats['matching']:5d} / {stats['total_lines']}")
        print(f"❌ Different lines:   {stats['different']:5d} / {stats['total_lines']}")
        
        if stats['total_lines'] > 0:
            match_pct = (stats['matching'] / stats['total_lines']) * 100
            print(f"📈 Match percentage:  {match_pct:5.1f}%")
        
        print(f"\n🔍 Difference Breakdown:")
        print(f"   Coordinate diffs:  {stats['coordinate_diffs']}")
        print(f"   Extrusion diffs:   {stats['extrusion_diffs']}")
        print(f"   Speed diffs:       {stats['speed_diffs']}")
        print(f"   Temperature diffs: {stats['temp_diffs']}")
        
        if stats['critical_errors']:
            print(f"\n🚨 CRITICAL ERRORS: {len(stats['critical_errors'])}")
            for err in stats['critical_errors'][:5]:  # Show first 5
                print(f"   Line {err['line']}: {err['reason']}")
            if len(stats['critical_errors']) > 5:
                print(f"   ... and {len(stats['critical_errors']) - 5} more")
        
        # Show sample differences
        if diffs:
            print(f"\n📋 Sample Differences (first 10):")
            print("-"*60)
            for diff in diffs[:10]:
                print(f"\nLine {diff['line']}:")
                if diff['type'] == 'mismatch':
                    print(f"  Ref:  {diff['ref']}")
                    print(f"  Test: {diff['test']}")
                    print(f"  → {diff['reason']}")
                elif diff['type'] == 'missing_test':
                    print(f"  Ref:  {diff['ref']}")
                    print(f"  Test: (missing)")
                elif diff['type'] == 'extra_test':
                    print(f"  Ref:  (missing)")
                    print(f"  Test: {diff['test']}")
            
            if len(diffs) > 10:
                print(f"\n... and {len(diffs) - 10} more differences")
        
        print("\n" + "="*60)
        
        # Summary verdict
        if stats['critical_errors']:
            print("⚠️  CRITICAL ISSUES FOUND - Review and fix")
        elif stats['different'] == 0:
            print("✅ PERFECT MATCH!")
        elif stats['different'] < stats['total_lines'] * 0.05:
            print("✅ GOOD MATCH - Minor differences only")
        else:
            print("⚠️  SIGNIFICANT DIFFERENCES - Investigation needed")
        
        print("="*60)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Compare G-code files")
    parser.add_argument("reference", help="Reference G-code file (IdeaMaker)")
    parser.add_argument("test", help="Test G-code file (OrcaSlicer)")
    parser.add_argument("--tolerance", type=float, default=0.01, 
                       help="Coordinate tolerance in mm (default: 0.01)")
    parser.add_argument("--extrusion-tolerance", type=float, default=0.001,
                       help="Extrusion tolerance in mm (default: 0.001)")
    parser.add_argument("--include-comments", action="store_true",
                       help="Include comment-only lines in comparison")
    parser.add_argument("--output", help="Save detailed report to file")
    
    args = parser.parse_args()
    
    # Verify files exist
    if not Path(args.reference).exists():
        print(f"❌ Reference file not found: {args.reference}")
        return 1
    
    if not Path(args.test).exists():
        print(f"❌ Test file not found: {args.test}")
        return 1
    
    # Run comparison
    comparator = GCodeComparator(args.tolerance, args.extrusion_tolerance)
    results = comparator.compare_files(
        args.reference, 
        args.test,
        ignore_comments=not args.include_comments
    )
    
    # Print report
    comparator.print_report(results)
    
    # Save detailed report if requested
    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n📝 Detailed report saved to: {args.output}")
    
    # Exit code based on results
    if results['stats']['critical_errors']:
        return 2  # Critical errors
    elif results['stats']['different'] > 0:
        return 1  # Differences found
    else:
        return 0  # Perfect match


if __name__ == "__main__":
    sys.exit(main())
