#include "CompatibilityMode.hpp"
#include <cmath>
#include <sstream>

namespace Slic3r {
namespace BeltPrinter {

// === CompatibilityTransform Implementation ===

CompatibilityTransform CompatibilityTransform::create_identity()
{
    CompatibilityTransform compat;
    compat.T_compat = Eigen::Matrix4d::Identity();
    compat.is_orthonormal = true;
    compat.requires_extrusion_recalc = false;
    compat.output_frame = "V";
    return compat;
}

CompatibilityTransform CompatibilityTransform::create_from_matrix(
    const Eigen::Matrix4d& T,
    const std::string& output_frame)
{
    CompatibilityTransform compat;
    compat.T_compat = T;
    compat.output_frame = output_frame;
    compat.validate();
    return compat;
}

void CompatibilityTransform::validate()
{
    is_orthonormal = CompatibilityMode::is_orthonormal(T_compat);
    requires_extrusion_recalc = !is_orthonormal;
}

// === CompatibilityMode Implementation ===

Eigen::Vector3d CompatibilityMode::apply_transform(
    const Eigen::Vector3d& point,
    const CompatibilityTransform& compat)
{
    return BeltTransforms::apply_T_compat(point, compat.T_compat);
}

CompatibilitySegment CompatibilityMode::apply_to_segment(
    const Eigen::Vector3d& start,
    const Eigen::Vector3d& end,
    double extrusion,
    const CompatibilityTransform& compat)
{
    CompatibilitySegment segment;
    
    // Store pre-transform values
    segment.start_pre = start;
    segment.end_pre = end;
    segment.extrusion_pre = extrusion;
    segment.length_pre = (end - start).norm();
    
    // Apply transform
    segment.start_post = apply_transform(start, compat);
    segment.end_post = apply_transform(end, compat);
    segment.length_post = (segment.end_post - segment.start_post).norm();
    
    // Recalculate extrusion if needed
    if (compat.requires_extrusion_recalc) {
        segment.extrusion_post = recalculate_extrusion(
            extrusion, segment.length_pre, segment.length_post);
    } else {
        segment.extrusion_post = extrusion;
    }
    
    return segment;
}

double CompatibilityMode::recalculate_extrusion(
    double extrusion_pre,
    double length_pre,
    double length_post)
{
    if (length_pre < 1e-6) {
        return extrusion_pre;
    }
    
    // E_post = E_pre * (length_post / length_pre)
    return extrusion_pre * (length_post / length_pre);
}

bool CompatibilityMode::is_orthonormal(
    const Eigen::Matrix4d& T,
    double tolerance)
{
    return BeltTransforms::is_transform_orthonormal(T, tolerance);
}

double CompatibilityMode::compute_scale_factor(
    const Eigen::Matrix4d& T)
{
    // Extract 3x3 rotation/scale component
    Eigen::Matrix3d R = BeltTransforms::extract_rotation_component(T);
    
    // Compute singular values (scale factors along each axis)
    Eigen::JacobiSVD<Eigen::Matrix3d> svd(R);
    Eigen::Vector3d singular_values = svd.singularValues();
    
    // Return average scale factor
    return singular_values.mean();
}

CompatibilityTransform CompatibilityMode::create_legacy_shear_transform(
    double angle_deg,
    int belt_axis)
{
    double angle_rad = angle_deg * M_PI / 180.0;
    double tan_angle = std::tan(angle_rad);
    
    Eigen::Matrix4d T = Eigen::Matrix4d::Identity();
    
    // Create shear transform based on belt axis
    // For Y-axis belt (most common):
    //   Ym = Ys - Zs * tan(α)
    //   This is a shear in the Y-Z plane
    
    if (belt_axis == 1) {  // Y-axis belt
        // Shear matrix: Y_machine = Y_slice - Z_slice * tan(α)
        T(1, 2) = -tan_angle;  // Y row, Z column
    } else if (belt_axis == 0) {  // X-axis belt
        // Shear matrix: X_machine = X_slice - Z_slice * tan(α)
        T(0, 2) = -tan_angle;  // X row, Z column
    } else {  // Z-axis belt (unusual)
        // No shear needed for Z-axis belt in standard configuration
    }
    
    CompatibilityTransform compat;
    compat.T_compat = T;
    compat.output_frame = "F";  // Outputs to firmware frame
    compat.validate();
    
    return compat;
}

void CompatibilityMode::apply_to_segments(
    std::vector<CompatibilitySegment>& segments,
    const CompatibilityTransform& compat)
{
    for (auto& segment : segments) {
        CompatibilitySegment result = apply_to_segment(
            segment.start_pre,
            segment.end_pre,
            segment.extrusion_pre,
            compat
        );
        segment = result;
    }
}

std::string CompatibilityMode::generate_warning_message(
    const CompatibilityTransform& compat)
{
    std::ostringstream msg;
    
    if (!compat.is_orthonormal) {
        double scale = compute_scale_factor(compat.T_compat);
        
        msg << "WARNING: Non-orthonormal compatibility transform detected!\n";
        msg << "  Transform includes scaling/shear (scale factor: " << scale << ")\n";
        msg << "  Extrusion amounts MUST be recalculated from post-transform segment lengths.\n";
        msg << "  Using pre-transform extrusion will result in under/over-extrusion.\n";
        
        if (!compat.requires_extrusion_recalc) {
            msg << "  ERROR: Extrusion recalculation is DISABLED but REQUIRED!\n";
        } else {
            msg << "  Extrusion recalculation is ENABLED (correct).\n";
        }
    }
    
    return msg.str();
}

} // namespace BeltPrinter
} // namespace Slic3r
