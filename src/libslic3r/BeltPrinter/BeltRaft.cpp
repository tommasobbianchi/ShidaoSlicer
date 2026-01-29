#include "BeltRaft.hpp"
#include "BeltPlacement.hpp"
#include <algorithm>
#include <cmath>
#include <limits>

namespace Slic3r {
namespace BeltPrinter {

RaftGeometry BeltRaft::generate_raft_geometry(
    const Polygon2D& model_footprint,
    const BeltMachineProfile& profile,
    const RaftSettings& settings)
{
    printf("DEBUG BeltRaft: generate_raft_geometry called\n");
    printf("DEBUG BeltRaft: model_footprint has %zu vertices\n", model_footprint.size());
    if (!model_footprint.empty()) {
        for (size_t i = 0; i < model_footprint.size(); ++i) {
            printf("DEBUG BeltRaft:   vertex[%zu] = (%.2f, %.2f)\n", 
                   i, model_footprint[i].x(), model_footprint[i].y());
        }
    }
    printf("DEBUG BeltRaft: settings.enabled=%d, raft_layers=%d\n", 
           settings.enabled, settings.raft_layers);
    
    RaftGeometry result;
    
    if (!settings.enabled || model_footprint.empty()) {
        printf("DEBUG BeltRaft: Early return - disabled or empty footprint\n");
        return result;
    }
    
    printf("DEBUG BeltRaft: Expanding polygon...\n");
    
    // Step 1: Model footprint is P0 (already provided)
    
    // Step 2: Expand by raft_offset_mm => P1
    Polygon2D P1 = expand_polygon(model_footprint, settings.raft_offset_mm);
    
    // Step 3 & 4: Extend upstream by lead_in_length => P2
    Polygon2D P2 = extend_upstream(P1, settings.lead_in_length_mm, 
                                    profile.belt_positive_direction_in_V);
    
    printf("DEBUG BeltRaft: About to call BeltPlacement::get_printable_Yv_range...\n");
    // Step 5: Clip to printable strip
    auto [min_Yv, max_Yv] = BeltPlacement::get_printable_Yv_range(profile);
    printf("DEBUG BeltRaft: get_printable_Yv_range returned min=%.2f, max=%.2f\n", min_Yv, max_Yv);
    result.footprint = clip_to_printable_strip(P2, min_Yv, max_Yv);
    printf("DEBUG BeltRaft: clip_to_printable_strip completed\n");
    
    // Step 6: Compute bounds
    printf("DEBUG BeltRaft: About to call compute_bbox_2d...\n");
    auto bbox = compute_bbox_2d(result.footprint);
    printf("DEBUG BeltRaft: compute_bbox_2d returned\n");
    result.min_Yv = bbox[2];  // min_y
    result.max_Yv = bbox[3];  // max_y
    
    printf("DEBUG BeltRaft: About to generate_layer_heights...\n");
    // Step 7: Generate layer heights
    result.layer_heights_Zv = generate_layer_heights(
        settings.raft_thickness_mm, settings.raft_layers);
    printf("DEBUG BeltRaft: generate_layer_heights returned %zu layers\n", result.layer_heights_Zv.size());
    result.raft_surface_Zv = settings.raft_thickness_mm;
    
    printf("DEBUG BeltRaft: generate_raft_geometry returning\n");
    return result;
}

Polygon2D BeltRaft::expand_polygon(
    const Polygon2D& polygon,
    double offset_mm)
{
    printf("DEBUG BeltRaft::expand_polygon: polygon.size()=%zu, offset=%.2f\n", polygon.size(), offset_mm);
    // Simplified expansion: offset each vertex outward along its normal
    // For a proper implementation, use a polygon offsetting library
    // This is a basic approximation for testing
    
    if (polygon.size() < 3) {
        printf("DEBUG BeltRaft::expand_polygon: polygon too small, returning as-is\n");
        return polygon;
    }
    
    Polygon2D expanded;
    expanded.reserve(polygon.size());
    
    printf("DEBUG BeltRaft::expand_polygon: Computing centroid...\n");
    // Compute centroid
    Eigen::Vector2d centroid(0, 0);
    for (const auto& pt : polygon) {
        centroid += pt;
    }
    centroid /= polygon.size();
    printf("DEBUG BeltRaft::expand_polygon: centroid=(%.2f, %.2f)\n", centroid.x(), centroid.y());
    
    // Offset each vertex away from centroid
    printf("DEBUG BeltRaft::expand_polygon: Offsetting vertices...\n");
    for (size_t i = 0; i < polygon.size(); ++i) {
        const auto& pt = polygon[i];
        Eigen::Vector2d direction = (pt - centroid).normalized();
        Eigen::Vector2d new_pt = pt + direction * offset_mm;
        printf("DEBUG BeltRaft::expand_polygon: vertex %zu: (%.2f,%.2f) -> (%.2f,%.2f)\n",
               i, pt.x(), pt.y(), new_pt.x(), new_pt.y());
        expanded.push_back(new_pt);
    }
    printf("DEBUG BeltRaft::expand_polygon: Done, expanded.size()=%zu\n", expanded.size());
    
    return expanded;
}

Polygon2D BeltRaft::extend_upstream(
    const Polygon2D& polygon,
    double lead_in_length_mm,
    int belt_positive_direction)
{
    printf("DEBUG BeltRaft::extend_upstream: polygon.size()=%zu, lead_in=%.2f, belt_dir=%d\n",
           polygon.size(), lead_in_length_mm, belt_positive_direction);
    // Upstream direction is opposite to belt positive direction
    // If belt_positive_direction = +1 (+Yv is forward), upstream is -Yv
    double upstream_offset = -belt_positive_direction * lead_in_length_mm;
    printf("DEBUG BeltRaft::extend_upstream: upstream_offset=%.2f\n", upstream_offset);
    
    printf("DEBUG Belt Raft::extend_upstream: Computing bbox...\n");
    // Find min and max Y coordinates
    auto bbox = compute_bbox_2d(polygon);
    double min_y = bbox[2];
    double max_y = bbox[3];
    printf("DEBUG BeltRaft::extend_upstream: bbox min_y=%.2f, max_y=%.2f\n", min_y, max_y);
    
    // Extend the polygon upstream by adding a rectangular extension
    // This is a simplified version - a full implementation would do proper Minkowski sum
    
    Polygon2D extended = polygon;
    printf("DEBUG BeltRaft::extend_upstream: Copied polygon, extended.size()=%zu\n", extended.size());
    
    // Add upstream extension rectangle
    // Find vertices at min_y and max_y
    double min_x = bbox[0];
    double max_x = bbox[1];
    printf("DEBUG BeltRaft::extend_upstream: min_x=%.2f, max_x=%.2f\n", min_x, max_x);
    
    // Create extension rectangle
    if (upstream_offset < 0) {
        printf("DEBUG BeltRaft::extend_upstream: Extending in -Y direction\n");
        // Extending in -Y direction
        extended.push_back(Eigen::Vector2d(min_x, min_y));
        extended.push_back(Eigen::Vector2d(min_x, min_y + upstream_offset));
        extended.push_back(Eigen::Vector2d(max_x, min_y + upstream_offset));
        extended.push_back(Eigen::Vector2d(max_x, min_y));
    } else {
        printf("DEBUG BeltRaft::extend_upstream: Extending in +Y direction\n");
        // Extending in +Y direction
        extended.push_back(Eigen::Vector2d(min_x, max_y));
        extended.push_back(Eigen::Vector2d(min_x, max_y + upstream_offset));
        extended.push_back(Eigen::Vector2d(max_x, max_y + upstream_offset));
        extended.push_back(Eigen::Vector2d(max_x, max_y));
    }
    printf("DEBUG BeltRaft::extend_upstream: Done, extended.size()=%zu\n", extended.size());
    
    return extended;
}

Polygon2D BeltRaft::clip_to_printable_strip(
    const Polygon2D& polygon,
    double min_Yv,
    double max_Yv)
{
    // Simplified clipping: just clamp Y coordinates
    // A proper implementation would use polygon clipping algorithms
    
    Polygon2D clipped;
    clipped.reserve(polygon.size());
    
    for (const auto& pt : polygon) {
        double y_clamped = std::max(min_Yv, std::min(max_Yv, pt.y()));
        clipped.push_back(Eigen::Vector2d(pt.x(), y_clamped));
    }
    
    return clipped;
}

std::array<double, 4> BeltRaft::compute_bbox_2d(
    const Polygon2D& polygon)
{
    if (polygon.empty()) {
        return {0, 0, 0, 0};
    }
    
    double min_x = std::numeric_limits<double>::max();
    double max_x = -std::numeric_limits<double>::max();
    double min_y = std::numeric_limits<double>::max();
    double max_y = -std::numeric_limits<double>::max();
    
    for (const auto& pt : polygon) {
        min_x = std::min(min_x, pt.x());
        max_x = std::max(max_x, pt.x());
        min_y = std::min(min_y, pt.y());
        max_y = std::max(max_y, pt.y());
    }
    
    return {min_x, max_x, min_y, max_y};
}

std::vector<double> BeltRaft::generate_layer_heights(
    double raft_thickness_mm,
    int num_layers)
{
    std::vector<double> heights;
    heights.reserve(num_layers);
    
    if (num_layers <= 0) {
        return heights;
    }
    
    double layer_height = raft_thickness_mm / num_layers;
    
    for (int i = 0; i < num_layers; ++i) {
        heights.push_back((i + 1) * layer_height);
    }
    
    return heights;
}

bool BeltRaft::validate_leading_edge(
    const RaftGeometry& raft_geom,
    const BeltMachineProfile& profile)
{
    // Raft should start at or after the leading edge
    return raft_geom.min_Yv >= profile.belt_leading_edge_Yv_mm;
}

Polygon2D BeltRaft::create_rectangle(
    double min_x, double max_x,
    double min_y, double max_y)
{
    Polygon2D rect;
    rect.reserve(4);
    
    rect.push_back(Eigen::Vector2d(min_x, min_y));
    rect.push_back(Eigen::Vector2d(max_x, min_y));
    rect.push_back(Eigen::Vector2d(max_x, max_y));
    rect.push_back(Eigen::Vector2d(min_x, max_y));
    
    return rect;
}

} // namespace BeltPrinter
} // namespace Slic3r
