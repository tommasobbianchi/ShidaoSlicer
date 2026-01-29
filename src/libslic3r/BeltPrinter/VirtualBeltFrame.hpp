#ifndef slic3r_BeltPrinter_VirtualBeltFrame_hpp_
#define slic3r_BeltPrinter_VirtualBeltFrame_hpp_

#include <Eigen/Dense>

namespace Slic3r {
namespace BeltPrinter {

/**
 * Virtual Belt Frame (V) Coordinate System
 * 
 * A right-handed orthonormal frame where:
 * - Xv: Across belt width (finite)
 * - Yv: Along belt travel direction (effectively unbounded/infinite)
 * - Zv: Normal to belt plane (layer height axis, finite)
 * 
 * Key properties:
 * - Belt plane equation: Zv = 0
 * - Layer planes: Zv = k * layer_height, for integer k >= 0
 * - All slicing operations occur in this frame
 * - Only final G-code emission converts V→F (Firmware Frame)
 */

/// Point in Virtual Belt Frame
using PointV = Eigen::Vector3d;

/// Direction vector in Virtual Belt Frame
using VectorV = Eigen::Vector3d;

/// Point in Firmware Frame
using PointF = Eigen::Vector3d;

/// Direction vector in Firmware Frame
using VectorF = Eigen::Vector3d;

/// Virtual Belt Frame utilities
class VirtualBeltFrame {
public:
    /// Unit vectors in Virtual Belt Frame
    static const VectorV UnitXv;  // (1, 0, 0) - across belt width
    static const VectorV UnitYv;  // (0, 1, 0) - along belt travel
    static const VectorV UnitZv;  // (0, 0, 1) - normal to belt plane
    
    /// Belt plane normal (always +Zv)
    static const VectorV BeltPlaneNormal;
    
    /// Check if a point is on the belt plane (Zv ≈ 0)
    static bool is_on_belt_plane(const PointV& point, double epsilon = 0.05);
    
    /// Check if a point is above the belt plane (Zv > 0)
    static bool is_above_belt_plane(const PointV& point, double epsilon = 1e-6);
    
    /// Project a point onto the belt plane (set Zv = 0)
    static PointV project_to_belt_plane(const PointV& point);
    
    /// Get the Zv coordinate (layer height) of a point
    static double get_layer_height(const PointV& point) { return point.z(); }
    
    /// Get the Yv coordinate (belt position) of a point
    static double get_belt_position(const PointV& point) { return point.y(); }
    
    /// Get the Xv coordinate (belt width position) of a point
    static double get_width_position(const PointV& point) { return point.x(); }
    
    /// Create a point in Virtual Belt Frame
    static PointV make_point(double Xv, double Yv, double Zv) {
        return PointV(Xv, Yv, Zv);
    }
    
    /// Compute distance between two points in V
    static double distance(const PointV& p1, const PointV& p2) {
        return (p2 - p1).norm();
    }
    
    /// Compute segment length in V
    static double segment_length(const PointV& start, const PointV& end) {
        return distance(start, end);
    }
};

} // namespace BeltPrinter
} // namespace Slic3r

#endif // slic3r_BeltPrinter_VirtualBeltFrame_hpp_
