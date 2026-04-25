#include "BeltSupportMesh.hpp"
#include <cmath>
#include <vector>
#include <boost/log/trivial.hpp>

namespace Slic3r { namespace BeltPrinter {

indexed_triangle_set create_belt_support_mesh(
    const indexed_triangle_set &model_its,
    const Transform3d          &trafo,
    double                      belt_angle_deg,
    double                      support_angle,
    float                       bottom_offset)
{
    // --- Step 1: Transform all model vertices to virtual space ---
    std::vector<Vec3f> verts(model_its.vertices.size());
    for (size_t i = 0; i < model_its.vertices.size(); ++i) {
        Vec3d v = trafo * model_its.vertices[i].cast<double>();
        verts[i] = v.cast<float>();
    }

    // --- Step 2: Compute biased gravity vector ---
    // For a 45° belt, gravity in virtual space is not [0,0,-1] but
    // biased toward -Y (the belt direction):
    //   gravity = [0, -cos(belt_angle), -sin(belt_angle)]
    // At 45°: [0, -0.707, -0.707]
    double angle_rad = belt_angle_deg * M_PI / 180.0;
    Vec3f gravity(0.f, float(-std::cos(angle_rad)), float(-std::sin(angle_rad)));

    // Support threshold: faces whose normal · gravity >= cos(90° - support_angle)
    float cos_threshold = std::cos(float((90.0 - support_angle) * M_PI / 180.0));

    // --- Step 3: Find overhang faces ---
    size_t num_overhang = 0;
    std::vector<bool> is_overhang(model_its.indices.size(), false);
    for (size_t fi = 0; fi < model_its.indices.size(); ++fi) {
        const auto &face = model_its.indices[fi];
        const Vec3f &v0 = verts[face[0]];
        const Vec3f &v1 = verts[face[1]];
        const Vec3f &v2 = verts[face[2]];

        Vec3f edge1 = v1 - v0;
        Vec3f edge2 = v2 - v0;
        Vec3f normal = edge1.cross(edge2);
        float len = normal.norm();
        if (len < 1e-12f)
            continue;
        normal /= len;

        // Dot product with biased gravity: positive means face points "downward"
        if (normal.dot(gravity) >= cos_threshold) {
            // Also filter: skip faces that are coplanar with the belt (Y ≈ 0)
            float min_y = std::min({v0.y(), v1.y(), v2.y()});
            if (min_y > bottom_offset) {
                is_overhang[fi] = true;
                ++num_overhang;
            }
        }
    }

    BOOST_LOG_TRIVIAL(info) << "BeltSupportMesh: " << num_overhang
        << " overhang faces out of " << model_its.indices.size()
        << " (belt_angle=" << belt_angle_deg
        << ", support_angle=" << support_angle << ")";

    if (num_overhang == 0)
        return {};

    // --- Step 4: Build support mesh ---
    // For each overhang face, create a triangular PRISM from the face
    // straight down to the belt surface (Y_virt = bottom_offset).
    //
    // Projection direction: [0, -1, 0] in virtual space.
    // Floor vertex = (x, bottom_offset, z_same_as_roof).
    // This keeps support at the SAME Z_virt as the overhang, so it
    // only appears at layers where the arm exists — no side wedge.
    // The belt provides a fresh surface at every layer, so support
    // doesn't need to build up from earlier layers.
    //
    // Roof: the overhang triangle (at its original position)
    // Floor: same X/Z, Y dropped to belt surface
    // Sides: 3 quads (6 triangles) connecting roof to floor

    indexed_triangle_set support_its;
    support_its.vertices.reserve(num_overhang * 6);
    support_its.indices.reserve(num_overhang * 8);

    for (size_t fi = 0; fi < model_its.indices.size(); ++fi) {
        if (!is_overhang[fi])
            continue;

        const auto &face = model_its.indices[fi];
        const Vec3f &r0 = verts[face[0]];  // roof vertices
        const Vec3f &r1 = verts[face[1]];
        const Vec3f &r2 = verts[face[2]];

        // Floor vertices: project straight down [0,-1,0] to Y = bottom_offset.
        // Z_virt stays the same — support only exists at the arm's Z_virt range.
        Vec3f f0(r0.x(), bottom_offset, r0.z());
        Vec3f f1(r1.x(), bottom_offset, r1.z());
        Vec3f f2(r2.x(), bottom_offset, r2.z());

        int base = (int)support_its.vertices.size();
        support_its.vertices.push_back(r0);  // base+0
        support_its.vertices.push_back(r1);  // base+1
        support_its.vertices.push_back(r2);  // base+2
        support_its.vertices.push_back(f0);  // base+3
        support_its.vertices.push_back(f1);  // base+4
        support_its.vertices.push_back(f2);  // base+5

        // Roof face (same winding as original)
        support_its.indices.push_back(Vec3i32(base+0, base+1, base+2));
        // Floor face (reversed winding for outward normal)
        support_its.indices.push_back(Vec3i32(base+3, base+5, base+4));

        // Side walls (3 quads = 6 triangles)
        // Edge 0→1
        support_its.indices.push_back(Vec3i32(base+0, base+1, base+4));
        support_its.indices.push_back(Vec3i32(base+0, base+4, base+3));
        // Edge 1→2
        support_its.indices.push_back(Vec3i32(base+1, base+2, base+5));
        support_its.indices.push_back(Vec3i32(base+1, base+5, base+4));
        // Edge 2→0
        support_its.indices.push_back(Vec3i32(base+2, base+0, base+3));
        support_its.indices.push_back(Vec3i32(base+2, base+3, base+5));
    }

    BOOST_LOG_TRIVIAL(info) << "BeltSupportMesh: created mesh with "
        << support_its.vertices.size() << " vertices, "
        << support_its.indices.size() << " faces";

    return support_its;
}

}} // namespace Slic3r::BeltPrinter
