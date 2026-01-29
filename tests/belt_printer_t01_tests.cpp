#include "../src/libslic3r/BeltPrinter/MachineProfile.hpp"
#include "../src/libslic3r/BeltPrinter/VirtualBeltFrame.hpp"
#include "../src/libslic3r/BeltPrinter/BeltTransforms.hpp"
#include <iostream>
#include <cassert>
#include <cmath>

using namespace Slic3r::BeltPrinter;

void test_UT01_M_VF_VALIDATION() {
    std::cout << "\n=== UT01: M_VF Validation ===" << std::endl;
    
    // Test 1: Valid orthonormal matrix (CR30 example)
    Eigen::Matrix3d M_valid;
    M_valid << 1, 0, 0,
               0, 0, 1,
               0, 1, 0;
    
    bool is_valid = BeltTransforms::validate_M_VF_orthonormal(M_valid);
    assert(is_valid && "CR30 M_VF should be valid");
    std::cout << "✓ CR30 M_VF is orthonormal" << std::endl;
    
    // Test 2: Invalid matrix (not orthonormal)
    Eigen::Matrix3d M_invalid;
    M_invalid << 1, 0, 0,
                 0, 2, 0,  // Scaling factor 2
                 0, 0, 1;
    
    is_valid = BeltTransforms::validate_M_VF_orthonormal(M_invalid);
    assert(!is_valid && "Scaled matrix should be invalid");
    std::cout << "✓ Scaled matrix correctly rejected" << std::endl;
    
    // Test 3: Invalid matrix (shear)
    Eigen::Matrix3d M_shear;
    M_shear << 1, 0.5, 0,
               0, 1,   0,
               0, 0,   1;
    
    is_valid = BeltTransforms::validate_M_VF_orthonormal(M_shear);
    assert(!is_valid && "Shear matrix should be invalid");
    std::cout << "✓ Shear matrix correctly rejected" << std::endl;
    
    // Test 4: Profile validation
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    assert(profile.is_validated && "CR30 profile should validate");
    std::cout << "✓ CR30 profile validates successfully" << std::endl;
    std::cout << "  Machine ID: " << profile.machine_id << std::endl;
    std::cout << "  Gantry angle: " << profile.gantry_angle_theta_deg << "°" << std::endl;
}

void test_UT02_NATIVE_LENGTH_INVARIANCE() {
    std::cout << "\n=== UT02: Native Length Invariance ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    
    // Test segment in V
    PointV start_V(10.0, 20.0, 5.0);
    PointV end_V(15.0, 25.0, 10.0);
    
    double length_V = VirtualBeltFrame::segment_length(start_V, end_V);
    std::cout << "  Segment length in V: " << length_V << " mm" << std::endl;
    
    // Transform to F
    PointF start_F = BeltTransforms::apply_V_to_F_mapping(start_V, profile);
    PointF end_F = BeltTransforms::apply_V_to_F_mapping(end_V, profile);
    
    double length_F = (end_F - start_F).norm();
    std::cout << "  Segment length in F: " << length_F << " mm" << std::endl;
    
    // Lengths should be equal (orthonormal transform)
    double length_diff = std::abs(length_V - length_F);
    assert(length_diff < 1e-6 && "Segment length should be preserved");
    std::cout << "✓ Segment length preserved (diff: " << length_diff << " mm)" << std::endl;
    
    // Test inverse transform
    PointV start_V_recovered = BeltTransforms::apply_F_to_V_mapping(start_F, profile);
    PointV end_V_recovered = BeltTransforms::apply_F_to_V_mapping(end_F, profile);
    
    double recovery_error_start = (start_V - start_V_recovered).norm();
    double recovery_error_end = (end_V - end_V_recovered).norm();
    
    assert(recovery_error_start < 1e-6 && "F→V→F should recover original point");
    assert(recovery_error_end < 1e-6 && "F→V→F should recover original point");
    std::cout << "✓ Inverse transform recovers original points" << std::endl;
}

