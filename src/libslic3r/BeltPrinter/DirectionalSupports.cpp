#include "DirectionalSupports.hpp"
#include <cmath>

namespace Slic3r {
namespace BeltPrinter {

FacetClassification DirectionalSupports::classify_overhang_direction(
    const VectorV& facet_normal,
    const DirectionalSupportSettings& settings)
{
    FacetClassification result;
    
    if (!settings.enable_directional_logic) {
        result.dependency = SupportDependency::NEUTRAL;
        result.needs_support = false;
        return result;
    }
    
    // Step 1: Compute overhang angle
    result.overhang_angle_deg = compute_overhang_angle(facet_normal);
    
    // Step 2: Check if it's an overhang
    if (result.overhang_angle_deg < settings.overhang_threshold_deg) {
        result.dependency = SupportDependency::NEUTRAL;
        result.needs_support = false;
        return result;
    }
    
    // Step 3: Compute steepest descent direction
    VectorV steepest_descent = compute_steepest_descent(facet_normal);
    
    // Step 4: Project into belt plane
    VectorV descent_in_belt_plane = project_to_belt_plane(steepest_descent);
    
    // Step 5: Get belt direction component
    result.belt_direction_component = get_belt_direction_component(
        descent_in_belt_plane,
        settings.belt_positive_direction
    );
    
    // Step 6: Classify based on direction
    if (result.belt_direction_component > 0.01) {
        // Dependency points forward along belt
        result.dependency = SupportDependency::FORWARD;
        result.needs_support = true;
    } else if (result.belt_direction_component < -0.01) {
        // Dependency points backward - naturally supported
        result.dependency = SupportDependency::BACKWARD;
        result.needs_support = false;
    } else {
        // Perpendicular to belt or negligible component
        result.dependency = SupportDependency::NEUTRAL;
        result.needs_support = true;  // Use conventional logic
    }
    
    return result;
}

bool DirectionalSupports::needs_support(
    const VectorV& facet_normal,
    const DirectionalSupportSettings& settings)
{
    FacetClassification classification = classify_overhang_direction(
        facet_normal, settings);
    return classification.needs_support;
}

double DirectionalSupports::compute_overhang_angle(
    const VectorV& facet_normal)
{
    // Overhang angle is the angle from vertical (+Zv)
    // α = arccos(dot(normal, +Zv))
    
    VectorV up = VirtualBeltFrame::UnitZv;
    double dot_product = facet_normal.dot(up);
    
    // Clamp to [-1, 1] for numerical stability
    dot_product = std::max(-1.0, std::min(1.0, dot_product));
    
    double angle_rad = std::acos(dot_product);
    double angle_deg = angle_rad * 180.0 / M_PI;
    
    return angle_deg;
}

VectorV DirectionalSupports::compute_steepest_descent(
    const VectorV& facet_normal)
{
    // Steepest descent is the direction material would fall if not supported
    // It's the projection of the downward direction (-Zv) onto the surface plane
    // For a surface with normal n, the steepest descent is:
    // d = -ẑ - ((-ẑ)·n)n = -ẑ + (ẑ·n)n
    
    VectorV down = -VirtualBeltFrame::UnitZv;  // Gravity direction
    VectorV n = facet_normal.normalized();
    
    // Project gravity onto the surface plane
    double dot_product = down.dot(n);
    VectorV descent = down - dot_product * n;
    
    // Normalize
    double length = descent.norm();
    if (length > 1e-6) {
        descent /= length;
    } else {
        // Surface is horizontal, no preferred descent direction
        descent = VectorV::Zero();
    }
    
    return descent;
}

VectorV DirectionalSupports::project_to_belt_plane(
    const VectorV& vec)
{
    // Project onto XY plane (set Zv = 0)
    return VectorV(vec.x(), vec.y(), 0.0);
}

double DirectionalSupports::get_belt_direction_component(
    const VectorV& vec,
    int belt_positive_direction)
{
    // Belt direction is along +Yv or -Yv
    double yv_component = vec.y();
    return yv_component * belt_positive_direction;
}

DirectionalSupportSettings DirectionalSupports::create_settings_from_profile(
    const BeltMachineProfile& profile,
    double overhang_threshold_deg)
{
    DirectionalSupportSettings settings;
    settings.overhang_threshold_deg = overhang_threshold_deg;
    settings.belt_positive_direction = profile.belt_positive_direction_in_V;
    settings.enable_directional_logic = true;
    return settings;
}

} // namespace BeltPrinter
} // namespace Slic3r
