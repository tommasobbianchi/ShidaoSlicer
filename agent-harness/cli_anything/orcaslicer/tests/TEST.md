# Test Plan

## Unit Tests (test_core.py)

### threemf module
- test_read_settings: Read settings from a real 3MF file
- test_get_setting: Get a specific setting by key
- test_set_setting: Modify a setting and verify it persists
- test_set_setting_preserves_geometry: Ensure ZIP contents besides config are preserved
- test_info: Get summary info from 3MF
- test_missing_file: Error on nonexistent file
- test_list_contents: List ZIP entries

### slicer module
- test_missing_binary: Graceful error when binary not found
- test_missing_model: Graceful error when 3MF not found

### validate module
- test_validate_missing_gcode: Error on nonexistent file
- test_validate_synthetic_pass: Validate synthetic passing G-code
- test_validate_synthetic_fail: Validate synthetic failing G-code (negative Z)
- test_format_report: Format a report dict as text
- test_is_safe_to_upload: Check PASS/FAIL logic

### upload module
- test_upload_missing_file: Error on nonexistent file
- test_check_printer_offline: Graceful handling when printer unreachable

## Integration Tests (require orca-slicer binary)
- test_slice_real: Slice test_cube_belt.3mf and check output
- test_pipeline: Full slice -> validate pipeline

## Running
```bash
cd /home/user/projects/ORCA_BELT/agent-harness
pytest -v cli_anything/orcaslicer/tests/
```
