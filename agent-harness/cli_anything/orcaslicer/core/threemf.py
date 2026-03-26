"""3MF file management — read/write/modify settings inside OrcaSlicer 3MF files.

OrcaSlicer 3MF files are ZIP archives containing:
  - 3D/3dmodel.model          (geometry)
  - Metadata/model_settings.config   (per-object XML config)
  - Metadata/project_settings.config (global JSON config — KEY: VALUE or KEY: [LIST])
  - Metadata/plate_*.gcode    (embedded gcode, optional)
  - Metadata/slice_info.config
  - Thumbnails/               (preview images)
"""

from __future__ import annotations

import io
import json
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path
from typing import Any


CONFIG_PATH = "Metadata/project_settings.config"


def read_settings(threemf_path: str | Path) -> dict[str, Any]:
    """Read all settings from a 3MF project_settings.config.

    Returns:
        Dict of setting_name -> value (str, list, or nested).
    """
    threemf_path = Path(threemf_path)
    if not threemf_path.exists():
        raise FileNotFoundError(f"3MF file not found: {threemf_path}")

    with zipfile.ZipFile(threemf_path, "r") as zf:
        if CONFIG_PATH not in zf.namelist():
            raise ValueError(f"No {CONFIG_PATH} found in {threemf_path}")
        raw = zf.read(CONFIG_PATH).decode("utf-8")

    return json.loads(raw)


def get_setting(threemf_path: str | Path, key: str) -> Any:
    """Get a single setting value from a 3MF file.

    Returns:
        The value (str, list, int, etc.) or None if not found.
    """
    settings = read_settings(threemf_path)
    return settings.get(key)


def set_setting(threemf_path: str | Path, key: str, value: Any) -> Path:
    """Modify a single setting in a 3MF file (in-place).

    Preserves all other ZIP content (geometry, thumbnails, etc.).

    Args:
        threemf_path: Path to the 3MF file.
        key: Setting key (e.g., "enable_support", "layer_height").
        value: New value. Strings are auto-parsed:
               "1"/"0" stay as strings, lists stay as lists.

    Returns:
        Path to the modified 3MF file.
    """
    threemf_path = Path(threemf_path)
    settings = read_settings(threemf_path)

    # Auto-convert numeric strings
    if isinstance(value, str):
        # Try int
        try:
            value = int(value)
            # But some settings like "enable_support" are stored as strings
            # Keep as string if original was string
            if key in settings and isinstance(settings[key], str):
                value = str(value)
        except ValueError:
            # Try float
            try:
                value = float(value)
                if key in settings and isinstance(settings[key], str):
                    value = str(value)
            except ValueError:
                pass

    settings[key] = value
    new_json = json.dumps(settings, indent=4, ensure_ascii=False)

    _rewrite_zip_file(threemf_path, CONFIG_PATH, new_json.encode("utf-8"))
    return threemf_path


def set_settings_bulk(threemf_path: str | Path, updates: dict[str, Any]) -> Path:
    """Modify multiple settings at once in a 3MF file (in-place).

    Args:
        threemf_path: Path to the 3MF file.
        updates: Dict of key -> value pairs to set.

    Returns:
        Path to the modified 3MF file.
    """
    threemf_path = Path(threemf_path)
    settings = read_settings(threemf_path)
    settings.update(updates)
    new_json = json.dumps(settings, indent=4, ensure_ascii=False)
    _rewrite_zip_file(threemf_path, CONFIG_PATH, new_json.encode("utf-8"))
    return threemf_path


def list_contents(threemf_path: str | Path) -> list[str]:
    """List all files inside a 3MF archive."""
    with zipfile.ZipFile(threemf_path, "r") as zf:
        return zf.namelist()


def info(threemf_path: str | Path) -> dict[str, Any]:
    """Get summary info about a 3MF file.

    Returns:
        Dict with keys: path, files, settings_count, belt_settings, key_settings.
    """
    threemf_path = Path(threemf_path)
    contents = list_contents(threemf_path)
    settings = read_settings(threemf_path)

    belt_keys = [k for k in settings if "belt" in k.lower()]
    belt_settings = {k: settings[k] for k in belt_keys}

    key_settings = {}
    for k in [
        "layer_height", "initial_layer_print_height",
        "enable_support", "support_type", "support_style",
        "wall_loops", "sparse_infill_density",
        "print_sequence", "printer_structure",
        "belt_angle", "belt_axis", "belt_inclined_gcode",
    ]:
        if k in settings:
            key_settings[k] = settings[k]

    return {
        "path": str(threemf_path),
        "size_bytes": threemf_path.stat().st_size,
        "files": contents,
        "file_count": len(contents),
        "settings_count": len(settings),
        "belt_settings": belt_settings,
        "key_settings": key_settings,
    }


_REPO = Path("/home/user/projects/ORCA_BELT")
_TEMPLATE_3MF = _REPO / "inverted_L.3mf"


_REPO = Path("/home/user/projects/ORCA_BELT")
_TEMPLATE_3MF = _REPO / "inverted_L.3mf"


