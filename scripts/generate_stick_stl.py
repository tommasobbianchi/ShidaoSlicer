import struct

def make_cube_stl(filename):
    # 10x10x100 mm cube
    # Vertices
    w = 10.0
    h = 10.0
    l = 100.0 # Length along Z (Belt Axis)
    
    # 2 triangles per face, 6 faces = 12 triangles
    # Normal is (0,0,0) for simplicity as slicer recalculates or ignores
    
    # Define vertices
    v = [
        [0,0,0], [w,0,0], [w,h,0], [0,h,0], # Front Z=0
        [0,0,l], [w,0,l], [w,h,l], [0,h,l]  # Back Z=l
    ]
    
    # Indices for triangles (CCW)
    indices = [
        # Front (Z=0) - Normal -Z
        [0,2,1], [0,3,2],
        # Back (Z=l) - Normal +Z
        [4,5,6], [4,6,7],
        # Bottom (Y=0) - Normal -Y
        [0,1,5], [0,5,4],
        # Top (Y=h) - Normal +Y
        [3,6,2], [3,7,6],
        # Left (X=0) - Normal -X
        [0,4,7], [0,7,3],
        # Right (X=w) - Normal +X
        [1,2,6], [1,6,5]
    ]

    with open(filename, 'wb') as f:
        # Header 80 bytes
        f.write(b'Orca Belt Validation STL' + b'\0' * 56)
        # Number of triangles
        f.write(struct.pack('<I', len(indices)))
        
        for tri in indices:
            # Normal
            f.write(struct.pack('<fff', 0.0, 0.0, 0.0))
            # Vertices
            for idx in tri:
                f.write(struct.pack('<fff', float(v[idx][0]), float(v[idx][1]), float(v[idx][2])))
            # Attribute byte count
            f.write(struct.pack('<H', 0))

if __name__ == '__main__':
    make_cube_stl("long_stick.stl")
    print("Created long_stick.stl (10x10x100mm)")
