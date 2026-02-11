import numpy as np
from stl import mesh
import sys

def rotate_stl(input_file, output_file, angle_deg=45):
    my_mesh = mesh.Mesh.from_file(input_file)
    
    # Rotate 45 degrees around X axis
    # This stands the cube on its edge/corner
    angle_rad = np.radians(angle_deg)
    
    # Rotation matrix around X
    # [1, 0, 0]
    # [0, cos, -sin]
    # [0, sin, cos]
    
    my_mesh.rotate([1.0, 0.0, 0.0], angle_rad)
    
    # Translate to positive octant (z>=0)
    # Get bounds
    minx, maxx, miny, maxy, minz, maxz = my_mesh.x.min(), my_mesh.x.max(), \
                                         my_mesh.y.min(), my_mesh.y.max(), \
                                         my_mesh.z.min(), my_mesh.z.max()
                                         
    # Move to Z=0
    my_mesh.z -= minz
    # Move to Y=0 (or center?)
    # For belt, usually we want it centered on X, sitting on Y=0?
    # User said "Y=0, Z=0".
    # Let's align Y min to 0.
    my_mesh.y -= miny
    
    my_mesh.save(output_file)
    print(f"Saved rotated STL to {output_file}")
    
    # Print bounds
    print(f"Bounds: X[{minx:.2f}, {maxx:.2f}], Y[{my_mesh.y.min():.2f}, {my_mesh.y.max():.2f}], Z[{my_mesh.z.min():.2f}, {my_mesh.z.max():.2f}]")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python rotate_stl.py <input> <output>")
        sys.exit(1)
    rotate_stl(sys.argv[1], sys.argv[2])
