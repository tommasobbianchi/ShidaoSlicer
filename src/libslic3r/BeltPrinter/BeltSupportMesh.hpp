#ifndef slic3r_BeltSupportMesh_hpp_
#define slic3r_BeltSupportMesh_hpp_

#include "../TriangleMesh.hpp"
#include <Eigen/Geometry>

namespace Slic3r { namespace BeltPrinter {

// Create a 3D support mesh for belt printer overhangs.
//
// Algorithm (BlackBelt/BirthT approach):
// 1. Transform model vertices to virtual space via trafo_centered()
// 2. Use a belt-biased gravity vector to detect overhang faces
// 3. For each overhang face, create a triangular prism from the face
//    down to Y_virt=0 (belt surface)
// 4. Return the combined mesh in virtual space
//
// The mesh is meant to be sliced at the same Z levels as the model.
// Each cross-section gives the support polygon at that layer.
//
// Parameters:
//   model_its      - the raw model mesh (in model space)
//   trafo          - trafo_centered() transform (model → virtual space)
//   belt_angle_deg - belt inclination angle (typically 45°)
//   support_angle  - minimum overhang angle requiring support (default 50°)
//   bottom_offset  - small Y offset above Y=0 to avoid z-fighting (default 0.1mm)
//
indexed_triangle_set create_belt_support_mesh(
    const indexed_triangle_set &model_its,
    const Transform3d          &trafo,
    double                      belt_angle_deg  = 45.0,
    double                      support_angle   = 50.0,
    float                       bottom_offset   = 0.1f);

}} // namespace Slic3r::BeltPrinter

#endif // slic3r_BeltSupportMesh_hpp_
