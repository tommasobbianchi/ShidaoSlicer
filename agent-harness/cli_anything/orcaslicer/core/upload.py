"""Upload G-code to IdeaFormer IR3 V2 belt printer via SCP."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


# IdeaFormer connection defaults
IDEAFORMER_HOST = "<PRINTER_HOST>"
IDEAFORMER_USER = "ideaformer"
IDEAFORMER_PASS = ""
IDEAFORMER_GCODE_DIR = "printer_data/gcodes"


def upload_gcode(
    gcode_path: str | Path,
    name: str | None = None,
    host: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Upload a G-code file to IdeaFormer via SCP.

    Args:
        gcode_path: Local path to .gcode file.
        name: Filename on the printer. Defaults to source filename.
        host: Override host IP. Defaults to IdeaFormer Tailscale IP.
        timeout: SCP timeout in seconds.

    Returns:
        Dict with keys: success, dest, error (optional).
    """
    gcode_path = Path(gcode_path)
    if not gcode_path.exists():
        return {"success": False, "error": f"G-code file not found: {gcode_path}"}

    dest_name = name or gcode_path.name
    host = host or IDEAFORMER_HOST
    user = os.environ.get("IDEAFORMER_USER", IDEAFORMER_USER)
    password = os.environ.get("IDEAFORMER_PASS", IDEAFORMER_PASS)
    gcode_dir = os.environ.get("IDEAFORMER_GCODE_DIR", IDEAFORMER_GCODE_DIR)

    dest = f"{user}@{host}:{gcode_dir}/{dest_name}"

    try:
        result = subprocess.run(
            ["sshpass", "-p", password, "scp", str(gcode_path), dest],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return {
                "success": True,
                "dest": dest,
                "filename": dest_name,
                "host": host,
            }
        else:
            return {
                "success": False,
                "error": result.stderr.strip() or f"SCP exit code {result.returncode}",
                "dest": dest,
            }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "sshpass not installed. Install with: sudo apt install sshpass",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"SCP timed out after {timeout}s — is IdeaFormer online?",
        }


def check_printer_online(host: str | None = None, timeout: int = 5) -> bool:
    """Check if the IdeaFormer printer is reachable via Tailscale.

    Returns:
        True if reachable, False otherwise.
    """
    host = host or IDEAFORMER_HOST
    try:
        result = subprocess.run(
            ["tailscale", "ping", "-c", "1", "--timeout", f"{timeout}s", host],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
