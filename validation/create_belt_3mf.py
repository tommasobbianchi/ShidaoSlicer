#!/usr/bin/env python3
"""Create a proper 3MF for belt printer CLI slicing with support enabled.
Replaces model in existing test_cube_clean.3mf structure with inverted-L.
"""
import zipfile, os, sys, shutil, tempfile

def create_3mf(stl_path, output_3mf, enable_support=True):
    """Create a 3MF with belt settings and the given STL model."""

    stl_name = os.path.basename(stl_path)

    # Read the STL binary
    with open(stl_path, 'rb') as f:
        stl_data = f.read()

    # 3D model XML (main assembly)
    model_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US"
       xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
       xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
       requiredextensions="p">
 <metadata name="Application">OrcaSlicer-2.3.2-dev</metadata>
 <resources>
  <object id="1" p:UUID="00000001-0000-0000-0000-000000000001" type="model">
   <components>
    <component p:path="/3D/Objects/{stl_name}_1.model" objectid="1"
               p:UUID="00010000-0000-0000-0000-000000000001"
               transform="1 0 0 0 1 0 0 0 1 0 0 0"/>
   </components>
  </object>
 </resources>
 <build p:UUID="00000002-0000-0000-0000-000000000001">
  <item objectid="1" p:UUID="00000003-0000-0000-0000-000000000001"
        transform="1 0 0 0 1 0 0 0 1 125 5 0" printable="1"/>
 </build>
</model>'''

    # Object model XML (references the STL)
    object_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US"
       xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
       xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">
 <resources>
  <object id="1" type="model">
   <mesh>
    <vertices/>
    <triangles/>
   </mesh>
  </object>
 </resources>
</model>'''

    # Project settings (belt printer + supports)
    support_val = "1" if enable_support else "0"
    project_settings = f'''{{
    "printer_structure": "belt",
    "printer_is_belt": "1",
    "belt_angle": "45",
    "belt_axis": "y",
    "belt_inclined_gcode": "1",
    "belt_wall_enabled": "0",
    "best_object_pos": "0.5x0",
    "gcode_flavor": "klipper",
    "use_relative_e_distances": "1",
    "nozzle_diameter": ["0.4"],
    "printable_area": ["0x0", "250x0", "250x2000", "0x2000"],
    "printable_height": "250",
    "retraction_length": ["2"],
    "retraction_speed": ["40"],
    "z_hop": ["0.4"],
    "retract_lift_below": ["300"],
    "layer_height": "0.2",
    "initial_layer_print_height": "0.2",
    "wall_loops": "2",
    "top_shell_layers": "3",
    "bottom_shell_layers": "3",
    "sparse_infill_density": "15%",
    "enable_support": "{support_val}",
    "support_type": "normal(auto)",
    "support_threshold_angle": "30",
    "support_base_pattern": "rectilinear",
    "support_base_pattern_spacing": "2.5",
    "support_on_build_plate_only": "0",
    "machine_start_gcode": "G28\\n",
    "machine_end_gcode": "M84\\n"
}}'''

    # Slice info config
    slice_info = f'''<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="prediction" value="0"/>
    <metadata key="outside" value="false"/>
    <metadata key="support_used" value="{'true' if enable_support else 'false'}"/>
    <object identify_id="1" name="{stl_name}" skipped="false" />
  </plate>
</config>'''

    # Model settings config
    model_settings = '''<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="1">
    <metadata key="name" value="object"/>
    <part id="1" subtype="normal_part">
      <metadata key="name" value="part1"/>
      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>
      <metadata key="source_file" value=""/>
    </part>
  </object>
</config>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>'''

    rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>'''

    model_rels = f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/Objects/{stl_name}_1.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>'''

    # Write ZIP
    with zipfile.ZipFile(output_3mf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', rels)
        zf.writestr('3D/3dmodel.model', model_xml)
        zf.writestr('3D/_rels/3dmodel.model.rels', model_rels)
        zf.writestr(f'3D/Objects/{stl_name}_1.model', object_xml)
        zf.writestr('Metadata/project_settings.config', project_settings)
        zf.writestr('Metadata/slice_info.config', slice_info)
        zf.writestr('Metadata/model_settings.config', model_settings)
        # Include the actual STL as binary data
        zf.write(stl_path, f'3D/Objects/{stl_name}')

    print(f"Created {output_3mf} with support={'enabled' if enable_support else 'disabled'}")


if __name__ == '__main__':
    stl = sys.argv[1] if len(sys.argv) > 1 else '/home/user/projects/ORCA_BELT/validation/test_models/inverted_L.stl'
    out = sys.argv[2] if len(sys.argv) > 2 else '/tmp/belt_support_test/inverted_L_belt.3mf'
    support = '--no-support' not in sys.argv
    create_3mf(stl, out, enable_support=support)
