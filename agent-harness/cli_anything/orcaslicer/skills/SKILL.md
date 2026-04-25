# cli-anything-orcaslicer

## Overview
CLI harness for OrcaSlicer belt printer fork. Manages 3MF files, invokes headless slicing, validates belt G-code safety, and uploads to IdeaFormer IR3 V2.

## Commands

### 3MF Management
```bash
cli-anything-orcaslicer project info <model.3mf>
cli-anything-orcaslicer project get-setting <3mf> <key>
cli-anything-orcaslicer project set-setting <3mf> <key> <value>
cli-anything-orcaslicer project list-settings <3mf> [--filter <substring>]
```

### Slicing
```bash
cli-anything-orcaslicer slice <model.3mf> [-o output_dir] [--load-settings preset.json]
```

### Validation
```bash
cli-anything-orcaslicer validate <file.gcode>
```
Runs 9 belt-safety rules (R1-R9). Exit 0=PASS, 1=FAIL, 2=WARN.

### Upload
```bash
cli-anything-orcaslicer upload <file.gcode> [--name filename_on_printer.gcode]
```
Validates before upload. Blocks on FAIL.

### Full Pipeline
```bash
cli-anything-orcaslicer pipeline <model.3mf> [--upload] [--name NAME] [-o dir]
```
Slice -> Validate -> Upload (if --upload and PASS).

## JSON Mode
Add `--json` before the subcommand for machine-readable output:
```bash
cli-anything-orcaslicer --json project info model.3mf
cli-anything-orcaslicer --json pipeline model.3mf --upload
```

## Environment Variables
- `ORCA_SLICER_BIN` — Override orca-slicer binary path
- `BELT_GATE_SCRIPT` — Override belt_gcode_gate.py path
- `IDEAFORMER_USER` / `IDEAFORMER_PASS` — Override printer credentials

## REPL Mode
Run without arguments for interactive REPL:
```bash
cli-anything-orcaslicer
```
