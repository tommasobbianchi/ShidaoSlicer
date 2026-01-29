#!/usr/bin/env python3
"""
Script per AgentForge: Promemoria periodico assi belt printer.
Esegui ogni 10 minuti con cron o systemd timer.
"""

import os
import sys
from datetime import datetime

REMINDER = """
╔══════════════════════════════════════════════════════════════════╗
║  ⚠️  PROMEMORIA CRITICO - IdeaFormer Belt Printer ⚠️            ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Y (Machine) = ALTEZZA GANTRY (inclinata 45°)                   ║
║      Y = 0  →  Ugello A CONTATTO col nastro                     ║
║      Y > 0  →  Ugello SALE                                      ║
║                                                                  ║
║  Z (Machine) = NASTRO INFINITO                                  ║
║      Z PUÒ SOLO AUMENTARE (nastro avanti!)                      ║
║      MAI comandi Z negativi!                                    ║
║                                                                  ║
║  X (Machine) = LARGHEZZA (standard)                             ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = "/tmp/belt_axis_reminder.log"
    
    # Stampa a console (per AgentForge/cron)
    print(f"\n[{timestamp}] BELT AXIS REMINDER")
    print(REMINDER)
    
    # Log per tracciamento
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] Reminder sent\n")
        
    # INTEGRATION: Memorize this event in Hippocampal context
    # This allows the Agent to know it has been reminded recently
    import subprocess
    script_dir = os.path.dirname(os.path.abspath(__file__))
    delegate_script = os.path.join(script_dir, "delegate_agentforge.py")
    
    try:
        if os.path.exists(delegate_script):
            subprocess.run([
                sys.executable, 
                delegate_script, 
                "memorize", 
                f"Belt Axis Reminder triggered at {timestamp}", 
                "--tag", "REMINDER"
            ], check=False, stdout=subprocess.DEVNULL)
    except Exception as e:
        print(f"⚠️ Failed to memorize reminder: {e}")
    
    # Se eseguito in ambiente interattivo, mostra anche il file completo
    reminder_file = "/home/user/.gemini/antigravity/brain/a781100c-6847-4b7c-9d70-5206bd7c8533/CRITICAL_REMINDER_BELT_AXES.md"
    if os.path.exists(reminder_file):
        print(f"\n📄 Full reminder at: {reminder_file}")

if __name__ == "__main__":
    main()
