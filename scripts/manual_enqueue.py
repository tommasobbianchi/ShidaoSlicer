#!/usr/bin/env python3
import time
import sys
import logging
import os

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(script_dir)

from klipper_remote import KlipperPrinter

# Configuration
PRINTER_IP = "<PRINTER_HOST>"
SSH_USER = "ideaformer"
SSH_PASS = "1234"
GCODE_FILE = "cube_Zfixed.gcode"

def main():
    print(f"🔧 Enqueueing {GCODE_FILE} on {PRINTER_IP}...")
    
    try:
        printer = KlipperPrinter(PRINTER_IP, SSH_USER, ssh_password=SSH_PASS)
        printer.enqueue_job(GCODE_FILE)
    except Exception as e:
        print(f"❌ Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
