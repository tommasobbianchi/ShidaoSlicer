#!/usr/bin/env python3
"""cli-anything-orcaslicer — CLI harness for OrcaSlicer belt printer fork.

Provides subcommand and REPL interfaces for:
- 3MF settings management
- Headless slicing
- Belt G-code validation (9-rule safety gate)
- Upload to IdeaFormer IR3 V2 belt printer
- Full pipeline: slice -> validate -> upload
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from cli_anything.orcaslicer.core import threemf, slicer, validate, upload


# ── JSON output helper ─────────────────────────────────────────────────

def _output(data: dict, use_json: bool):
    """Print data as JSON or human-readable."""
    if use_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        for k, v in data.items():
            if isinstance(v, dict):
                click.echo(f"  {k}:")
                for kk, vv in v.items():
                    click.echo(f"    {kk}: {vv}")
            elif isinstance(v, list):
                click.echo(f"  {k}: [{len(v)} items]")
            else:
                click.echo(f"  {k}: {v}")


# ── Main CLI group ─────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Machine-readable JSON output")
@click.pass_context
def cli(ctx, use_json):
    """cli-anything-orcaslicer — OrcaSlicer belt printer CLI harness."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json

    if ctx.invoked_subcommand is None:
        # REPL mode
        _run_repl(ctx)


# ── project group ──────────────────────────────────────────────────────

@cli.group()
@click.pass_context
def project(ctx):
    """3MF project file management."""
    pass


@project.command("info")
@click.argument("model_3mf", type=click.Path(exists=True))
@click.pass_context
def project_info(ctx, model_3mf):
    """Show 3MF file info and key settings."""
    use_json = ctx.obj.get("json", False)
    try:
        data = threemf.info(model_3mf)
        if use_json:
            click.echo(json.dumps(data, indent=2, default=str))
        else:
            click.echo(f"\n  3MF: {data['path']}")
            click.echo(f"  Size: {data['size_bytes']} bytes")
            click.echo(f"  Files: {data['file_count']}")
            click.echo(f"  Settings: {data['settings_count']}")
            if data["key_settings"]:
                click.echo("\n  Key settings:")
                for k, v in data["key_settings"].items():
                    click.echo(f"    {k} = {v}")
            if data["belt_settings"]:
                click.echo("\n  Belt settings:")
                for k, v in data["belt_settings"].items():
                    click.echo(f"    {k} = {v}")
            click.echo()
    except Exception as e:
        if use_json:
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


@project.command("get-setting")
@click.argument("model_3mf", type=click.Path(exists=True))
@click.argument("key")
@click.pass_context
def project_get_setting(ctx, model_3mf, key):
    """Get a specific setting from a 3MF file."""
    use_json = ctx.obj.get("json", False)
    try:
        value = threemf.get_setting(model_3mf, key)
        if use_json:
            click.echo(json.dumps({"key": key, "value": value}, default=str))
        else:
            if value is None:
                click.echo(f"  {key}: (not set)")
            else:
                click.echo(f"  {key} = {value}")
    except Exception as e:
        if use_json:
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


@project.command("set-setting")
@click.argument("model_3mf", type=click.Path(exists=True))
@click.argument("key")
@click.argument("value")
@click.pass_context
def project_set_setting(ctx, model_3mf, key, value):
    """Modify a setting in a 3MF file (in-place)."""
    use_json = ctx.obj.get("json", False)
    try:
        threemf.set_setting(model_3mf, key, value)
        new_val = threemf.get_setting(model_3mf, key)
        if use_json:
            click.echo(json.dumps({"key": key, "value": new_val, "success": True}, default=str))
        else:
            click.echo(f"  Set {key} = {new_val}")
    except Exception as e:
        if use_json:
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


@project.command("from-stl")
@click.argument("stl", type=click.Path(exists=True))
@click.argument("output_3mf", type=click.Path())
@click.option("--support", is_flag=True, default=False, help="Enable support generation")
@click.option("--layer-height", type=float, default=0.2, help="Layer height in mm")
@click.pass_context
def project_from_stl(ctx, stl, output_3mf, support, layer_height):
    """Create a belt-printer 3MF from an STL file."""
    use_json = ctx.obj.get("json", False)
    try:
        out = threemf.from_stl(stl, output_3mf, enable_support=support, layer_height=layer_height)
        result = {"success": True, "output": str(out), "support": support, "layer_height": layer_height}
        if use_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"  Created: {out}")
    except Exception as e:
        if use_json:
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