def from_stl(
    stl_path: str | Path,
    output_3mf: str | Path,
    *,
    enable_support: bool = False,
    layer_height: float = 0.2,
    template_3mf: str | Path | None = None,
) -> Path:
    """Create a belt-printer 3MF from an STL file.

    Uses inverted_L.3mf as a template (copy + replace geometry). The template
    provides all required OrcaSlicer metadata, thumbnails, and belt settings.

    Args:
        stl_path: Path to input STL file (binary format).
        output_3mf: Path for the output .3mf file.
        enable_support: Whether to enable support generation.
        layer_height: Layer height in mm.
        template_3mf: Override the base template (default: inverted_L.3mf).

    Returns:
        Path to the created 3MF.
    """
    import re as _re

    stl_path = Path(stl_path).resolve()
    output_3mf = Path(output_3mf)
    output_3mf.parent.mkdir(parents=True, exist_ok=True)
    tmpl = Path(template_3mf) if template_3mf else _TEMPLATE_3MF
    if not tmpl.exists():
        raise FileNotFoundError(f"Template 3MF not found: {tmpl}")

    obj_name = stl_path.stem

    # --- Parse binary STL ---
    with open(stl_path, "rb") as f:
        f.read(80)  # header
        num_tri = struct.unpack("<I", f.read(4))[0]
        triangles = []
        for _ in range(num_tri):
            f.read(12)  # normal
            v0 = struct.unpack("<fff", f.read(12))
            v1 = struct.unpack("<fff", f.read(12))
            v2 = struct.unpack("<fff", f.read(12))
            f.read(2)   # attribute
            triangles.append((v0, v1, v2))

    # Deduplicate vertices
    verts: list[tuple] = []
    vert_idx: dict[tuple, int] = {}
    tris_idx: list[tuple[int, int, int]] = []
    for (v0, v1, v2) in triangles:
        idxs = []
        for v in (v0, v1, v2):
            vk = tuple(round(x, 6) for x in v)
            if vk not in vert_idx:
                vert_idx[vk] = len(verts)
                verts.append(vk)
            idxs.append(vert_idx[vk])
        tris_idx.append(tuple(idxs))

    # Build replacement geometry XML
    verts_xml = "\n".join(
        f'     <vertex x="{v[0]}" y="{v[1]}" z="{v[2]}"/>' for v in verts
    )
    tris_xml = "\n".join(
        f'     <triangle v1="{t[0]}" v2="{t[1]}" v3="{t[2]}"/>' for t in tris_idx
    )
    new_geom_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US"\n'
        f'  xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"\n'
        f'  xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">\n'
        f' <resources>\n'
        f'  <object id="1" type="model">\n'
        f'   <mesh>\n'
        f'    <vertices>\n'
        f'{verts_xml}\n'
        f'    </vertices>\n'
        f'    <triangles>\n'
        f'{tris_xml}\n'
        f'    </triangles>\n'
        f'   </mesh>\n'
        f'  </object>\n'
        f' </resources>\n'
        f'</model>'
    )

    # Compute center translation for proper belt printer placement
    # X: center of model at print_center_x=125mm; Y/Z: start at 0/10
    x_vals = [v[0] for v in verts]
    x_min, x_max = min(x_vals), max(x_vals)
    t_x = 125.0 - (x_min + x_max) / 2.0
    t_y = -min(v[1] for v in verts)   # shift Y_min → 0
    t_z = 10.0 - min(v[2] for v in verts)  # shift Z_min → 10 (belt_z_base)

    # Copy template, replacing geometry + updating settings
    with zipfile.ZipFile(tmpl, "r") as zin:
        tmpl_names = zin.namelist()
        # Find the geometry sub-model file (3D/Objects/*.model)
        geom_entry = next(
            (n for n in tmpl_names if n.startswith("3D/Objects/") and n.endswith(".model")),
            None,
        )
        if not geom_entry:
            raise ValueError(f"No geometry sub-model found in template {tmpl}")

        with zipfile.ZipFile(output_3mf, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in tmpl_names:
                if name == geom_entry:
                    zout.writestr(name, new_geom_xml.encode())

                elif name == "3D/3dmodel.model":
                    # Replace item transform with identity rotation + computed translation
                    raw = zin.read(name).decode()
                    raw = _re.sub(
                        r'(<item\b[^>]*)\btransform="[^"]*"',
                        rf'\1transform="1 0 0 0 1 0 0 0 1 {t_x:.6f} {t_y:.6f} {t_z:.6f}"',
                        raw,
                    )
                    zout.writestr(name, raw.encode())

                elif name == "Metadata/project_settings.config":
                    old = json.loads(zin.read(name).decode())
                    old["enable_support"] = "1" if enable_support else "0"
                    old["layer_height"] = str(layer_height)
                    old["initial_layer_print_height"] = str(layer_height)
                    zout.writestr(name, json.dumps(old, indent=4).encode())

                elif name == "Metadata/model_settings.config":
                    raw = zin.read(name).decode()
                    # Remove support_part block (part with name="support")
                    raw = _re.sub(
                        r'\s*<part\b[^>]*>\s*(?:<metadata[^/]*/>\s*)*'
                        r'<metadata key="name" value="support"[^/]*/>\s*(?:<metadata[^/]*/>\s*)*</part>',
                        "", raw, flags=_re.DOTALL
                    )
                    zout.writestr(name, raw.encode())

                else:
                    zout.writestr(name, zin.read(name))

    return output_3mf


def _rewrite_zip_file(zip_path: Path, target_entry: str, new_data: bytes):
    """Rewrite a single file inside a ZIP, preserving all other entries."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".3mf")

    try:
        with zipfile.ZipFile(zip_path, "r") as zin, \
             zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == target_entry:
                    zout.writestr(item, new_data)
                else:
                    zout.writestr(item, zin.read(item.filename))
        # Atomic replace
        shutil.move(tmp_path, zip_path)
    except Exception:
        # Clean up temp file on error
        Path(tmp_path).unlink(missing_ok=True)
        raise
