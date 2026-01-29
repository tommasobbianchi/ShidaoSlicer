#include <catch2/catch_all.hpp>
#include "libslic3r/GCodeWriter.hpp"
#include "libslic3r/Geometry.hpp"

using namespace Slic3r;

TEST_CASE("GCodeWriter Belt Transform Custom Matrix", "[belt_gcode]") {
    GCodeWriter writer;
    
    // Simulate M_VF for 45 deg Y-belt
    // alpha = 45 deg
    // M_VF:
    // 1, 0, 0
    // 0, s, -c
    // 0, c, s
    double alpha = Geometry::deg2rad(45.0);
    double s = std::sin(alpha);
    double c = std::cos(alpha);
    
    Transform3d M_VF = Transform3d::Identity();
    M_VF.matrix() << 
        1, 0, 0, 0,
        0, s, -c, 0,
        0, c, s, 0,
        0, 0, 0, 1;
        
    // Simulate Shift in V: Place object at Y=10.
    Vec3d shift_V(0.0, 10.0, 0.0);
    
    // Compute Shift_F expected
    // Shift_F = M_VF * shift_V
    Vec3d shift_F = M_VF * shift_V;
    // Expected: (0, 10*s, 10*c)
    
    // Set Transform
    writer.set_belt_transform(true, M_VF, shift_F);
    
    // Test Point in V (e.g. Sliced Point at Y=1, Z=0 relative to Object Origin)
    // Point P_V = (0, 1, 0).
    // Absolute V position = P_V + shift_V = (0, 11, 0).
    // We pass P_V to transform_belt_point (point is in local coord system if slicing centers it, 
    // or V if slicing assumes V? GCodeWriter usually receives absolute coordinates)
    
    // Wait, GCodeWriter receives coordinates from GCode generator.
    // In GCode.cpp process_layer, we iterate over slices.
    // The slices are in Object Coordinate System? Or Sliced Coordinate System?
    // PrintObject stores slices. Slices are relative to PrintObject origin?
    // PrintObject origin is usually (0,0) in V?
    // Slices are 2D polygons + Z height.
    // GCode generator converts them to 3D points.
    // If P is (x, y, z) in V.
    // writer.transform_belt_point(P) should result in F.
    
    // writer formula: (M_VF * P) + Shift_F.
    // = M_VF * P + M_VF * shift_V.
    // = M_VF * (P + shift_V).
    // This is valid if P is relative to shift_V.
    // i.e. P is Object-Local. shift_V is Object Position.
    
    Vec3d point_local_V(0.0, 1.0, 0.0);
    
    Vec3d result_F = writer.transform_belt_point(point_local_V);
    
    Vec3d expected_total_V = point_local_V + shift_V; // (0, 11, 0)
    Vec3d expected_F = M_VF * expected_total_V; // (0, 11s, 11c)
    
    REQUIRE(result_F.x() == Catch::Approx(expected_F.x()));
    REQUIRE(result_F.y() == Catch::Approx(expected_F.y()));
    REQUIRE(result_F.z() == Catch::Approx(expected_F.z()));
}
