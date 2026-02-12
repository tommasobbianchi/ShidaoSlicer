#ifndef slic3r_BeltPrinter_DirectionalSupports_hpp_
#define slic3r_BeltPrinter_DirectionalSupports_hpp_

#include "MachineProfile.hpp"
#include "VirtualBeltFrame.hpp"
#include "../Polygon.hpp"
#include <Eigen/Dense>

namespace Slic3r {

class PrintObject;  // Forward declaration

namespace BeltPrinter {

/// Support dependency classification
enum class SupportDependency {
    FORWARD,    // Overhang leans forward along belt - NEEDS support
    BACKWARD,   // Overhang leans backward - naturally supported by belt motion
    NEUTRAL     // Not an overhang or conventional support logic applies
};

/// Facet classification result
struct FacetClassification {
    SupportDependency dependency;
    double overhang_angle_deg;      // Angle from vertical (0° = vertical, 90° = horizontal)
    double belt_direction_component; // Component along belt direction
    bool needs_support;             // Final decision
    
    FacetClassification()
        : dependency(SupportDependency::NEUTRAL)
        , overhang_angle_deg(0.0)
        , belt_direction_component(0.0)
        , needs_support(false)
    {}
};

/// Settings for directional support generation
struct DirectionalSupportSettings {
    double overhang_threshold_deg;   // Angle threshold for overhang (default 45°)
    int belt_positive_direction;     // +1 or -1
    bool enable_directional_logic;   // Enable/disable directional classification
    
    DirectionalSupportSettings()
        : overhang_threshold_deg(45.0)
        , belt_positive_direction(1)
        , enable_directional_logic(true)
    {}
};

/// Directional support utilities for belt printers
class DirectionalSupports {
public:
    /**
     * Classify overhang direction for a facet
     * 
     * Algorithm:
     * 1. Compute overhang angle α = arccos(dot(normal, +Zv))
     * 2. If α < threshold, return NEUTRAL (not an overhang)
     * 3. Project steepest descent direction into belt plane
     * 4. Check Yv component sign vs belt_positive_direction
     * 5. Return FORWARD (needs support) or BACKWARD (naturally supported)
     * 
     * @param facet_normal Normal vector of the facet in V frame
     * @param settings Support settings including threshold and belt direction
     * @return Classification result
     */
    static FacetClassification classify_overhang_direction(
        const VectorV& facet_normal,
        const DirectionalSupportSettings& settings
    );
    
    /**
     * Determine if a facet needs support based on directional logic
     * 
     * @param facet_normal Normal vector in V frame
     * @param settings Support settings
     * @return true if support is needed, false otherwise
     */
    static bool needs_support(
        const VectorV& facet_normal,
        const DirectionalSupportSettings& settings
    );
    
    /**
     * Compute overhang angle from vertical
     * Returns angle in degrees (0° = vertical, 90° = horizontal)
     * 
     * @param facet_normal Normal vector in V frame
     * @return Overhang angle in degrees
     */
    static double compute_overhang_angle(
        const VectorV& facet_normal
    );
    
    /**
     * Compute steepest descent direction for a facet
     * This is the direction material would "fall" if not supported
     * 
     * @param facet_normal Normal vector in V frame
     * @return Steepest descent direction (normalized)
     */
    static VectorV compute_steepest_descent(
        const VectorV& facet_normal
    );
    
    /**
     * Project a vector onto the belt plane (XY plane in V)
     * 
     * @param vec Vector to project
     * @return Projected vector (Zv component = 0)
     */
    static VectorV project_to_belt_plane(
        const VectorV& vec
    );
    
    /**
     * Get belt direction component of a vector
     * Positive = forward along belt, Negative = backward
     * 
     * @param vec Vector in V frame
     * @param belt_positive_direction Sign of belt positive direction (+1 or -1)
     * @return Component along belt direction
     */
    static double get_belt_direction_component(
        const VectorV& vec,
        int belt_positive_direction
    );
    
    /**
     * Create settings from machine profile
     *
     * @param profile Machine profile
     * @param overhang_threshold_deg Overhang angle threshold
     * @return Support settings
     */
    static DirectionalSupportSettings create_settings_from_profile(
        const BeltMachineProfile& profile,
        double overhang_threshold_deg = 45.0
    );

    /**
     * Compute per-layer blocker polygons for backward-facing overhangs.
     *
     * Iterates over all model-part mesh facets, transforms them to V-frame,
     * classifies each with classify_overhang_direction(), and projects
     * BACKWARD triangles as blocker polygons onto the layers they span.
     *
     * @param object PrintObject (provides mesh, trafo, layers, belt profile)
     * @param settings Directional support settings
     * @return Vector of Polygons indexed by layer, for merging into blocker vectors
     */
    static std::vector<Polygons> compute_belt_overhang_blockers(
        const PrintObject& object,
        const DirectionalSupportSettings& settings
    );
};

} // namespace BeltPrinter
} // namespace Slic3r

#endif // slic3r_BeltPrinter_DirectionalSupports_hpp_
