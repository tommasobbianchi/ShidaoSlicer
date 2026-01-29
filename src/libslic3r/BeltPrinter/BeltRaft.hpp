#ifndef slic3r_BeltPrinter_BeltRaft_hpp_
#define slic3r_BeltPrinter_BeltRaft_hpp_

#include "MachineProfile.hpp"
#include "VirtualBeltFrame.hpp"
#include <Eigen/Geometry>
#include <vector>

namespace Slic3r {
namespace BeltPrinter {

/// 2D polygon in belt plane (XY in V frame)
using Polygon2D = std::vector<Eigen::Vector2d>;

/// Raft settings
struct RaftSettings {
    double raft_offset_mm;          // Expansion around model footprint
    double lead_in_length_mm;       // Upstream extension for adhesion
    double raft_thickness_mm;       // Total raft height in Zv
    int raft_layers;                // Number of raft layers
    double raft_line_spacing_mm;    // Spacing between raft lines
    bool enabled;                   // Whether raft is enabled
    
    RaftSettings()
        : raft_offset_mm(3.0)
        , lead_in_length_mm(10.0)
        , raft_thickness_mm(0.6)
        , raft_layers(3)
        , raft_line_spacing_mm(2.0)
        , enabled(false)
    {}
};

/// Raft geometry result
struct RaftGeometry {
    Polygon2D footprint;            // Final raft footprint in belt plane
    double min_Yv;                  // Minimum Yv (upstream extent)
    double max_Yv;                  // Maximum Yv (downstream extent)
    double raft_surface_Zv;         // Top surface of raft
    std::vector<double> layer_heights_Zv;  // Z heights of each raft layer
    
    RaftGeometry()
        : min_Yv(0.0)
        , max_Yv(0.0)
        , raft_surface_Zv(0.0)
    {}
};

/// Belt raft generation utilities
class BeltRaft {
public:
    /**
     * Generate belt raft geometry
     * 
     * Algorithm (from specification):
     * 1. Compute model footprint P0 on belt plane
     * 2. Expand P0 by raft_offset_mm => P1
     * 3. Determine upstream direction: u = -sign(belt_positive) * Yv_unit
     * 4. Extend P1 by lead_in_length along u (Minkowski sum) => P2
     * 5. Clip P2 to printable strip [Yv_min, Yv_max]
     * 6. Create raft volume from Zv in [0, raft_thickness_mm]
     * 7. Generate layer heights
     * 
     * @param model_footprint Model footprint polygon in belt plane (XY)
     * @param profile Machine profile
     * @param settings Raft settings
     * @return Raft geometry
     */
    static RaftGeometry generate_raft_geometry(
        const Polygon2D& model_footprint,
        const BeltMachineProfile& profile,
        const RaftSettings& settings
    );
    
    /**
     * Expand polygon by offset (2D Minkowski sum with circle)
     * 
     * @param polygon Input polygon
     * @param offset_mm Expansion distance
     * @return Expanded polygon
     */
    static Polygon2D expand_polygon(
        const Polygon2D& polygon,
        double offset_mm
    );
    
    /**
     * Extend polygon upstream along belt direction
     * This creates a "lead-in" region for better adhesion
     * 
     * @param polygon Input polygon
     * @param lead_in_length_mm Extension distance
     * @param belt_positive_direction Sign of belt positive direction
     * @return Extended polygon
     */
    static Polygon2D extend_upstream(
        const Polygon2D& polygon,
        double lead_in_length_mm,
        int belt_positive_direction
    );
    
    /**
     * Clip polygon to printable Yv range
     * 
     * @param polygon Input polygon
     * @param min_Yv Minimum printable Yv
     * @param max_Yv Maximum printable Yv (may be infinity)
     * @return Clipped polygon
     */
    static Polygon2D clip_to_printable_strip(
        const Polygon2D& polygon,
        double min_Yv,
        double max_Yv
    );
    
    /**
     * Compute bounding box of 2D polygon
     * 
     * @param polygon Input polygon
     * @return [min_x, max_x, min_y, max_y]
     */
    static std::array<double, 4> compute_bbox_2d(
        const Polygon2D& polygon
    );
    
    /**
     * Generate raft layer heights
     * 
     * @param raft_thickness_mm Total raft thickness
     * @param num_layers Number of raft layers
     * @return Vector of Z heights for each layer
     */
    static std::vector<double> generate_layer_heights(
        double raft_thickness_mm,
        int num_layers
    );
    
    /**
     * Check if raft starts at or after leading edge
     * 
     * @param raft_geom Raft geometry
     * @param profile Machine profile
     * @return true if valid, false if starts before leading edge
     */
    static bool validate_leading_edge(
        const RaftGeometry& raft_geom,
        const BeltMachineProfile& profile
    );
    
    /**
     * Create simple rectangular footprint for testing
     * 
     * @param min_x Minimum X
     * @param max_x Maximum X
     * @param min_y Minimum Y
     * @param max_y Maximum Y
     * @return Rectangular polygon
     */
    static Polygon2D create_rectangle(
        double min_x, double max_x,
        double min_y, double max_y
    );
};

} // namespace BeltPrinter
} // namespace Slic3r

#endif // slic3r_BeltPrinter_BeltRaft_hpp_
