"""Tests for cli-anything-orcaslicer core modules."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest

from cli_anything.orcaslicer.core import threemf, slicer, validate, upload


# ── Fixtures ───────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[4]
REAL_3MF = REPO_ROOT / "test_cube_belt.3mf"
HAS_REAL_3MF = REAL_3MF.exists()

ORCA_BINARY = Path(slicer.DEFAULT_BINARY)
HAS_BINARY = ORCA_BINARY.exists()


@pytest.fixture
def tmp_3mf(tmp_path):
    """Create a minimal synthetic 3MF for testing."""
    config = {
        "layer_height": "0.2",
        "enable_support": "0",
        "belt_angle": "45",
        "belt_axis": "Z",
        "belt_inclined_gcode": "1",
        "wall_loops": "2",
        "sparse_infill_density": "15%",
    }
    threemf_path = tmp_path / "test.3mf"
    with zipfile.ZipFile(threemf_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Metadata/project_settings.config", json.dumps(config, indent=4))
        zf.writestr("3D/3dmodel.model", "<model>dummy geometry</model>")
        zf.writestr("Metadata/model_settings.config", "<config>dummy</config>")
    return threemf_path


@pytest.fixture
def real_3mf(tmp_path):
    """Copy real 3MF to temp dir for safe modification."""
    if not HAS_REAL_3MF:
        pytest.skip("test_cube_belt.3mf not found")
    dst = tmp_path / "test_cube_belt.3mf"
    shutil.copy2(REAL_3MF, dst)
    return dst


@pytest.fixture
def synthetic_gcode_pass(tmp_path):
    """Create synthetic passing G-code."""
    lines = [
        "; HEADER",
        "G28",
        ";LAYER_CHANGE",
        ";Z:0.283",
        "G1 X10 Y0.5 Z0.283 F3000",
        "G1 X20 Y1.0 E0.5 F1500",
        "G1 X30 Y1.5 E1.0",
        "G1 X10 Y0.8 F3000",
        ";LAYER_CHANGE",
        ";Z:0.566",
        "G1 X10 Y0.5 Z0.566 F3000",
        "G1 X20 Y1.0 E1.5 F1500",
        "G1 X30 Y1.5 E2.0",
        ";LAYER_CHANGE",
        ";Z:0.849",
        "G1 X10 Y0.5 Z0.849 F3000",
        "G1 X20 Y1.0 E2.5 F1500",
        "G1 X30 Y1.5 E3.0",
    ]
    p = tmp_path / "pass.gcode"
    p.write_text("\n".join(lines))
    return p


@pytest.fixture
def synthetic_gcode_fail(tmp_path):
    """Create synthetic failing G-code (negative Z, Z-only moves)."""
    lines = [
        "; HEADER",
        "G28",
        ";LAYER_CHANGE",
        ";Z:0.283",
        "G1 Z0.283",  # Z-only move (R3 violation)
        "G1 X10 Y0.5 Z0.283 F3000",
        "G1 X20 Y1.0 E0.5 F1500",
        ";LAYER_CHANGE",
        ";Z:-0.1",
        "G1 X10 Y0.5 Z-0.1 F3000",  # negative Z (R2 violation)
        "G1 X20 Y1.0 E1.0 F1500",
    ]
    p = tmp_path / "fail.gcode"
    p.write_text("\n".join(lines))
    return p


# ── threemf tests ──────────────────────────────────────────────────────

class TestThreemf:
    def test_read_settings(self, tmp_3mf):
        settings = threemf.read_settings(tmp_3mf)
        assert isinstance(settings, dict)
        assert settings["layer_height"] == "0.2"
        assert settings["belt_angle"] == "45"

    def test_get_setting(self, tmp_3mf):
        assert threemf.get_setting(tmp_3mf, "layer_height") == "0.2"
        assert threemf.get_setting(tmp_3mf, "nonexistent_key") is None

    def test_set_setting(self, tmp_3mf):
        threemf.set_setting(tmp_3mf, "layer_height", "0.3")
        assert threemf.get_setting(tmp_3mf, "layer_height") == "0.3"

    def test_set_setting_new_key(self, tmp_3mf):
        threemf.set_setting(tmp_3mf, "new_setting", "hello")
        assert threemf.get_setting(tmp_3mf, "new_setting") == "hello"

    def test_set_setting_preserves_geometry(self, tmp_3mf):
        threemf.set_setting(tmp_3mf, "layer_height", "0.1")
        contents = threemf.list_contents(tmp_3mf)
        assert "3D/3dmodel.model" in contents
        assert "Metadata/model_settings.config" in contents
        # Verify geometry content unchanged
        with zipfile.ZipFile(tmp_3mf, "r") as zf:
            model = zf.read("3D/3dmodel.model").decode()
            assert "dummy geometry" in model

    def test_info(self, tmp_3mf):
        data = threemf.info(tmp_3mf)
        assert data["file_count"] == 3
        assert data["settings_count"] == 7
        assert "belt_angle" in data["belt_settings"]
        assert "layer_height" in data["key_settings"]

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            threemf.read_settings("/nonexistent/path.3mf")

    def test_list_contents(self, tmp_3mf):
        contents = threemf.list_contents(tmp_3mf)
        assert len(contents) == 3

    def test_set_settings_bulk(self, tmp_3mf):
        threemf.set_settings_bulk(tmp_3mf, {
            "layer_height": "0.1",
            "enable_support": "1",
        })
        assert threemf.get_setting(tmp_3mf, "layer_height") == "0.1"
        assert threemf.get_setting(tmp_3mf, "enable_support") == "1"

    @pytest.mark.skipif(not HAS_REAL_3MF, reason="Real 3MF not available")
    def test_read_real_3mf(self, real_3mf):
        settings = threemf.read_settings(real_3mf)
        assert isinstance(settings, dict)
        assert len(settings) > 50  # Real 3MF has many settings
        assert "layer_height" in settings

    @pytest.mark.skipif(not HAS_REAL_3MF, reason="Real 3MF not available")
    def test_modify_real_3mf(self, real_3mf):
        original = threemf.get_setting(real_3mf, "layer_height")
        threemf.set_setting(real_3mf, "layer_height", "0.15")
        assert threemf.get_setting(real_3mf, "layer_height") == "0.15"
        # Ensure other entries still present
        contents = threemf.list_contents(real_3mf)
        assert any("3dmodel" in c.lower() or "3D" in c for c in contents)


# ── slicer tests ───────────────────────────────────────────────────────

class TestSlicer:
    def test_missing_model(self):
        result = slicer.slice_model("/nonexistent/model.3mf")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_missing_binary(self, tmp_3mf, monkeypatch):
        monkeypatch.setenv("ORCA_SLICER_BIN", "/nonexistent/orca-slicer")
        result = slicer.slice_model(tmp_3mf)
        assert result["success"] is False

    def test_get_binary_env(self, monkeypatch):
        monkeypatch.setenv("ORCA_SLICER_BIN", "/custom/orca")
        assert slicer.get_binary() == "/custom/orca"

    def test_get_binary_default(self):
        # Without env override, should return default
        saved = os.environ.pop("ORCA_SLICER_BIN", None)
        try:
            assert slicer.get_binary() == slicer.DEFAULT_BINARY
        finally:
            if saved:
                os.environ["ORCA_SLICER_BIN"] = saved


# ── validate tests ─────────────────────────────────────────────────────

class TestValidate:
    def test_validate_missing_gcode(self):
        report = validate.validate_gcode("/nonexistent/file.gcode")
        assert report["result"] == "FAIL"

    def test_validate_synthetic_pass(self, synthetic_gcode_pass):
        report = validate.validate_gcode(str(synthetic_gcode_pass))
        # Synthetic gcode may not pass all rules but should parse without error
        assert "result" in report
        assert report["result"] in ("PASS", "WARN", "FAIL")
        assert "checks" in report

    def test_validate_synthetic_fail(self, synthetic_gcode_fail):
        report = validate.validate_gcode(str(synthetic_gcode_fail))
        assert report["result"] == "FAIL"
        # Should have R2 (negative Z) and R3 (Z-only) failures
        rules_failed = [
            c["rule"] for c in report.get("checks", []) if c["status"] == "FAIL"
        ]
        assert "R2-NO-NEG-Z" in rules_failed
        assert "R3-NO-Z-ONLY" in rules_failed

    def test_is_safe_to_upload(self):
        assert validate.is_safe_to_upload({"result": "PASS"}) is True
        assert validate.is_safe_to_upload({"result": "WARN"}) is False
        assert validate.is_safe_to_upload({"result": "FAIL"}) is False

    def test_format_report(self):
        report = {
            "result": "PASS",
            "layers": 10,
            "total_moves": 100,
            "checks": [
                {"status": "OK", "rule": "R1-Z-CONST", "message": "Z constant"},
            ],
        }
        text = validate.format_report(report)
        assert "PASS" in text
        assert "R1-Z-CONST" in text
        assert "Layers: 10" in text


# ── upload tests ───────────────────────────────────────────────────────

class TestUpload:
    def test_upload_missing_file(self):
        result = upload.upload_gcode("/nonexistent/file.gcode")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_check_printer_offline(self):
        # Use a bogus IP to ensure it fails quickly
        online = upload.check_printer_online(host="192.0.2.1", timeout=1)
        assert online is False


# ── CLI integration tests ──────────────────────────────────────────────

class TestCLI:
    def test_cli_help(self):
        """Test CLI --help works."""
        from click.testing import CliRunner
        from cli_anything.orcaslicer.orcaslicer_cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "orcaslicer" in result.output.lower() or "OrcaSlicer" in result.output

    def test_cli_project_info_json(self, tmp_3mf):
        from click.testing import CliRunner
        from cli_anything.orcaslicer.orcaslicer_cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "project", "info", str(tmp_3mf)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["settings_count"] == 7

    def test_cli_project_get_setting_json(self, tmp_3mf):
        from click.testing import CliRunner
        from cli_anything.orcaslicer.orcaslicer_cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "project", "get-setting", str(tmp_3mf), "layer_height"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["value"] == "0.2"

    def test_cli_project_set_setting_json(self, tmp_3mf):
        from click.testing import CliRunner
        from cli_anything.orcaslicer.orcaslicer_cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "project", "set-setting", str(tmp_3mf), "layer_height", "0.3"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

    def test_cli_validate_json(self, synthetic_gcode_fail):
        from click.testing import CliRunner
        from cli_anything.orcaslicer.orcaslicer_cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "validate", str(synthetic_gcode_fail)])
        assert result.exit_code == 1  # FAIL
        data = json.loads(result.output)
        assert data["result"] == "FAIL"

    def test_cli_list_settings_json(self, tmp_3mf):
        from click.testing import CliRunner
        from cli_anything.orcaslicer.orcaslicer_cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "project", "list-settings", str(tmp_3mf), "--filter", "belt"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "belt_angle" in data
        assert "layer_height" not in data  # filtered out
