#!/usr/bin/env python3
"""
Klipper Belt Printer Remote Controller
Automated workflow: Generate -> Upload -> Print -> Monitor

Credentials loaded from ~/.secrets/tailscale_hosts.yaml
"""

import paramiko
import requests
import time
import sys
import json
import yaml
from pathlib import Path
from typing import Optional, Dict, Any

# Default secrets file location
SECRETS_FILE = Path.home() / ".secrets" / "tailscale_hosts.yaml"


def load_host_credentials(hostname: str) -> Dict[str, str]:
    """Load credentials for a host from secrets file"""
    if not SECRETS_FILE.exists():
        raise FileNotFoundError(f"Secrets file not found: {SECRETS_FILE}")
    
    with open(SECRETS_FILE, 'r') as f:
        secrets = yaml.safe_load(f)
    
    hosts = secrets.get('hosts', {})
    if hostname not in hosts:
        available = list(hosts.keys())
        raise ValueError(f"Host '{hostname}' not found. Available: {available}")
    
    return hosts[hostname]

class KlipperError(Exception):
    """Custom exception for Klipper remote operations"""
    pass

class KlipperPrinter:
    """Remote Klipper printer controller via Tailscale SSH + Moonraker API"""
    
    def __init__(self, tailscale_ip: str, ssh_user: str = "pi", ssh_key_path: Optional[str] = None, ssh_password: Optional[str] = None):
        self.ip = tailscale_ip
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path
        self.ssh_password = ssh_password
        self.api_url = f"http://{self.ip}:7125"
        self.gcode_path = f"/home/{self.ssh_user}/printer_data/gcodes"
        
    def _ssh_connect(self) -> paramiko.SSHClient:
        """Create SSH connection"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        connect_kwargs = {
            "username": self.ssh_user,
            "timeout": 10
        }
        
        if self.ssh_key_path:
            connect_kwargs["key_filename"] = self.ssh_key_path
            
        if self.ssh_password:
            connect_kwargs["password"] = self.ssh_password
            
        ssh.connect(self.ip, **connect_kwargs)
        
        return ssh
    
    def upload_gcode(self, local_path: str, remote_name: Optional[str] = None) -> str:
        """Upload G-code file via SCP"""
        if remote_name is None:
            remote_name = Path(local_path).name
            
        print(f"📤 Uploading {local_path} → {remote_name}...")
        
        ssh = self._ssh_connect()
        sftp = ssh.open_sftp()
        remote_path = f"{self.gcode_path}/{remote_name}"
        
        try:
            sftp.put(local_path, remote_path)
            print(f"✅ Upload complete: {remote_name}")
            return remote_name
        finally:
            sftp.close()
            ssh.close()
    
    def start_print(self, filename: str) -> Dict[str, Any]:
        """Start print via Moonraker API"""
        print(f"▶️  Starting print: {filename}...")
        
        endpoint = f"{self.api_url}/printer/print/start"
        response = requests.post(endpoint, json={"filename": filename})
        
        if response.status_code == 200:
            print(f"✅ Print started successfully")
        else:
            print(f"❌ Failed to start: {response.text}")
            
        return response.json()
    
    def pause_print(self) -> Dict[str, Any]:
        """Pause current print"""
        endpoint = f"{self.api_url}/printer/print/pause"
        response = requests.post(endpoint)
        return response.json()
    
    def resume_print(self) -> Dict[str, Any]:
        """Resume paused print"""
        endpoint = f"{self.api_url}/printer/print/resume"
        response = requests.post(endpoint)
        return response.json()
    
    def cancel_print(self) -> Dict[str, Any]:
        """Cancel current print"""
        endpoint = f"{self.api_url}/printer/print/cancel"
        response = requests.post(endpoint)
        return response.json()
    
    def emergency_stop(self):
        """Emergency stop (M112)"""
        print("🚨 EMERGENCY STOP!")
        endpoint = f"{self.api_url}/printer/emergency_stop"
        requests.post(endpoint)

    def enqueue_job(self, filename: str) -> Dict[str, Any]:
        """Enqueue a job in Moonraker job_queue"""
        print(f"📥 Enqueuing job: {filename}...")
        endpoint = f"{self.api_url}/server/job_queue/job"
        response = requests.post(endpoint, json={"filenames": [filename]})
        
        if response.status_code == 200:
            print(f"✅ Job enqueued successfully")
        else:
            print(f"❌ Failed to enqueue: {response.text}")
            
        return response.json()
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive printer status"""
        endpoint = f"{self.api_url}/printer/objects/query"
        params = {
            "toolhead": None,
            "extruder": None,
            "heater_bed": None,
            "print_stats": None,
            "gcode_move": None
        }
        
        response = requests.get(endpoint, params={"objects": json.dumps(params)})
        return response.json()["result"]["status"]
    
    def get_position(self) -> tuple:
        """Get current toolhead position (X, Y, Z)"""
        status = self.get_status()
        return tuple(status["toolhead"]["position"][:3])
    
    def get_temperatures(self) -> Dict[str, float]:
        """Get current temperatures"""
        status = self.get_status()
        return {
            "extruder": status["extruder"]["temperature"],
            "extruder_target": status["extruder"]["target"],
            "bed": status["heater_bed"]["temperature"],
            "bed_target": status["heater_bed"]["target"]
        }
    
    def get_print_stats(self) -> Dict[str, Any]:
        """Get print statistics"""
        status = self.get_status()
        return status["print_stats"]
    
    def monitor_live(self, interval: float = 2.0, duration: Optional[float] = None):
        """Live monitoring loop with real-time feedback"""
        print("\n📊 Live Monitoring Started (Ctrl+C to stop)\n")
        
        start_time = time.time()
        
        try:
            while True:
                if duration and (time.time() - start_time) > duration:
                    break
                
                status = self.get_status()
                stats = status["print_stats"]
                temps = self.get_temperatures()
                pos = status["toolhead"]["position"]
                
                # Clear line and print status
                print(f"\r🖨️  State: {stats['state']:10s} | "
                      f"File: {stats.get('filename', 'N/A'):20s} | "
                      f"Time: {int(stats.get('print_duration', 0))}s | "
                      f"Pos: X{pos[0]:.1f} Y{pos[1]:.1f} Z{pos[2]:.1f} | "
                      f"E:{temps['extruder']:.0f}°C B:{temps['bed']:.0f}°C",
                      end='', flush=True)
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n⏹️  Monitoring stopped")
    
    def verify_belt_coordinates(self, samples: int = 50, max_variance: float = 2.0) -> bool:
        """Verify Y-axis stability for belt printer"""
        print(f"\n🔍 Verifying belt coordinates ({samples} samples)...")
        
        y_coords = []
        for i in range(samples):
            pos = self.get_position()
            y_coords.append(pos[1])
            time.sleep(0.1)
            print(f"\rSample {i+1}/{samples}: Y={pos[1]:.3f}mm", end='', flush=True)
        
        y_variance = max(y_coords) - min(y_coords)
        y_mean = sum(y_coords) / len(y_coords)
        
        print(f"\n\n📈 Results:")
        print(f"   Y mean: {y_mean:.3f}mm")
        print(f"   Y variance: {y_variance:.3f}mm")
        
        if y_variance > max_variance:
            print(f"   ⚠️  VARIANCE TOO HIGH! (max: {max_variance}mm)")
            print(f"   Belt coordinate issue detected!")
            return False
        else:
            print(f"   ✅ Y-axis stable (within {max_variance}mm)")
            return True
    
    def tail_klipper_log(self, lines: int = 50):
        """Tail Klipper log file"""
        ssh = self._ssh_connect()
        stdin, stdout, stderr = ssh.exec_command(f"tail -n {lines} /tmp/klippy.log")
        
        print(f"\n📋 Klipper Log (last {lines} lines):\n")
        print(stdout.read().decode())
        
        ssh.close()
    
    def watch_log_live(self):
        """Watch Klipper log in real-time"""
        print("\n📋 Watching Klipper log (Ctrl+C to stop)...\n")
        
        ssh = self._ssh_connect()
        stdin, stdout, stderr = ssh.exec_command("tail -f /tmp/klippy.log")
        
        try:
            for line in iter(stdout.readline, ""):
                print(line, end='')
        except KeyboardInterrupt:
            print("\n\n⏹️  Log watch stopped")
        finally:
            ssh.close()


