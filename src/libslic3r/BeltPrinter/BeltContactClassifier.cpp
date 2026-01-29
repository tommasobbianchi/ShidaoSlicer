#include "BeltContactClassifier.hpp"
#include <cmath>

namespace Slic3r {
namespace BeltPrinter {

ContactClass BeltContactClassifier::classify_segment(
    const ToolpathSegment& segment,
    const ContactClassificationSettings& settings)
{
    return classify_segment(segment.start, segment.end, settings);
}

ContactClass BeltContactClassifier::classify_segment(
    const PointV& start,
    const PointV& end,
    const ContactClassificationSettings& settings)
{
    // Get minimum Zv of the segment
    double min_Zv = std::min(start.z(), end.z());
    
    // Check if on belt plane (Zv ≈ 0)
    if (is_on_belt_plane(min_Zv, settings.epsilon_mm)) {
        return ContactClass::BELT_CONTACT;
    }
    
    // Check if on raft surface (if raft enabled)
    if (settings.raft_enabled) {
        if (is_on_raft_surface(min_Zv, settings.raft_surface_Zv, settings.epsilon_mm)) {
            return ContactClass::BELT_CONTACT;
        }
    }
    
    // Otherwise, it's on previous plastic
    return ContactClass::NON_CONTACT;
}

bool BeltContactClassifier::is_on_belt_plane(
    double Zv,
    double epsilon)
{
    return std::abs(Zv - 0.0) < epsilon;
}

bool BeltContactClassifier::is_on_raft_surface(
    double Zv,
    double raft_surface_Zv,
    double epsilon)
{
    return std::abs(Zv - raft_surface_Zv) < epsilon;
}

ContactParameterSet BeltContactClassifier::get_parameter_set(
    ContactClass contact_class,
    const ContactClassificationSettings& settings)
{
    switch (contact_class) {
        case ContactClass::BELT_CONTACT:
            return settings.belt_contact_params;
        case ContactClass::NON_CONTACT:
            return settings.normal_params;
        default:
            return settings.normal_params;
    }
}

void BeltContactClassifier::classify_segments(
    std::vector<ToolpathSegment>& segments,
    const ContactClassificationSettings& settings)
{
    for (auto& segment : segments) {
        segment.contact_class = classify_segment(segment, settings);
    }
}

std::pair<size_t, size_t> BeltContactClassifier::count_by_class(
    const std::vector<ToolpathSegment>& segments)
{
    size_t belt_contact_count = 0;
    size_t non_contact_count = 0;
    
    for (const auto& segment : segments) {
        if (segment.contact_class == ContactClass::BELT_CONTACT) {
            belt_contact_count++;
        } else {
            non_contact_count++;
        }
    }
    
    return {belt_contact_count, non_contact_count};
}

ContactClassificationSettings BeltContactClassifier::create_settings_from_raft(
    const RaftGeometry& raft_geom,
    bool raft_enabled)
{
    ContactClassificationSettings settings;
    settings.raft_enabled = raft_enabled;
    settings.raft_surface_Zv = raft_geom.raft_surface_Zv;
    
    // Default belt contact parameters (from specification):
    // - Slower speed (0.5x) for better adhesion
    // - More flow (1.2x) for squish
    // - No fan (0.0x) for better adhesion
    settings.belt_contact_params = ContactParameterSet(0.5, 1.2, 0.0);
    
    // Normal parameters
    settings.normal_params = ContactParameterSet(1.0, 1.0, 1.0);
    
    return settings;
}

} // namespace BeltPrinter
} // namespace Slic3r
