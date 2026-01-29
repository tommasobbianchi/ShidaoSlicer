import struct

def write_stl(filename, facets):
    with open(filename, 'wb') as f:
        f.write(b'\0' * 80)
        f.write(struct.pack('<I', len(facets)))
        for facet in facets:
            f.write(struct.pack('<fff', 0, 0, 0)) # Normal
            for vertex in facet:
                f.write(struct.pack('<fff', *vertex))
            f.write(struct.pack('<H', 0))

def create_box(x, y, z):
    v = [
        (0, 0, 0), (x, 0, 0), (x, y, 0), (0, y, 0),
        (0, 0, z), (x, 0, z), (x, y, z), (0, y, z)
    ]
    # 12 triangles
    triangles = [
        [v[0], v[1], v[2]], [v[0], v[2], v[3]], # bottom
        [v[4], v[6], v[5]], [v[4], v[7], v[6]], # top
        [v[0], v[4], v[5]], [v[0], v[5], v[1]], # front
        [v[1], v[5], v[6]], [v[1], v[6], v[2]], # right
        [v[2], v[6], v[7]], [v[2], v[7], v[3]], # back
        [v[3], v[7], v[4]], [v[3], v[4], v[0]]  # left
    ]
    return triangles

if __name__ == "__main__":
    # Create a bar 20 mm x, 100 mm y, 20 mm z
    facets = create_box(20, 100, 20)
    write_stl("bar_20x100x20.stl", facets)
    print("Generated bar_20x100x20.stl")
