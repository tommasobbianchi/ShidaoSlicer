#!/usr/bin/env python3
"""Save validation screenshots from the orca-belt MCP server with consistent naming.

Usage:
  save_screenshot.py --phase 03 --object voron-cube-v7 --view iso --tag sliced \
      --png-base64-file /tmp/ss.b64 [--camera '{"position":[...],...}'] [--validation-json ...]

Writes:
  validation/screenshots/YYYY-MM-DD/phaseNN_seqNNN_<slug>_<view>_<tag>.png
  validation/screenshots/YYYY-MM-DD/phaseNN_seqNNN_<slug>_<view>_<tag>.json
  validation/screenshots/YYYY-MM-DD/INDEX.md (appended)

seq is computed per-day (monotone zero-padded 3 digits).
"""

import argparse
import base64
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "screenshots"


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def next_seq(day_dir: Path) -> int:
    existing = list(day_dir.glob("phase*_seq*_*.png"))
    if not existing:
        return 1
    nums = []
    for p in existing:
        m = re.match(r"phase\d+_seq(\d+)_", p.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) if nums else 0) + 1


def git_sha(binary: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(binary.parent.parent.parent.parent), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def append_index(day_dir: Path, filename: str, meta: dict):
    index = day_dir / "INDEX.md"
    header_needed = not index.exists()
    with index.open("a") as f:
        if header_needed:
            f.write(f"# Validation screenshots — {day_dir.name}\n\n")
            f.write("| File | Phase | Object | View | Tag | Timestamp | Notes |\n")
            f.write("|---|---|---|---|---|---|---|\n")
        notes = meta.get("notes", "")
        f.write(
            f"| `{filename}` | {meta['phase']} | {meta['object']} | {meta['view']} "
            f"| {meta.get('tag','')} | {meta['timestamp_iso']} | {notes} |\n"
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", required=True, help="Two-digit phase number, e.g. 03")
    p.add_argument("--object", required=True, help="Object slug, e.g. voron-cube-v7 or empty-plate")
    p.add_argument("--view", required=True,
                   choices=["iso", "top", "front", "rear", "left", "right", "bottom",
                            "topfront", "preview", "gcode-preview"])
    p.add_argument("--tag", default="", help="Optional state tag: baseline|loaded|keel-placed|sliced|error")
    p.add_argument("--png-base64", default=None, help="PNG content as base64 string")
    p.add_argument("--png-base64-file", default=None, help="Path to file containing base64 PNG")
    p.add_argument("--png-file", default=None, help="Path to existing PNG file to copy")
    p.add_argument("--camera", default=None, help="JSON dict with camera {position, target, zoom}")
    p.add_argument("--validation-json", default=None,
                   help="Path to belt_gcode_gate.py --json output for sliced variants")
    p.add_argument("--notes", default="", help="Short note shown in INDEX.md")
    p.add_argument("--binary", default="/home/user/projects/ORCA_BELT/build/src/Debug/orca-slicer")
    args = p.parse_args()

    now = datetime.datetime.now()
    day_str = now.strftime("%Y-%m-%d")
    day_dir = ROOT / day_str
    day_dir.mkdir(parents=True, exist_ok=True)

    seq = next_seq(day_dir)
    phase = f"phase{int(args.phase):02d}"
    slug = slugify(args.object)
    tag = slugify(args.tag) if args.tag else ""

    parts = [phase, f"seq{seq:03d}", slug, args.view]
    if tag:
        parts.append(tag)
    stem = "_".join(parts)

    png_path = day_dir / f"{stem}.png"
    meta_path = day_dir / f"{stem}.json"

    # Write PNG
    if args.png_base64:
        png_path.write_bytes(base64.b64decode(args.png_base64))
    elif args.png_base64_file:
        b64 = Path(args.png_base64_file).read_text().strip()
        png_path.write_bytes(base64.b64decode(b64))
    elif args.png_file:
        png_path.write_bytes(Path(args.png_file).read_bytes())
    else:
        print("ERROR: one of --png-base64, --png-base64-file, --png-file required", file=sys.stderr)
        sys.exit(2)

    # Gather metadata
    meta = {
        "file": png_path.name,
        "phase": phase,
        "seq": seq,
        "object": args.object,
        "view": args.view,
        "tag": args.tag or None,
        "notes": args.notes,
        "timestamp_iso": now.isoformat(timespec="seconds"),
        "orca_binary": str(args.binary),
        "orca_repo_sha": git_sha(Path(args.binary)),
    }
    if args.camera:
        try:
            meta["camera"] = json.loads(args.camera)
        except json.JSONDecodeError:
            meta["camera_raw"] = args.camera
    if args.validation_json:
        try:
            meta["validation"] = json.loads(Path(args.validation_json).read_text())
        except Exception as e:
            meta["validation_error"] = str(e)

    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    append_index(day_dir, png_path.name, meta)

    print(f"saved: {png_path}")
    print(f"meta:  {meta_path}")


if __name__ == "__main__":
    main()