@project.command("list-settings")
@click.argument("model_3mf", type=click.Path(exists=True))
@click.option("--filter", "key_filter", default="", help="Filter keys containing this substring")
@click.pass_context
def project_list_settings(ctx, model_3mf, key_filter):
    """List all settings in a 3MF file."""
    use_json = ctx.obj.get("json", False)
    try:
        settings = threemf.read_settings(model_3mf)
        if key_filter:
            settings = {k: v for k, v in settings.items() if key_filter.lower() in k.lower()}
        if use_json:
            click.echo(json.dumps(settings, indent=2, default=str))
        else:
            for k in sorted(settings):
                v = settings[k]
                if isinstance(v, list) and len(v) == 1:
                    v = v[0]
                click.echo(f"  {k} = {v}")
    except Exception as e:
        if use_json:
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


# ── slice command ──────────────────────────────────────────────────────

@cli.command("slice")
@click.argument("model_3mf", type=click.Path(exists=True))
@click.option("-o", "--output-dir", type=click.Path(), default=None,
              help="Output directory for G-code")
@click.option("--load-settings", type=click.Path(exists=True), default=None,
              help="JSON preset file to override settings")
@click.option("--timeout", type=int, default=300, help="Max slicing time in seconds")
@click.pass_context
def slice_cmd(ctx, model_3mf, output_dir, load_settings, timeout):
    """Slice a 3MF model using OrcaSlicer headless CLI."""
    use_json = ctx.obj.get("json", False)

    if not use_json:
        click.echo(f"  Slicing {Path(model_3mf).name}...")

    result = slicer.slice_model(model_3mf, output_dir, load_settings, timeout)

    if use_json:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        if result["success"]:
            click.echo(f"  OK: {result['gcode_path']}")
            click.echo(f"  Duration: {result['duration_s']}s")
        else:
            click.echo(f"  FAILED: {result.get('error', result.get('stderr', 'unknown'))}", err=True)
            if result.get("stderr"):
                # Show last 5 lines of stderr
                lines = result["stderr"].strip().splitlines()[-5:]
                for line in lines:
                    click.echo(f"    {line}", err=True)
    if not result["success"]:
        sys.exit(1)


# ── validate command ───────────────────────────────────────────────────

@cli.command("validate")
@click.argument("gcode", type=click.Path(exists=True))
@click.pass_context
def validate_cmd(ctx, gcode):
    """Run belt G-code validation gate (9 safety rules)."""
    use_json = ctx.obj.get("json", False)

    report = validate.validate_gcode(gcode)

    if use_json:
        click.echo(json.dumps(report, indent=2, default=str))
    else:
        click.echo()
        click.echo(validate.format_report(report))
        click.echo()

    if report.get("result") == "FAIL":
        sys.exit(1)
    elif report.get("result") == "WARN":
        sys.exit(2)


# ── upload command ─────────────────────────────────────────────────────

@cli.command("upload")
@click.argument("gcode", type=click.Path(exists=True))
@click.option("--name", default=None, help="Filename on printer")
@click.option("--skip-validation", is_flag=True, help="Skip safety validation (dangerous)")
@click.pass_context
def upload_cmd(ctx, gcode, name, skip_validation):
    """Upload G-code to IdeaFormer belt printer (validates first)."""
    use_json = ctx.obj.get("json", False)

    # Validate first unless skipped
    if not skip_validation:
        if not use_json:
            click.echo("  Validating G-code...")
        report = validate.validate_gcode(gcode)
        if not validate.is_safe_to_upload(report):
            result = {
                "success": False,
                "error": f"Validation {report.get('result', 'FAIL')} — upload blocked",
                "validation": report,
            }
            if use_json:
                click.echo(json.dumps(result, indent=2, default=str))
            else:
                click.echo(f"  BLOCKED: Validation {report.get('result')} — will not upload unsafe G-code")
                click.echo(validate.format_report(report))
            sys.exit(1)
        elif not use_json:
            click.echo("  Validation PASSED")

    if not use_json:
        click.echo(f"  Uploading {Path(gcode).name}...")

    result = upload.upload_gcode(gcode, name)

    if use_json:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        if result["success"]:
            click.echo(f"  OK: uploaded to {result['dest']}")
        else:
            click.echo(f"  FAILED: {result.get('error', 'unknown')}", err=True)
            sys.exit(1)


# ── pipeline command ───────────────────────────────────────────────────

@cli.command("pipeline")
@click.argument("model_3mf", type=click.Path(exists=True))
@click.option("-o", "--output-dir", type=click.Path(), default=None,
              help="Output directory for G-code")
@click.option("--upload", "do_upload", is_flag=True, help="Upload to printer on PASS")
@click.option("--name", default=None, help="Filename on printer")
@click.option("--load-settings", type=click.Path(exists=True), default=None,
              help="JSON preset file")
