#include "BeltTransforms.hpp"
#include <cmath>

namespace Slic3r {
namespace BeltPrinter {

PointF BeltTransforms::apply_V_to_F_mapping(
    const PointV& point_V,
    const BeltMachineProfile& profile)
{
    // pF = M_VF * pV + t_VF
    return profile.M_VF * point_V + profile.t_VF;
}

PointV BeltTransforms::apply_F_to_V_mapping(
    const PointF& point_F,
    const BeltMachineProfile& profile)
{
    // pV = M_VF^-1 * (pF - t_VF)
    // Since M_VF is orthonormal, M_VF^-1 = M_VF^T
    return profile.M_VF.transpose() * (point_F - profile.t_VF);
}

bool BeltTransforms::validate_M_VF_orthonormal(
    const Eigen::Matrix3d& M_VF,
    double tolerance)
{
    // Check 1: M_VF * M_VF^T == I
    Eigen::Matrix3d product = M_VF * M_VF.transpose();
    Eigen::Matrix3d identity = Eigen::Matrix3d::Identity();
    double orthonormal_error = (product - identity).norm();
    
    if (orthonormal_error > tolerance) {
        return false;
    }
    
    // Check 2: det(M_VF) == ±1
    double det = M_VF.determinant();
    if (std::abs(std::abs(det) - 1.0) > tolerance) {
        return false;
    }
    
    // Check 3: Each row and column has exactly one non-zero entry (±1)
    for (int i = 0; i < 3; ++i) {
        int row_nonzero = 0;
        int col_nonzero = 0;
        
        for (int j = 0; j < 3; ++j) {
            if (std::abs(M_VF(i, j)) > tolerance) {
                row_nonzero++;
                // Check that non-zero entry is ±1
                if (std::abs(std::abs(M_VF(i, j)) - 1.0) > tolerance) {
                    return false;
                }
            }
            if (std::abs(M_VF(j, i)) > tolerance) {
                col_nonzero++;
            }
        }
        
        if (row_nonzero != 1 || col_nonzero != 1) {
            return false;
        }
    }
    
    return true;
}

Eigen::Vector3d BeltTransforms::apply_T_compat(
    const Eigen::Vector3d& point,
    const Eigen::Matrix4d& T_compat)
{
    // Convert to homogeneous coordinates
    Eigen::Vector4d point_homog(point.x(), point.y(), point.z(), 1.0);
    
    // Apply transform
    Eigen::Vector4d result_homog = T_compat * point_homog;
    
    // Convert back to 3D (divide by w if needed, though it should be 1)
    return Eigen::Vector3d(
        result_homog.x() / result_homog.w(),
        result_homog.y() / result_homog.w(),
        result_homog.z() / result_homog.w()
    );
}

bool BeltTransforms::is_transform_orthonormal(
    const Eigen::Matrix4d& T,
    double tolerance)
{
    // Extract 3x3 rotation component
    Eigen::Matrix3d R = extract_rotation_component(T);
    
    // Check if R is orthonormal
    Eigen::Matrix3d product = R * R.transpose();
    Eigen::Matrix3d identity = Eigen::Matrix3d::Identity();
    double error = (product - identity).norm();
    
    if (error > tolerance) {
        return false;
    }
    
    // Check determinant is ±1
    double det = R.determinant();
    if (std::abs(std::abs(det) - 1.0) > tolerance) {
        return false;
    }
    
    return true;
}

double BeltTransforms::compute_segment_length_post_transform(
    const Eigen::Vector3d& start,
    const Eigen::Vector3d& end,
    const Eigen::Matrix4d& T)
{
    Eigen::Vector3d start_transformed = apply_T_compat(start, T);
    Eigen::Vector3d end_transformed = apply_T_compat(end, T);
    
    return (end_transformed - start_transformed).norm();
}

Eigen::Matrix3d BeltTransforms::extract_rotation_component(
    const Eigen::Matrix4d& T)
{
    return T.block<3, 3>(0, 0);
}

Eigen::Vector3d BeltTransforms::extract_translation_component(
    const Eigen::Matrix4d& T)
{
    return T.block<3, 1>(0, 3);
}

} // namespace BeltPrinter
} // namespace Slic3r
