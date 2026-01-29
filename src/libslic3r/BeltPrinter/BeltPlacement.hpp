#ifndef slic3r_BeltPrinter_BeltPlacement_hpp_
#define slic3r_BeltPrinter_BeltPlacement_hpp_

#include "MachineProfile.hpp"
#include "VirtualBeltFrame.hpp"
#include <vector>
#include <string>

namespace Slic3r {
namespace BeltPrinter {

/// Warning types for placement validation
enum class PlacementWarningType {
    AIR_START,                  // min_Zv > 0 and belt raft disabled
    OUT_OF_PRINTABLE_STRIP,     // footprint outside printable Yv window
    ROLLER_COLLISION_RISK       // footprint within roller_clearance_Yv_mm
};

/// Placement warning with details
struct PlacementWarning {
    PlacementWarningType type;
    std::string message;
    double severity;  // 0.0 = info, 1.0 = critical
    
    PlacementWarning(PlacementWarningType t, const std::string& msg, double sev = 0.5)
        : type(t), message(msg), severity(sev) {}
};

/// Settings for mesh placement
struct PlacementSettings {
    double air_gap_mm;              // Gap above belt plane (usually 0)
    double belt_offset_Yv_mm;       // Offset along belt direction
    bool auto_shift_enabled;        // Auto-shift to printable region
    bool raft_enabled;              // Whether raft is enabled
    
    PlacementSettings()
        : air_gap_mm(0.0)
        , belt_offset_Yv_mm(0.0)
        , auto_shift_enabled(true)
        , raft_enabled(false)
    {}
};

/// Bounding box in Virtual Belt Frame
struct BoundingBoxV {
    PointV min_point;
    PointV max_point;
    
    BoundingBoxV() 
        : min_point(PointV::Zero())
        , max_point(PointV::Zero())
    {}
    
    BoundingBoxV(const PointV& min_pt, const PointV& max_pt)
        : min_point(min_pt)
        , max_point(max_pt)
    {}
    
    double min_Xv() const { return min_point.x(); }
    double max_Xv() const { return max_point.x(); }
    double min_Yv() const { return min_point.y(); }
    double max_Yv() const { return max_point.y(); }
    double min_Zv() const { return min_point.z(); }
    double max_Zv() const { return max_point.z(); }
    
    double size_Xv() const { return max_Xv() - min_Xv(); }
    double size_Yv() const { return max_Yv() - min_Yv(); }
    double size_Zv() const { return max_Zv() - min_Zv(); }
    
    PointV center() const { return (min_point + max_point) * 0.5; }
};

/// Mesh placement utilities for belt printers
class BeltPlacement {
public:
    /**
     * Drop mesh to belt plane
     * Translates mesh so min_Zv == air_gap_mm
     * 
     * @param bbox Current bounding box in V
     * @param air_gap_mm Desired air gap above belt (usually 0)
     * @return Translation vector to apply
     */
    static VectorV compute_drop_to_belt_translation(
        const BoundingBoxV& bbox,
        double air_gap_mm = 0.0
    );
    
    /**
     * Apply belt offset
     * Translates mesh along +Yv direction
     * 
     * @param offset_Yv_mm Offset distance in mm
     * @return Translation vector to apply
     */
    static VectorV compute_belt_offset_translation(
        double offset_Yv_mm
    );
    
    /**
     * Validate printable region
     * Checks if mesh footprint is within printable strip
     * 
     * @param bbox Bounding box after placement
     * @param profile Machine profile with printable region
     * @param settings Placement settings
     * @return List of warnings (empty if no issues)
     */
    static std::vector<PlacementWarning> validate_printable_region(
        const BoundingBoxV& bbox,
        const BeltMachineProfile& profile,
        const PlacementSettings& settings
    );
    
    /**
     * Compute auto-shift to bring mesh into printable region
     * 
     * @param bbox Current bounding box
     * @param profile Machine profile
     * @return Translation along Yv to shift into printable region (0 if already valid)
     */
    static double compute_auto_shift_Yv(
        const BoundingBoxV& bbox,
        const BeltMachineProfile& profile
    );
    
    /**
     * Check if mesh is within build volume
     * 
     * @param bbox Bounding box to check
     * @param profile Machine profile
     * @return true if within volume, false otherwise
     */
    static bool is_within_build_volume(
        const BoundingBoxV& bbox,
        const BeltMachineProfile& profile
    );
    
    /**
     * Get printable Yv range from profile
     * Handles infinite belt case
     * 
     * @param profile Machine profile
     * @return [min_Yv, max_Yv] (max may be infinity)
     */
    static std::pair<double, double> get_printable_Yv_range(
        const BeltMachineProfile& profile
    );
};

} // namespace BeltPrinter
} // namespace Slic3r

#endif // slic3r_BeltPrinter_BeltPlacement_hpp_