def main():
    """CLI interface for quick testing"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Klipper Remote Controller",
        epilog="Example: klipper_remote.py --host ideaformer status"
    )
    
    # Connection options (mutually exclusive: --host OR --ip/--user/--password)
    # Not required - 'hosts' command doesn't need it
    conn_group = parser.add_mutually_exclusive_group(required=False)
    conn_group.add_argument("--host", help="Host name from ~/.secrets/tailscale_hosts.yaml (e.g., ideaformer)")
    conn_group.add_argument("--ip", help="Tailscale IP of printer (manual mode)")
    
    parser.add_argument("--user", help="SSH username (only with --ip)")
    parser.add_argument("--password", help="SSH password (only with --ip)")
    parser.add_argument("--key", help="SSH key path (only with --ip)")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Upload command
    upload_parser = subparsers.add_parser("upload", help="Upload G-code")
    upload_parser.add_argument("file", help="G-code file to upload")
    upload_parser.add_argument("--name", help="Remote filename")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start print")
    start_parser.add_argument("filename", help="G-code filename on printer")
    
    # Monitor command
    subparsers.add_parser("monitor", help="Live monitoring")
    
    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify belt coordinates")
    verify_parser.add_argument("--samples", type=int, default=50, help="Number of samples")
    
    # Log command
    log_parser = subparsers.add_parser("log", help="View Klipper log")
    log_parser.add_argument("--live", action="store_true", help="Watch live")
    log_parser.add_argument("--lines", type=int, default=50, help="Number of lines")
    
    # Status command
    subparsers.add_parser("status", help="Get printer status")
    
    # List hosts command
    subparsers.add_parser("hosts", help="List available hosts from secrets file")
    
    # Control commands
    subparsers.add_parser("pause", help="Pause print")
    subparsers.add_parser("resume", help="Resume print")
    subparsers.add_parser("cancel", help="Cancel print")
    subparsers.add_parser("emergency", help="Emergency stop")
    
    args = parser.parse_args()
    
    # Handle 'hosts' command (doesn't need connection)
    if args.command == "hosts":
        if SECRETS_FILE.exists():
            with open(SECRETS_FILE, 'r') as f:
                secrets = yaml.safe_load(f)
            print("\n📋 Available hosts:\n")
            for name, info in secrets.get('hosts', {}).items():
                desc = info.get('description', '')
                print(f"  • {name:20s} {info['ip']:18s} {desc}")
            print()
        else:
            print(f"❌ Secrets file not found: {SECRETS_FILE}")
        return
    
    if not args.command:
        parser.print_help()
        return
    
    # Resolve connection credentials
    if args.host:
        # Load from secrets file
        creds = load_host_credentials(args.host)
        ip = creds['ip']
        user = creds['user']
        password = creds.get('password')
        key = None
        print(f"🔑 Using credentials for '{args.host}' ({ip})")
    else:
        # Manual mode - require --ip for commands that need connection
        if not args.ip:
            parser.error("--host or --ip is required for this command")
        ip = args.ip
        user = args.user or "pi"
        password = args.password
        key = args.key
    
    # Create printer instance
    printer = KlipperPrinter(ip, user, key, password)
    
    # Execute command
    if args.command == "upload":
        printer.upload_gcode(args.file, args.name)
        
    elif args.command == "start":
        printer.start_print(args.filename)
        
    elif args.command == "monitor":
        printer.monitor_live()
        
    elif args.command == "verify":
        printer.verify_belt_coordinates(args.samples)
        
    elif args.command == "log":
        if args.live:
            printer.watch_log_live()
        else:
            printer.tail_klipper_log(args.lines)
            
    elif args.command == "status":
        status = printer.get_status()
        print(json.dumps(status, indent=2))
        
    elif args.command == "pause":
        printer.pause_print()
        
    elif args.command == "resume":
        printer.resume_print()
        
    elif args.command == "cancel":
        printer.cancel_print()
        
    elif args.command == "emergency":
        printer.emergency_stop()


if __name__ == "__main__":
    main()