@click.pass_context
def pipeline_cmd(ctx, model_3mf, output_dir, do_upload, name, load_settings):
    """Full pipeline: slice -> validate -> upload."""
    use_json = ctx.obj.get("json", False)
    results = {"stages": {}}

    # Stage 1: Slice
    if not use_json:
        click.echo(f"\n  [1/3] Slicing {Path(model_3mf).name}...")
    slice_result = slicer.slice_model(model_3mf, output_dir, load_settings)
    results["stages"]["slice"] = slice_result

    if not slice_result["success"]:
        results["success"] = False
        results["error"] = "Slicing failed"
        if use_json:
            click.echo(json.dumps(results, indent=2, default=str))
        else:
            click.echo(f"  FAILED at slicing: {slice_result.get('error', 'unknown')}")
        sys.exit(1)

    gcode_path = slice_result["gcode_path"]
    if not use_json:
        click.echo(f"  OK: {gcode_path} ({slice_result['duration_s']}s)")

    # Stage 2: Validate
    if not use_json:
        click.echo(f"\n  [2/3] Validating...")
    val_report = validate.validate_gcode(gcode_path)
    results["stages"]["validate"] = val_report

    if not use_json:
        click.echo(f"  Result: {val_report.get('result', 'UNKNOWN')}")
        for check in val_report.get("checks", []):
            status = check.get("status", "?")
            rule = check.get("rule", "?")
            if status != "OK":
                click.echo(f"    {status} [{rule}] {check.get('message', '')}")

    # Stage 3: Upload (optional)
    if do_upload:
        if validate.is_safe_to_upload(val_report):
            if not use_json:
                click.echo(f"\n  [3/3] Uploading to IdeaFormer...")
            upload_result = upload.upload_gcode(gcode_path, name)
            results["stages"]["upload"] = upload_result
            if not use_json:
                if upload_result["success"]:
                    click.echo(f"  OK: {upload_result['dest']}")
                else:
                    click.echo(f"  FAILED: {upload_result.get('error')}")
        else:
            results["stages"]["upload"] = {
                "success": False,
                "error": f"Blocked — validation {val_report.get('result')}",
            }
            if not use_json:
                click.echo(f"\n  [3/3] Upload BLOCKED — validation {val_report.get('result')}")
    else:
        if not use_json:
            click.echo(f"\n  [3/3] Upload skipped (use --upload to enable)")

    results["success"] = slice_result["success"] and val_report.get("result") != "FAIL"
    results["gcode_path"] = gcode_path

    if use_json:
        click.echo(json.dumps(results, indent=2, default=str))
    elif not use_json:
        click.echo()

    if val_report.get("result") == "FAIL":
        sys.exit(1)


# ── simulate command ───────────────────────────────────────────────────

_MODELS_DIR = Path("/home/user/projects/ORCA_BELT/validation/test_models")
_EXPECTED_LAYERS = {
    # model_stem: (expected_layers, description)
    # Formula: layers = (Y_max + Z_max) / (layer_height / cos(45°)) = (Y_max + Z_max) / 0.283
    "inverted_L":       (106, "Y+Z=30mm → 30/0.283≈106"),
    "arc_bridge":       (159, "Y+Z=45mm → 45/0.283≈159"),
    "box_10x10x10":     ( 71, "Y+Z=20mm → 20/0.283≈71 (10mm cube)"),
    "box_20x20x20":     (141, "Y+Z=40mm → 40/0.283≈141 (20mm cube)"),
    "cylinder_d20_h20": (106, "Y+Z=30mm → 30/0.283≈106 (r=10, h=20)"),
}


@cli.command("simulate")
@click.argument("models", nargs=-1)
@click.option("--all-models", is_flag=True, help="Simulate all available test models")
@click.option("-o", "--output-dir", type=click.Path(), default="/tmp/orca_simulate",
              help="Output directory for G-code files")
