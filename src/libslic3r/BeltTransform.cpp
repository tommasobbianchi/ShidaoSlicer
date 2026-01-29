#include "BeltTransform.hpp"
#include <cmath>

namespace Slic3r {

static const double PI_RAD = 3.14159265358979323846;

static double to_rad(double angle_deg) {
    return angle_deg * PI_RAD / 180.0;
}

Transform3d BeltTransform::make_forward_transform(double angle_degree)
{
    // Forward: Machine to Slicer.
    // Ideally the inverse of the shearing, but often treated as a simple rotation
    // for visualization (model placement).
    // Rotation -angle around X axis.
    double alpha = to_rad(angle_degree);
    Transform3d t = Transform3d::Identity();
    t.linear() = Eigen::AngleAxisd(-alpha, Vec3d::UnitX()).toRotationMatrix();
    return t;
}

Transform3d BeltTransform::make_inverse_transform(double angle_degree)
{
    // Inverse: Slicer (Virtual) to Machine (G-code).
    // This maps the vertical slices onto the angled belt.
    // 
    // x_mach = x_virt
    // y_mach (belt) = z_virt / sin(alpha)
    // z_mach (head) = y_virt - z_virt / tan(alpha)

    double alpha = to_rad(angle_degree);
    double sin_a = std::sin(alpha);
    double tan_a = std::tan(alpha);

    // Avoid division by zero
    if (std::abs(sin_a) < 1e-6) sin_a = 1e-6;
    if (std::abs(tan_a) < 1e-6) tan_a = 1e-6;

    Transform3d t = Transform3d::Identity();
    
    // Matrix structure (Column-major in Eigen, but we set coeffs):
    // R0: 1, 0, 0
    // R1: 0, 0, 1/sin
    // R2: 0, 1, -1/tan
    
    // Eigen transforms are (Linear) + (Translation). 
    // We construct the linear matrix manually.
    
    Matrix3d m;
    m << 1.0, 0.0, 0.0,
         0.0, 0.0, 1.0 / sin_a,
         0.0, 1.0, -1.0 / tan_a;

    t.linear() = m;
    return t;
}

Vec3d BeltTransform::inverse_transform_point(const Vec3d& pt, double angle_degree)
{
    double alpha = to_rad(angle_degree);
    double sin_a = std::sin(alpha);
    double tan_a = std::tan(alpha);
    
    // Protection against singularity (0 degrees)
    if (std::abs(sin_a) < 1e-6) sin_a = 1e-6;
    if (std::abs(tan_a) < 1e-6) tan_a = 1e-6;

    double y_mach = pt.z() / sin_a;
    double z_mach = pt.y() - (pt.z() / tan_a);
    
    return Vec3d(pt.x(), y_mach, z_mach);
}

} // namespace Slic3r
