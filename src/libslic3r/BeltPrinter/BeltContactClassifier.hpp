#ifndef slic3r_BeltPrinter_BeltContactClassifier_hpp_
#define slic3r_BeltPrinter_BeltContactClassifier_hpp_

#include "VirtualBeltFrame.hpp"
#include "BeltRaft.hpp"
#include <vector>

namespace Slic3r {
namespace BeltPrinter {

/// Contact classification for toolpath segments
enum class ContactClass {
    BELT_CONTACT,    // Segment touches belt plane or raft surface
    NON_CONTACT      // Segment deposited on previous plastic
};

/// Toolpath segment in Virtual Belt Frame
struct ToolpathSegment {
    PointV start;
    PointV end;
    ContactClass contact_class;
    
    ToolpathSegment()
        : start(PointV::Zero())
        , end(PointV::Zero())
        , contact_class(ContactClass::NON_CONTACT)
    {}
    
    ToolpathSegment(const PointV& s, const PointV& e)
        : start(s)
        , end(e)
        , contact_class(ContactClass::NON_CONTACT)
    {}
    
    /// Get segment length in V frame
    double length() const {
        return (end - start).norm();
    }
    
    /// Get minimum Zv coordinate of segment
    double min_Zv() const {
        return std::min(start.z(), end.z());
    }
    
    /// Get maximum Zv coordinate of segment
    double max_Zv() const {
        return std::max(start.z(), end.z());
    }
};

/// Parameter set for different contact classes
struct ContactParameterSet {
    double speed_multiplier;    // Speed multiplier (1.0 = normal)
    double flow_multiplier;     // Flow multiplier (1.0 = normal)
    double fan_multiplier;      // Fan speed multiplier (1.0 = normal)
    
    ContactParameterSet()
        : speed_multiplier(1.0)
        , flow_multiplier(1.0)
        , fan_multiplier(1.0)
    {}
    
    ContactParameterSet(double speed, double flow, double fan)
        : speed_multiplier(speed)
        , flow_multiplier(flow)
        , fan_multiplier(fan)
    {}
};

/// Settings for contact classification
struct ContactClassificationSettings {
    double epsilon_mm;                      // Tolerance for "on belt" detection
    double raft_surface_Zv;                 // Top surface of raft (if enabled)
    bool raft_enabled;                      // Whether raft is enabled
    ContactParameterSet belt_contact_params;  // Parameters for BELT_CONTACT
    ContactParameterSet normal_params;        // Parameters for NON_CONTACT
    
    ContactClassificationSettings()
        : epsilon_mm(0.05)
        , raft_surface_Zv(0.0)
        , raft_enabled(false)
        , belt_contact_params(0.5, 1.2, 0.0)  // Slower, more flow, no fan
        , normal_params(1.0, 1.0, 1.0)        // Normal parameters
    {}
};

/// Belt contact classification utilities
class BeltContactClassifier {
public:
    /**
     * Classify a toolpath segment
     * 
     * A segment is BELT_CONTACT if its minimum Zv is within epsilon of:
     * - Belt plane (Zv = 0), OR
     * - Raft surface (Zv = raft_surface_Zv) if raft is enabled
     * 
     * @param segment Toolpath segment in V frame
     * @param settings Classification settings
     * @return Contact classification
     */
    static ContactClass classify_segment(
        const ToolpathSegment& segment,
        const ContactClassificationSettings& settings
    );
    
    /**
     * Classify a segment by its endpoints
     * 
     * @param start Start point in V frame
     * @param end End point in V frame
     * @param settings Classification settings
     * @return Contact classification
     */
    static ContactClass classify_segment(
        const PointV& start,
        const PointV& end,
        const ContactClassificationSettings& settings
    );
    
    /**
     * Check if a Z coordinate is on the belt plane
     * 
     * @param Zv Z coordinate in V frame
     * @param epsilon Tolerance
     * @return true if on belt plane
     */
    static bool is_on_belt_plane(
        double Zv,
        double epsilon = 0.05
    );
    
    /**
     * Check if a Z coordinate is on the raft surface
     * 
     * @param Zv Z coordinate in V frame
     * @param raft_surface_Zv Raft surface height
     * @param epsilon Tolerance
     * @return true if on raft surface
     */
    static bool is_on_raft_surface(
        double Zv,
        double raft_surface_Zv,
        double epsilon = 0.05
    );
    
    /**
     * Get parameter set for a contact class
     * 
     * @param contact_class Classification result
     * @param settings Classification settings
     * @return Appropriate parameter set
     */
    static ContactParameterSet get_parameter_set(
        ContactClass contact_class,
        const ContactClassificationSettings& settings
    );
    
    /**
     * Classify multiple segments
     * Modifies segments in-place to set their contact_class
     * 
     * @param segments Vector of segments to classify
     * @param settings Classification settings
     */
    static void classify_segments(
        std::vector<ToolpathSegment>& segments,
        const ContactClassificationSettings& settings
    );
    
    /**
     * Count segments by contact class
     * 
     * @param segments Vector of classified segments
     * @return [belt_contact_count, non_contact_count]
     */
    static std::pair<size_t, size_t> count_by_class(
        const std::vector<ToolpathSegment>& segments
    );
    
    /**
     * Create settings from raft geometry
     * 
     * @param raft_geom Raft geometry (if raft enabled)
     * @param raft_enabled Whether raft is enabled
     * @return Classification settings
     */
    static ContactClassificationSettings create_settings_from_raft(
        const RaftGeometry& raft_geom,
        bool raft_enabled = true
    );
};

} // namespace BeltPrinter
} // namespace Slic3r

#endif // slic3r_BeltPrinter_BeltContactClassifier_hpp_