@click.option("--timeout", type=int, default=120, help="Timeout per model in seconds")
@click.pass_context
def simulate_cmd(ctx, models, all_models, output_dir, timeout):
    """Slice multiple test models and report layer counts.

    MODELS can be STL paths or model names from validation/test_models/.
    Use --all-models to simulate all known test models.

    Example:
      cli-anything-orcaslicer simulate inverted_L arc_bridge box_10x10x10
      cli-anything-orcaslicer simulate --all-models
      cli-anything-orcaslicer --json simulate --all-models
    """
    import tempfile as _tmp
    use_json = ctx.obj.get("json", False)
    output_dir = Path(output_dir)

    # Resolve model list
    model_paths: list[tuple[str, Path]] = []
    if all_models:
        for stl in sorted(_MODELS_DIR.glob("*.stl")):
            model_paths.append((stl.stem, stl))
    else:
        for m in models:
            p = Path(m)
            if p.exists():
                model_paths.append((p.stem, p))
            else:
                # Try test_models dir
                candidate = _MODELS_DIR / f"{m}.stl"
                if candidate.exists():
                    model_paths.append((m, candidate))
                else:
                    if use_json:
                        pass  # will report as error below
                    else:
                        click.echo(f"  Warning: model '{m}' not found, skipping", err=True)

    if not model_paths:
        msg = "No models to simulate. Use model names from validation/test_models/ or --all-models"
        if use_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"  Error: {msg}", err=True)
        sys.exit(1)

    results = []
    for name, stl_path in model_paths:
        if not use_json:
            click.echo(f"\n  [{name}] Creating 3MF...")

        # Create temp 3MF
        work_dir = output_dir / name
        work_dir.mkdir(parents=True, exist_ok=True)
        tmf = work_dir / f"{name}_belt.3mf"

        try:
            threemf.from_stl(stl_path, tmf)
        except Exception as e:
            results.append({"model": name, "success": False, "error": f"3MF creation failed: {e}"})
            if not use_json:
                click.echo(f"  Error creating 3MF: {e}", err=True)
            continue

        if not use_json:
            click.echo(f"  [{name}] Slicing...")

        result = slicer.slice_model(tmf, work_dir, timeout=timeout)
        entry = {
            "model": name,
            "stl": str(stl_path),
            "success": result["success"],
            "layer_count": result.get("layer_count"),
            "gcode_path": result.get("gcode_path"),
            "duration_s": result.get("duration_s"),
        }

        # Compare against expected if known
        if name in _EXPECTED_LAYERS:
            expected, note = _EXPECTED_LAYERS[name]
            actual = result.get("layer_count")
            entry["expected_layers"] = expected
            entry["expected_note"] = note
            if actual is not None:
                entry["layer_match"] = abs(actual - expected) <= 2
            else:
                entry["layer_match"] = None

        if not result["success"]:
            entry["error"] = result.get("error") or result.get("stderr", "")[-200:]

        results.append(entry)

        if not use_json:
            ok = "✓" if result["success"] else "✗"
            layers = result.get("layer_count", "?")
            dur = result.get("duration_s", "?")
            click.echo(f"  {ok} layers={layers}  time={dur}s")
            if name in _EXPECTED_LAYERS:
                exp, note = _EXPECTED_LAYERS[name]
                match = entry.get("layer_match")
                sym = "✓" if match else ("~" if match is None else "✗")
                click.echo(f"    {sym} expected≈{exp}  ({note})")
            if not result["success"]:
                click.echo(f"    Error: {entry.get('error', '')[:120]}", err=True)

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["success"]),
        "layer_matches": sum(1 for r in results if r.get("layer_match") is True),
        "results": results,
    }

    if use_json:
        click.echo(json.dumps(summary, indent=2, default=str))
    else:
        click.echo(f"\n  Summary: {summary['passed']}/{summary['total']} sliced OK, "
                   f"{summary['layer_matches']} layer counts match expected\n")

    if summary["passed"] < summary["total"]:
        sys.exit(1)


# ── REPL mode ──────────────────────────────────────────────────────────

def _run_repl(ctx):
    """Interactive REPL mode."""
    try:
        from cli_anything.orcaslicer.utils.repl_skin import ReplSkin
        skin = ReplSkin("orcaslicer", version="1.0.0")
        skin.print_banner()
    except ImportError:
        skin = None
        click.echo("cli-anything-orcaslicer REPL v1.0.0")
        click.echo("Type 'help' for commands, 'quit' to exit.\n")

    commands = {
        "project info <3mf>": "Show 3MF file info",
        "project from-stl <stl> <out.3mf>": "Create 3MF from STL",
        "project get-setting <3mf> <key>": "Get a setting",
        "project set-setting <3mf> <key> <val>": "Set a setting",
        "project list-settings <3mf>": "List all settings",
        "simulate [model...] [--all-models]": "Batch slice test models",
        "slice <3mf> [-o dir]": "Slice model",
        "validate <gcode>": "Run belt validation",
        "upload <gcode> [--name N]": "Upload to printer",
        "pipeline <3mf> [--upload]": "Full pipeline",
        "help": "Show this help",
        "quit": "Exit REPL",
    }

    while True:
        try:
            if skin:
                prompt_str = skin.prompt()
                line = input(prompt_str).strip()
            else:
                line = input("orca> ").strip()
        except (EOFError, KeyboardInterrupt):
            if skin:
                skin.print_goodbye()
            break

        if not line:
            continue

        if line in ("quit", "exit", "q"):
            if skin:
                skin.print_goodbye()
            break

        if line == "help":
            if skin:
                skin.help(commands)
            else:
                for cmd, desc in commands.items():
                    click.echo(f"  {cmd:40s} {desc}")
            continue

        # Parse and dispatch via click
        try:
            args = line.split()
            ctx_obj = {"json": False}
            cli.main(args, standalone_mode=False, obj=ctx_obj)
        except SystemExit:
            pass  # Click raises SystemExit on error; absorb in REPL
        except Exception as e:
            if skin:
                skin.error(str(e))
            else:
                click.echo(f"  Error: {e}", err=True)


# ── Entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
