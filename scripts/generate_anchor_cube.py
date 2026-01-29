import struct

def write_cube_stl(filename, size=10, x_offset=5, y_offset=0):
    # STL binary format: Header (80 bytes), Number of triangles (4 bytes), then facets
    header = b'\0' * 80
    
    # 6 faces, 2 triangles each = 12 facets
    facets = []
    
    # Coordinates
    x0, x1 = x_offset, x_offset + size
    y0, y1 = y_offset, y_offset + size
    z0, z1 = 0, size
    
    # helper to add facet
    def add_facet(n, v1, v2, v3):
        facet = struct.pack('<3f', *n) # Normal
        facet += struct.pack('<3f', *v1)
        facet += struct.pack('<3f', *v2)
        facet += struct.pack('<3f', *v3)
        facet += b'\0\0' # Attribute byte count
        facets.append(facet)

    # Bottom
    add_facet((0,0,-1), (x0,y0,z0), (x1,y0,z0), (x0,y1,z0))
    add_facet((0,0,-1), (x0,y1,z0), (x1,y0,z0), (x1,y1,z0))
    # Top
    add_facet((0,0,1), (x0,y0,z1), (x0,y1,z1), (x1,y0,z1))
    add_facet((0,0,1), (x0,y1,z1), (x1,y1,z1), (x1,y0,z1))
    # Front (Y=0)
    add_facet((0,-1,0), (x0,y0,z0), (x0,y0,z1), (x1,y0,z1))
    add_facet((0,-1,0), (x0,y0,z0), (x1,y0,z1), (x1,y0,z0))
    # Back
    add_facet((0,1,0), (x0,y1,z0), (x1,y1,z1), (x0,y1,z1))
    add_facet((0,1,0), (x0,y1,z0), (x1,y1,z0), (x1,y1,z1))
    # Left
    add_facet((-1,0,0), (x0,y0,z0), (x0,y1,z1), (x0,y0,z1))
    add_facet((-1,0,0), (x0,y0,z0), (x0,y1,z0), (x0,y1,z1))
    # Right
    add_facet((1,0,0), (x1,y0,z0), (x1,y0,z1), (x1,y1,z1))
    add_facet((1,0,0), (x1,y0,z0), (x1,y1,z1), (x1,y1,z0))

    with open(filename, 'wb') as f:
        f.write(header)
        f.write(struct.pack('<I', len(facets)))
        for facet in facets:
            f.write(facet)

if __name__ == "__main__":
    write_cube_stl("tests/fixtures/anchor_cube.stl")
    print("Generated tests/fixtures/anchor_cube.stl at Y=0")
