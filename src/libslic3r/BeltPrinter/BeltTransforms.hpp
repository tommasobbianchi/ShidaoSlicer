#ifndef slic3r_BeltPrinter_BeltTransforms_hpp_
#define slic3r_BeltPrinter_BeltTransforms_hpp_

#include "MachineProfile.hpp"
#include "VirtualBeltFrame.hpp"
#include <Eigen/Dense>

namespace Slic3r {
namespace BeltPrinter {

/**
 * Belt Printer Coordinate Transformations
 * 
 * Implements the two distinct transforms defined in the specification:
 * 
 * 1. V→F Mapping (Orthonormal): Maps Virtual Belt Frame to Firmware Frame
 *    - Always orthonormal (preserves distances and angles)
 *    - Defined by M_VF matrix and t_VF offset
 *    - Formula: pF = M_VF * pV + t_VF
 * 
 * 2. Compatibility Transform (Affine): Optional legacy support
 *    - May include rotation, translation, shear, and non-uniform scaling
 *    - Defined by T_compat 4x4 matrix
 *    - WARNING: If non-orthonormal, extrusion must be recomputed!
 */

class BeltTransforms {
public:
    /**
     * Apply V→F mapping (orthonormal)
     * Transforms a point from Virtual Belt Frame to Firmware Frame
     * 
     * @param point_V Point in Virtual Belt Frame
     * @param profile Machine profile containing M_VF and t_VF
     * @return Point in Firmware Frame
     */
    static PointF apply_V_to_F_mapping(
        const PointV& point_V,
        const BeltMachineProfile& profile
    );
    
    /**
     * Apply inverse F→V mapping
     * Transforms a point from Firmware Frame to Virtual Belt Frame
     * 
     * @param point_F Point in Firmware Frame
     * @param profile Machine profile containing M_VF and t_VF
     * @return Point in Virtual Belt Frame
     */
    static PointV apply_F_to_V_mapping(
        const PointF& point_F,
        const BeltMachineProfile& profile
    );
    
    /**
     * Validate M_VF is orthonormal
     * Checks: M_VF * M_VF^T == I and det(M_VF) == ±1
     * 
     * @param M_VF Matrix to validate
     * @param tolerance Numerical tolerance for checks
     * @return true if orthonormal, false otherwise
     */
    static bool validate_M_VF_orthonormal(
        const Eigen::Matrix3d& M_VF,
        double tolerance = 1e-6
    );
    
    /**
     * Apply compatibility transform (affine)
     * WARNING: If T_compat is non-orthonormal, this changes path lengths!
     * 
     * @param point Point to transform (homogeneous coordinates)
     * @param T_compat 4x4 affine transformation matrix
     * @return Transformed point
     */
    static Eigen::Vector3d apply_T_compat(
        const Eigen::Vector3d& point,
        const Eigen::Matrix4d& T_compat
    );
    
    /**
     * Check if a 4x4 transform is orthonormal
     * (rotation + translation only, no scaling or shear)
     * 
     * @param T 4x4 transformation matrix
     * @param tolerance Numerical tolerance
     * @return true if orthonormal, false otherwise
     */
    static bool is_transform_orthonormal(
        const Eigen::Matrix4d& T,
        double tolerance = 1e-6
    );
    
    /**
     * Compute segment length after applying a transform
     * Essential for extrusion calculation in compatibility mode
     * 
     * @param start Start point
     * @param end End point
     * @param T 4x4 transformation matrix
     * @return Length of transformed segment
     */
    static double compute_segment_length_post_transform(
        const Eigen::Vector3d& start,
        const Eigen::Vector3d& end,
        const Eigen::Matrix4d& T
    );
    
    /**
     * Extract rotation matrix from 4x4 affine transform
     * 
     * @param T 4x4 transformation matrix
     * @return 3x3 rotation/scale/shear component
     */
    static Eigen::Matrix3d extract_rotation_component(
        const Eigen::Matrix4d& T
    );
    
    /**
     * Extract translation vector from 4x4 affine transform
     * 
     * @param T 4x4 transformation matrix
     * @return 3D translation vector
     */
    static Eigen::Vector3d extract_translation_component(
        const Eigen::Matrix4d& T
    );
};

} // namespace BeltPrinter
} // namespace Slic3r

#endif // slic3r_BeltPrinter_BeltTransforms_hpp_
