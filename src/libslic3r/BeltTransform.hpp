#ifndef slic3r_BeltTransform_hpp_
#define slic3r_BeltTransform_hpp_

#include "libslic3r.h"
#include "Point.hpp"

namespace Slic3r {

class BeltTransform {
public:
    // Create the Forward transformation matrix (Machine to Virtual Slicer Space).
    // This rotates the coordinate system so the belt plane becomes the XY plane.
    // angle_degree: Usually 45.0 degrees.
    static Transform3d make_forward_transform(double angle_degree);

    // Create the Inverse transformation matrix (Virtual Slicer Space to Machine).
    // NOTE: This is NOT just a rigid rotation inverse. It is a shear transformation
    // required to map the sliced layers onto the moving belt.
    //
    // Formulas:
    // Y_machine = z_virtual / sin(alpha)  [Belt Movement]
    // Z_machine = y_virtual - z_virtual / tan(alpha) [Head Movement]
    // X_machine = x_virtual
    //
    // However, if we follow the generic shear matrix approach:
    static Transform3d make_inverse_transform(double angle_degree);

    // Apply inverse transform to a single point explicitly (High precision)
    static Vec3d inverse_transform_point(const Vec3d& virtual_pt, double angle_degree);
};

} // namespace Slic3r

#endif // slic3r_BeltTransform_hpp_
