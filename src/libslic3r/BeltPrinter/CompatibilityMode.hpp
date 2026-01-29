#ifndef slic3r_BeltPrinter_CompatibilityMode_hpp_
#define slic3r_BeltPrinter_CompatibilityMode_hpp_

#include "BeltTransforms.hpp"
#include <Eigen/Dense>
#include <vector>

namespace Slic3r {
namespace BeltPrinter {

/// Compatibility transform configuration
struct CompatibilityTransform {
    Eigen::Matrix4d T_compat;       // 4x4 affine transformation matrix
    bool is_orthonormal;            // Whether transform preserves distances
    bool requires_extrusion_recalc; // Whether extrusion must be recalculated
    std::string output_frame;       // "V" or "F" - which frame T_compat outputs to
    
    CompatibilityTransform()
        : T_compat(Eigen::Matrix4d::Identity())
        , is_orthonormal(true)
        , requires_extrusion_recalc(false)
        , output_frame("V")
    {}
    
    /**
     * Create identity transform (no transformation)
     */
    static CompatibilityTransform create_identity();
    
    /**
     * Create from 4x4 matrix
     * Automatically detects if orthonormal
     */
    static CompatibilityTransform create_from_matrix(
        const Eigen::Matrix4d& T,
        const std::string& output_frame = "V"
    );
    
    /**
     * Validate the transform
     * Checks for common issues and sets flags
     */
    void validate();
};

/// Toolpath segment with pre/post transform coordinates
struct CompatibilitySegment {
    Eigen::Vector3d start_pre;      // Start point before transform
    Eigen::Vector3d end_pre;        // End point before transform
    Eigen::Vector3d start_post;     // Start point after transform
    Eigen::Vector3d end_post;       // End point after transform
    double length_pre;              // Segment length before transform
    double length_post;             // Segment length after transform
    double extrusion_pre;           // Original extrusion amount
    double extrusion_post;          // Recalculated extrusion amount
    
    CompatibilitySegment()
        : start_pre(Eigen::Vector3d::Zero())
        , end_pre(Eigen::Vector3d::Zero())
        , start_post(Eigen::Vector3d::Zero())
        , end_post(Eigen::Vector3d::Zero())
        , length_pre(0.0)
        , length_post(0.0)
        , extrusion_pre(0.0)
        , extrusion_post(0.0)
    {}
};

/// Compatibility mode utilities
class CompatibilityMode {
public:
    /**
     * Apply compatibility transform to a point
     * 
     * @param point Point to transform
     * @param compat Compatibility transform
     * @return Transformed point
     */
    static Eigen::Vector3d apply_transform(
        const Eigen::Vector3d& point,
        const CompatibilityTransform& compat
    );
    
    /**
     * Apply compatibility transform to a segment
     * Computes pre/post lengths and recalculates extrusion if needed
     * 
     * @param start Start point
     * @param end End point
     * @param extrusion Original extrusion amount
     * @param compat Compatibility transform
     * @return Segment with recalculated values
     */
    static CompatibilitySegment apply_to_segment(
        const Eigen::Vector3d& start,
        const Eigen::Vector3d& end,
        double extrusion,
        const CompatibilityTransform& compat
    );
    
    /**
     * Recalculate extrusion based on post-transform segment length
     * Essential for non-orthonormal transforms
     * 
     * Formula: E_post = E_pre * (length_post / length_pre)
     * 
     * @param extrusion_pre Original extrusion
     * @param length_pre Pre-transform segment length
     * @param length_post Post-transform segment length
     * @return Recalculated extrusion
     */
    static double recalculate_extrusion(
        double extrusion_pre,
        double length_pre,
        double length_post
    );
    
    /**
     * Check if a transform is orthonormal
     * (rotation + translation only, no scaling or shear)
     * 
     * @param T 4x4 transformation matrix
     * @param tolerance Numerical tolerance
     * @return true if orthonormal
     */
    static bool is_orthonormal(
        const Eigen::Matrix4d& T,
        double tolerance = 1e-6
    );
    
    /**
     * Compute scale factor of a transform
     * For uniform scaling, returns the scale factor
     * For non-uniform scaling, returns average scale
     * 
     * @param T 4x4 transformation matrix
     * @return Scale factor
     */
    static double compute_scale_factor(
        const Eigen::Matrix4d& T
    );
    
    /**
     * Create a shear transform for legacy belt printer compatibility
     * This is the classic oblique slicing transform
     * 
     * @param angle_deg Gantry angle in degrees
     * @param belt_axis 0=X, 1=Y, 2=Z
     * @return Compatibility transform
     */
    static CompatibilityTransform create_legacy_shear_transform(
        double angle_deg,
        int belt_axis = 1  // Default: Y-axis belt
    );
    
    /**
     * Apply compatibility mode to multiple segments
     * 
     * @param segments Vector of segments to process
     * @param compat Compatibility transform
     */
    static void apply_to_segments(
        std::vector<CompatibilitySegment>& segments,
        const CompatibilityTransform& compat
    );
    
    /**
     * Generate warning message for non-orthonormal transform
     * 
     * @param compat Compatibility transform
     * @return Warning message
     */
    static std::string generate_warning_message(
        const CompatibilityTransform& compat
    );
};

} // namespace BeltPrinter
} // namespace Slic3r

#endif // slic3r_BeltPrinter_CompatibilityMode_hpp_