void test_UT03_COMPAT_EXTRUSION_RECALC() {
    std::cout << "\n=== UT03: Compatibility Extrusion Recalc ===" << std::endl;
    
    // Create a non-orthonormal transform (includes sqrt(2) scaling)
    Eigen::Matrix4d T_compat = Eigen::Matrix4d::Identity();
    double scale_factor = std::sqrt(2.0);
    T_compat(0, 0) = scale_factor;
    T_compat(1, 1) = scale_factor;
    T_compat(2, 2) = scale_factor;
    
    // Test segment
    Eigen::Vector3d start(0.0, 0.0, 0.0);
    Eigen::Vector3d end(10.0, 0.0, 0.0);
    
    double length_pre = (end - start).norm();
    double length_post = BeltTransforms::compute_segment_length_post_transform(start, end, T_compat);
    
    std::cout << "  Pre-transform length: " << length_pre << " mm" << std::endl;
    std::cout << "  Post-transform length: " << length_post << " mm" << std::endl;
    std::cout << "  Scale factor: " << (length_post / length_pre) << std::endl;
    
    // Length should be scaled by sqrt(2)
    double expected_length = length_pre * scale_factor;
    double length_error = std::abs(length_post - expected_length);
    
    assert(length_error < 1e-6 && "Length should be scaled by sqrt(2)");
    std::cout << "✓ Non-orthonormal transform changes segment length" << std::endl;
    
    // Verify transform is detected as non-orthonormal
    bool is_orthonormal = BeltTransforms::is_transform_orthonormal(T_compat);
    assert(!is_orthonormal && "Scaled transform should be non-orthonormal");
    std::cout << "✓ Non-orthonormal transform correctly detected" << std::endl;
}

void test_virtual_belt_frame_utilities() {
    std::cout << "\n=== Virtual Belt Frame Utilities ===" << std::endl;
    
    // Test belt plane detection
    PointV on_belt(10.0, 20.0, 0.0);
    PointV above_belt(10.0, 20.0, 5.0);
    PointV near_belt(10.0, 20.0, 0.01);
    
    assert(VirtualBeltFrame::is_on_belt_plane(on_belt) && "Point at Zv=0 should be on belt");
    assert(!VirtualBeltFrame::is_above_belt_plane(on_belt) && "Point at Zv=0 should not be above belt");
    assert(VirtualBeltFrame::is_above_belt_plane(above_belt) && "Point at Zv=5 should be above belt");
    assert(VirtualBeltFrame::is_on_belt_plane(near_belt) && "Point at Zv=0.01 should be on belt (within epsilon)");
    
    std::cout << "✓ Belt plane detection works correctly" << std::endl;
    
    // Test projection
    PointV projected = VirtualBeltFrame::project_to_belt_plane(above_belt);
    assert(std::abs(projected.z()) < 1e-6 && "Projected point should have Zv=0");
    assert(std::abs(projected.x() - above_belt.x()) < 1e-6 && "X coordinate should be preserved");
    assert(std::abs(projected.y() - above_belt.y()) < 1e-6 && "Y coordinate should be preserved");
    
    std::cout << "✓ Belt plane projection works correctly" << std::endl;
}

int main() {
    std::cout << "==================================================" << std::endl;
    std::cout << "Belt Printer T01 Unit Tests" << std::endl;
    std::cout << "==================================================" << std::endl;
    
    try {
        test_UT01_M_VF_VALIDATION();
        test_UT02_NATIVE_LENGTH_INVARIANCE();
        test_UT03_COMPAT_EXTRUSION_RECALC();
        test_virtual_belt_frame_utilities();
        
        std::cout << "\n==================================================" << std::endl;
        std::cout << "✓ ALL TESTS PASSED" << std::endl;
        std::cout << "==================================================" << std::endl;
        
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n✗ TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
}
