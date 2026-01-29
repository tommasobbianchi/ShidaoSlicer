#include "../src/libslic3r/BeltTransform.hpp"
#include "../src/libslic3r/BeltTransform.cpp" 
// Including .cpp directly just for quick link-less testing in this script, 
// normally we compile separately.

#include <iostream>
#include <iomanip>

int main() {
    using namespace Slic3r;
    
    double angle = 45.0;
    std::cout << "Testing Belt Transform with angle: " << angle << "\n";
    
    // Test Forward
    Transform3d fwd = BeltTransform::make_forward_transform(angle);
    std::cout << "Forward Matrix:\n" << fwd.matrix() << "\n\n";
    
    // Test Inverse
    Transform3d inv = BeltTransform::make_inverse_transform(angle);
    std::cout << "Inverse Matrix:\n" << inv.matrix() << "\n\n";
    
    // Test Point Transformation (Inverse)
    // Virtual point (0, 10, 10) -> x=0, y=z/sin(45), z=y-z/tan(45)
    // z/sin(45) = 10 / 0.707 = 14.14
    // y - z/1 = 10 - 10 = 0
    // Expected Machine: (0, 14.14, 0)
    
    Vec3d virtual_pt(0, 10.0, 10.0);
    Vec3d machine_pt = BeltTransform::inverse_transform_point(virtual_pt, angle);
    
    std::cout << "Virtual Point: " << virtual_pt.transpose() << "\n";
    std::cout << "Machine Point: " << machine_pt.transpose() << "\n";
    
    if (std::abs(machine_pt.z()) < 1e-4 && std::abs(machine_pt.y() - 14.1421) < 1e-2) {
         std::cout << "SUCCESS: Point transform is correct.\n";
    } else {
         std::cout << "FAILURE: Point transform mismatch.\n";
         return 1;
    }

    return 0;
}
