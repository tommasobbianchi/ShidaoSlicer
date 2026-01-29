#include "BeltPlacement.hpp"
#include <cmath>
#include <limits>
#include <sstream>

namespace Slic3r {
namespace BeltPrinter {

VectorV BeltPlacement::compute_drop_to_belt_translation(
    const BoundingBoxV& bbox,
    double air_gap_mm)
{
    // Translate so min_Zv == air_gap_mm
    double current_min_Zv = bbox.min_Zv();
    double translation_Zv = air_gap_mm - current_min_Zv;
    
    return VectorV(0.0, 0.0, translation_Zv);
}

VectorV BeltPlacement::compute_belt_offset_translation(
    double offset_Yv_mm)
{
    return VectorV(0.0, offset_Yv_mm, 0.0);
}

std::vector<PlacementWarning> BeltPlacement::validate_printable_region(
    const BoundingBoxV& bbox,
    const BeltMachineProfile& profile,
    const PlacementSettings& settings)
{
    std::vector<PlacementWarning> warnings;
    
    // Check 1: AIR_START warning
    if (bbox.min_Zv() > 0.01 && !settings.raft_enabled) {
        std::ostringstream msg;
        msg << "Mesh starts " << bbox.min_Zv() << " mm above belt plane. "
            << "Consider enabling raft or adjusting air gap.";
        warnings.emplace_back(
            PlacementWarningType::AIR_START,
            msg.str(),
            0.7  // High severity
        );
    }
    
    // Check 2: OUT_OF_PRINTABLE_STRIP warning
    auto [min_Yv_printable, max_Yv_printable] = get_printable_Yv_range(profile);
    
    bool out_of_strip = false;
    if (bbox.min_Yv() < min_Yv_printable) {
        out_of_strip = true;
    }
    if (!std::isinf(max_Yv_printable) && bbox.max_Yv() > max_Yv_printable) {
        out_of_strip = true;
    }
    
    if (out_of_strip) {
        std::ostringstream msg;
        msg << "Mesh footprint [" << bbox.min_Yv() << ", " << bbox.max_Yv() 
            << "] mm extends outside printable strip ["
            << min_Yv_printable << ", ";
        if (std::isinf(max_Yv_printable)) {
            msg << "∞";
        } else {
            msg << max_Yv_printable;
        }
        msg << "] mm.";
        
        if (settings.auto_shift_enabled) {
            msg << " Auto-shift can correct this.";
        }
        
        warnings.emplace_back(
            PlacementWarningType::OUT_OF_PRINTABLE_STRIP,
            msg.str(),
            0.9  // Critical severity
        );
    }
    
    // Check 3: ROLLER_COLLISION_RISK warning
    double roller_clearance = profile.roller_clearance_Yv_mm;
    double forbidden_region_start = min_Yv_printable - roller_clearance;
    
    if (bbox.min_Yv() < forbidden_region_start) {
        std::ostringstream msg;
        msg << "Mesh footprint starts at " << bbox.min_Yv() 
            << " mm, within roller clearance zone (< " 
            << forbidden_region_start << " mm). Risk of collision!";
        warnings.emplace_back(
            PlacementWarningType::ROLLER_COLLISION_RISK,
            msg.str(),
            1.0  // Maximum severity
        );
    }
    
    return warnings;
}

double BeltPlacement::compute_auto_shift_Yv(
    const BoundingBoxV& bbox,
    const BeltMachineProfile& profile)
{
    auto [min_Yv_printable, max_Yv_printable] = get_printable_Yv_range(profile);
    
    // If mesh starts before printable region, shift forward
    if (bbox.min_Yv() < min_Yv_printable) {
        return min_Yv_printable - bbox.min_Yv();
    }
    
    // If mesh ends after printable region (and region is bounded), shift backward
    if (!std::isinf(max_Yv_printable) && bbox.max_Yv() > max_Yv_printable) {
        return max_Yv_printable - bbox.max_Yv();
    }
    
    // No shift needed
    return 0.0;
}

bool BeltPlacement::is_within_build_volume(
    const BoundingBoxV& bbox,
    const BeltMachineProfile& profile)
{
    // Check Xv range
    if (bbox.min_Xv() < profile.Xv_min_mm || bbox.max_Xv() > profile.Xv_max_mm) {
        return false;
    }
    
    // Check Zv range
    if (bbox.min_Zv() < profile.Zv_min_mm || bbox.max_Zv() > profile.Zv_max_mm) {
        return false;
    }
    
    // Check Yv range (if bounded)
    auto [min_Yv, max_Yv] = get_printable_Yv_range(profile);
    if (bbox.min_Yv() < min_Yv) {
        return false;
    }
    if (!std::isinf(max_Yv) && bbox.max_Yv() > max_Yv) {
        return false;
    }
    
    return true;
}

std::pair<double, double> BeltPlacement::get_printable_Yv_range(
    const BeltMachineProfile& profile)
{
    double min_Yv = profile.belt_printable_Yv_min_mm;
    double max_Yv = profile.belt_printable_Yv_max_mm;
    
    // Handle infinite belt case
    if (profile.is_infinite_belt() || std::isinf(max_Yv)) {
        max_Yv = std::numeric_limits<double>::infinity();
    }
    
    return {min_Yv, max_Yv};
}

} // namespace BeltPrinter
} // namespace Slic3r
