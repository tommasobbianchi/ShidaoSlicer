#include "VirtualBeltFrame.hpp"
#include <cmath>

namespace Slic3r {
namespace BeltPrinter {

// Static member initialization
const VectorV VirtualBeltFrame::UnitXv = VectorV(1.0, 0.0, 0.0);
const VectorV VirtualBeltFrame::UnitYv = VectorV(0.0, 1.0, 0.0);
const VectorV VirtualBeltFrame::UnitZv = VectorV(0.0, 0.0, 1.0);
const VectorV VirtualBeltFrame::BeltPlaneNormal = VectorV(0.0, 0.0, 1.0);

bool VirtualBeltFrame::is_on_belt_plane(const PointV& point, double epsilon)
{
    return std::abs(point.z()) < epsilon;
}

bool VirtualBeltFrame::is_above_belt_plane(const PointV& point, double epsilon)
{
    return point.z() > epsilon;
}

PointV VirtualBeltFrame::project_to_belt_plane(const PointV& point)
{
    return PointV(point.x(), point.y(), 0.0);
}

} // namespace BeltPrinter
} // namespace Slic3r
