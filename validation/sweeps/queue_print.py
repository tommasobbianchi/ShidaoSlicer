#!/usr/bin/env python3
"""Upload gate-OK sweep gcodes to IdeaFormer and submit them to the
Moonraker job queue in declared order. Skips FAIL/missing gcodes.

The IdeaFormer's Moonraker prints jobs sequentially from the queue —
this is exactly the "stampe seriali in queue" pathway the user picked.

Workflow:
  1. read sweep_summary.json
  2. for each variant whose gate is PASS or WARN: scp the gcode to
     printer_data/gcodes/sweep_v2/<label>.gcode (sshpass)
  3. POST /server/job_queue/job?filenames=sweep_v2/0base.gcode,sweep_v2/1d05.gcode,...
  4. POST /server/job_queue/start (unpauses the queue → starts printing)

CLI:
  --dry-run            print what would happen, don't upload or start
  --start              after uploading, also start the queue (default off)
  --include LABEL,...  only these labels (else: all gate≠FAIL with a gcode)
  --exclude LABEL,...  drop these labels
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, urllib.request, urllib.parse

REPO    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY = os.path.join(REPO, "validation/sweeps/support_v2/sweep_summary.json")

PRINTER_HOST = "<PRINTER_HOST>"
SSH_USER     = "ideaformer"
SSH_PASS     = "1234"
REMOTE_DIR   = "printer_data/gcodes/sweep_v2"
MOONRAKER    = f"http://{PRINTER_HOST}:7125"

def sshpass_scp(local, remote):
    return subprocess.run(
        ["sshpass", "-p", SSH_PASS, "scp", "-o", "StrictHostKeyChecking=no",
         local, f"{SSH_USER}@{PRINTER_HOST}:{remote}"],
        capture_output=True, text=True, timeout=120,
    )

def sshpass_ssh(cmd):
    return subprocess.run(
        ["sshpass", "-p", SSH_PASS, "ssh", "-o", "StrictHostKeyChecking=no",
         f"{SSH_USER}@{PRINTER_HOST}", cmd],
        capture_output=True, text=True, timeout=30,
    )

def http_post(path):
    req = urllib.request.Request(f"{MOONRAKER}{path}", method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()

def http_get(path):
    with urllib.request.urlopen(f"{MOONRAKER}{path}", timeout=10) as r:
        return r.read().decode()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start", action="store_true",
                    help="unpause the Moonraker queue after uploading (start prints)")
    ap.add_argument("--include")
    ap.add_argument("--exclude")
    args = ap.parse_args()

    if not os.path.exists(SUMMARY):
        sys.exit(f"summary missing: {SUMMARY}")
    with open(SUMMARY) as f:
        rows = json.load(f)

    eligible = []
    for r in rows:
        if not r.get("ok") or not r.get("out_gcode"):
            continue
        gate = r.get("gate", "?")
        if gate == "FAIL":
            continue
        eligible.append(r)

    if args.include:
        keep = set(s.strip() for s in args.include.split(","))
        eligible = [r for r in eligible if r["label"] in keep]
    if args.exclude:
        drop = set(s.strip() for s in args.exclude.split(","))
        eligible = [r for r in eligible if r["label"] not in drop]

    if not eligible:
        sys.exit("no eligible gcodes (gate PASS/WARN with out_gcode)")

    print(f"Eligible: {len(eligible)} variants")
    for r in eligible:
        print(f"  {r['label']:6s} gate={r.get('gate','?')} size={r.get('gcode_size','?')}")

    if args.dry_run:
        print("\n--dry-run: no uploads, no queue change.")
        return

    # 1. Ensure remote dir exists
    rc = sshpass_ssh(f"mkdir -p {REMOTE_DIR}")
    if rc.returncode != 0:
        sys.exit(f"mkdir failed: {rc.stderr or rc.stdout}")

    # 2. Upload each gcode
    uploaded = []
    for r in eligible:
        label = r["label"]
        local = r["out_gcode"]
        remote_rel = f"sweep_v2/{label}.gcode"
        remote_abs = f"{REMOTE_DIR}/{label}.gcode"
        print(f"  upload  {os.path.basename(local)} → {remote_abs}", flush=True)
        cp = sshpass_scp(local, remote_abs)
        if cp.returncode != 0:
            print(f"  ERROR scp {label}: {cp.stderr or cp.stdout}", flush=True)
            continue
        uploaded.append((label, remote_rel))

    if not uploaded:
        sys.exit("no successful uploads")

    # 3. Submit to job_queue (preserves declared order)
    filenames = ",".join(remote for _, remote in uploaded)
    qs = urllib.parse.urlencode({"filenames": filenames})
    print(f"\nSubmitting to Moonraker queue: {len(uploaded)} jobs")
    resp = http_post(f"/server/job_queue/job?{qs}")
    print(resp[:300])

    # 4. Optionally start the queue
    if args.start:
        print("\nStarting queue (state → ready)…")
        resp = http_post("/server/job_queue/start")
        print(resp[:300])
    else:
        print("\nQueue NOT started (omit --start to keep paused).")
        print(f"Manual start: curl -X POST {MOONRAKER}/server/job_queue/start")

    # 5. Final status
    print("\nFinal queue status:")
    print(http_get("/server/job_queue/status")[:600])

if __name__ == "__main__":
    main()
