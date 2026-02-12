#include "DirectionalSupports.hpp"
#include "../Print.hpp"
#include "../Layer.hpp"
#include "../Model.hpp"
#include "../ClipperUtils.hpp"
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

std::vector<Polygons> DirectionalSupports::compute_belt_overhang_blockers(
    const PrintObject& object,
    const DirectionalSupportSettings& settings)
{
    const auto* profile = object.belt_profile();
    if (!profile || !settings.enable_directional_logic)
        return {};

    // Get layer count and z-heights
    auto layers = object.layers();
    const size_t num_layers = layers.size();
    if (num_layers == 0)
        return {};

    std::vector<Polygons> blockers(num_layers);

    // F→V transform for this object
    Eigen::Affine3d F_to_V = profile->get_F_to_V_transform();

    const ModelObject* model_obj = object.model_object();
    if (!model_obj)
        return blockers;

    for (const ModelVolume* mv : model_obj->volumes) {
        if (!mv->is_model_part())
            continue;

        // Combined transform: F→V * object_trafo * volume_matrix
        Eigen::Affine3d combined = F_to_V * object.trafo() * mv->get_matrix();
        const indexed_triangle_set& its = mv->mesh().its;

        for (size_t fi = 0; fi < its.indices.size(); ++fi) {
            const auto& face = its.indices[fi];

            // Transform vertices to V-frame
            Eigen::Vector3d v0 = combined * its.vertices[face[0]].cast<double>();
            Eigen::Vector3d v1 = combined * its.vertices[face[1]].cast<double>();
            Eigen::Vector3d v2 = combined * its.vertices[face[2]].cast<double>();

            // Compute facet normal in V-frame
            Eigen::Vector3d normal = (v1 - v0).cross(v2 - v0);
            double len = normal.norm();
            if (len < 1e-12)
                continue;
            normal /= len;

            // Classify: only interested in BACKWARD facets
            VectorV normal_V(normal.x(), normal.y(), normal.z());
            FacetClassification cls = classify_overhang_direction(normal_V, settings);
            if (cls.dependency != SupportDependency::BACKWARD)
                continue;

            // Project triangle XY outline as blocker polygon
            double z_min = std::min({v0.z(), v1.z(), v2.z()});
            double z_max = std::max({v0.z(), v1.z(), v2.z()});

            // Build a scaled polygon from the 3 XY-projected vertices
            Polygon tri_poly;
            tri_poly.points.reserve(3);
            tri_poly.points.emplace_back(coord_t(scale_(v0.x())), coord_t(scale_(v0.y())));
            tri_poly.points.emplace_back(coord_t(scale_(v1.x())), coord_t(scale_(v1.y())));
            tri_poly.points.emplace_back(coord_t(scale_(v2.x())), coord_t(scale_(v2.y())));

            // Add this triangle's projection to every layer it spans
            for (size_t li = 0; li < num_layers; ++li) {
                double layer_z = layers[li]->slice_z;
                if (layer_z >= z_min - EPSILON && layer_z <= z_max + EPSILON)
                    blockers[li].emplace_back(tri_poly);
            }
        }
    }

    // Union blocker polygons per layer for cleaner geometry
    for (size_t li = 0; li < num_layers; ++li) {
        if (!blockers[li].empty())
            blockers[li] = union_(blockers[li]);
    }

    return blockers;
}

} // namespace BeltPrinter
} // namespace Slic3r
