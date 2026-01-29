#!/usr/bin/env python3
"""
Interactive Certification Session Manager
Real-time telemetry monitoring + visual feedback integration
"""

import sys
import time
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))
from klipper_remote import KlipperPrinter

class CertificationSession:
    """Manages interactive certification testing session"""
    
    def __init__(self, printer_ip: str):
        self.printer = KlipperPrinter(printer_ip)
        self.test_results = {}
        self.adjustments_made = []
        
    def verify_access(self) -> bool:
        """Verify all access requirements"""
        print("🔍 Verifying access to printer...\n")
        
        checks = {
            "SSH Connection": False,
            "Moonraker API": False,
            "Klipper Status": False,
            "G-code Upload Path": False
        }
        
        # Test SSH
        try:
            ssh = self.printer._ssh_connect()
            ssh.close()
            checks["SSH Connection"] = True
            print("✅ SSH Connection: OK")
        except Exception as e:
            print(f"❌ SSH Connection: FAILED - {e}")
            return False
            
        # Test Moonraker API
        try:
            status = self.printer.get_status()
            checks["Moonraker API"] = True
            print("✅ Moonraker API: OK")
        except Exception as e:
            print(f"❌ Moonraker API: FAILED - {e}")
            return False
            
        # Test Klipper status
        try:
            pos = self.printer.get_position()
            temps = self.printer.get_temperatures()
            checks["Klipper Status"] = True
            print(f"✅ Klipper Status: OK")
            print(f"   Position: X={pos[0]:.1f} Y={pos[1]:.1f} Z={pos[2]:.1f}")
            print(f"   Temps: E={temps['extruder']:.0f}°C B={temps['bed']:.0f}°C")
        except Exception as e:
            print(f"❌ Klipper Status: FAILED - {e}")
            return False
            
        # Test upload path
        try:
            ssh = self.printer._ssh_connect()
            stdin, stdout, stderr = ssh.exec_command("ls /home/pi/printer_data/gcodes/")
            output = stdout.read().decode()
            ssh.close()
            checks["G-code Upload Path"] = True
            print("✅ G-code Upload Path: OK")
        except Exception as e:
            print(f"❌ G-code Upload Path: FAILED - {e}")
            return False
        
        print("\n✅ All access checks passed!\n")
        return True
    
    def run_test(self, test_file: str, test_name: str, phase: str) -> bool:
        """Run single certification test with telemetry monitoring"""
        
        print(f"\n{'='*60}")
        print(f"🧪 TEST {phase}: {test_name}")
        print(f"   File: {Path(test_file).name}")
        print(f"{'='*60}\n")
        
        # Upload
        print("[ACTION] Uploading G-code...")
        filename = self.printer.upload_gcode(test_file)
        
        # Start
        print("[ACTION] Starting print...\n")
        self.printer.start_print(filename)
        
        # Monitor with telemetry
        print("[TELEMETRY] Monitoring started (Ctrl+C when test complete)\n")
        
        try:
            while True:
                status = self.printer.get_status()
                stats = status["print_stats"]
                temps = self.printer.get_temperatures()
                pos = status["toolhead"]["position"]
                
                # Print telemetry
                state = stats["state"]
                print(f"\r[STATE] {state:12s} | "
                      f"E:{temps['extruder']:5.1f}°C→{temps['extruder_target']:.0f}°C | "
                      f"B:{temps['bed']:5.1f}°C→{temps['bed_target']:.0f}°C | "
                      f"Pos: X{pos[0]:6.1f} Y{pos[1]:6.2f} Z{pos[2]:6.1f}",
                      end='', flush=True)
                
                # Check if complete
                if state in ["complete", "standby"]:
                    print("\n\n[STATE] Print complete!")
                    break
                    
                # Check for errors
                if state == "error":
                    print("\n\n[ERROR] Print failed!")
                    print("[ACTION] Checking error log...")
                    self.printer.tail_klipper_log(20)
                    return False
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\n\n[INFO] Monitoring stopped by user")
        
        # Get visual feedback
        print("\n" + "-"*60)
        print("📊 TELEMETRY DATA:")
        final_status = self.printer.get_status()
        final_temps = self.printer.get_temperatures()
        print(f"   Final temps: E={final_temps['extruder']:.1f}°C B={final_temps['bed']:.1f}°C")
        
        # Specific checks based on test type
        if "coordinate" in test_file.lower():
            # Special check for coordinate pattern test
            print("\n⚠️  CRITICAL: Verifying Y-axis stability...")
            y_stable = self.printer.verify_belt_coordinates(samples=30, max_variance=1.0)
            if not y_stable:
                print("\n❌ Y-axis coordinate issue detected!")
            else:
                print("\n✅ Y-axis stable - belt coordinates correct!")
        
        print("-"*60)
        print("\n👁️  VISUAL FEEDBACK NEEDED:")
        print("What did you observe?")
        print("  ✅ - Test passed")
        print("  ⚠️  - Issue found, needs adjustment")
        print("  🛑 - Critical failure, abort")
        print("")
        
        while True:
            feedback = input("Your assessment [✅/⚠️/🛑]: ").strip().lower()
            
            if feedback in ['✅', 'pass', 'ok', 'y', 'yes']:
                print(f"\n✅ TEST {phase} PASSED\n")
                self.test_results[test_name] = "PASS"
                return True
                
            elif feedback in ['⚠️', 'adjust', 'issue']:
                issue = input("Describe the issue: ")
                print(f"\n⚠️  Issue reported: {issue}")
                print("What adjustment is needed?")
                print("  1. Temperature adjustment")
                print("  2. Speed adjustment")
                print("  3. Z-offset adjustment")
                print("  4. Mechanical fix (you)")
                print("  5. Other")
                
                choice = input("Choice [1-5]: ").strip()
                
                # Handle adjustment
                # (This would integrate with parameter modification)
                print("\n[ACTION] Recording adjustment need...")
                self.adjustments_made.append({
                    'test': test_name,
                    'issue': issue,
                    'adjustment_type': choice
                })
                
                retry = input("\nRetry test now? [y/n]: ").strip().lower()
                if retry in ['y', 'yes']:
                    return self.run_test(test_file, test_name, phase)
                else:
                    self.test_results[test_name] = "FAILED"
                    return False
                    
            elif feedback in ['🛑', 'abort', 'stop', 'n', 'no']:
                print(f"\n🛑 TEST {phase} ABORTED\n")
                self.test_results[test_name] = "ABORTED"
                return False
                
            else:
                print("Invalid input, try again...")
    
    def print_summary(self):
        """Print session summary"""
        print("\n" + "="*60)
        print("📋 CERTIFICATION SESSION SUMMARY")
        print("="*60 + "\n")
        
        passed = sum(1 for r in self.test_results.values() if r == "PASS")
        total = len(self.test_results)
        
        print(f"Tests completed: {total}")
        print(f"Tests passed: {passed}/{total}")
        print(f"Adjustments made: {len(self.adjustments_made)}\n")
        
        print("Test Results:")
        for test, result in self.test_results.items():
            icon = "✅" if result == "PASS" else "❌"
            print(f"  {icon} {test}: {result}")
        
        if self.adjustments_made:
            print("\nAdjustments Made:")
            for adj in self.adjustments_made:
                print(f"  • {adj['test']}: {adj['issue']}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Interactive Certification Session")
    parser.add_argument("--ip", required=True, help="Printer Tailscale IP")
    parser.add_argument("--verify-only", action="store_true", help="Only verify access")
    
    args = parser.parse_args()
    
    print("🚀 Interactive Belt Printer Certification\n")
    
    session = CertificationSession(args.ip)
    
    # Verify access
    if not session.verify_access():
        print("\n❌ Access verification failed!")
        print("Please check Tailscale connection and try again.\n")
        return 1
    
    if args.verify_only:
        print("✅ Verification complete, ready for testing!\n")
        return 0
    
    # Run certification tests
    cert_dir = Path(__file__).parent.parent / "certification_tests"
    
    tests = [
        (cert_dir / "test_01_bed_heating.gcode", "Bed Heating", "1.1"),
        (cert_dir / "test_02_hotend_heating.gcode", "Hotend Heating", "1.2"),
        (cert_dir / "test_03_both_heaters.gcode", "Both Heaters", "1.3"),
        # Add more as needed
    ]
    
    print("\n▶️  Starting certification tests...\n")
    
    for test_file, name, phase in tests:
        if not session.run_test(str(test_file), name, phase):
            cont = input("\nContinue to next test anyway? [y/n]: ").strip().lower()
            if cont not in ['y', 'yes']:
                print("\n🛑 Certification stopped by user\n")
                break
    
    session.print_summary()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
