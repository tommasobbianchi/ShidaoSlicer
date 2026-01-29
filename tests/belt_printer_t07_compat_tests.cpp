#include "../src/libslic3r/BeltPrinter/CompatibilityMode.hpp"
#include <iostream>
#include <cassert>
#include <cmath>

using namespace Slic3r::BeltPrinter;

void test_identity_transform() {
    std::cout << "\n=== Identity Transform Test ===" << std::endl;
    
    CompatibilityTransform compat = CompatibilityTransform::create_identity();
    
    assert(compat.is_orthonormal && "Identity should be orthonormal");
    assert(!compat.requires_extrusion_recalc && "Identity should not require recalc");
    
    Eigen::Vector3d point(10, 20, 30);
    Eigen::Vector3d transformed = CompatibilityMode::apply_transform(point, compat);
    
    std::cout << "  Original: " << point.transpose() << std::endl;
    std::cout << "  Transformed: " << transformed.transpose() << std::endl;
    
    assert((point - transformed).norm() < 1e-6 && "Identity should not change point");
    
    std::cout << "✓ Identity transform correct" << std::endl;
}

void test_orthonormal_detection() {
    std::cout << "\n=== Orthonormal Detection Test ===" << std::endl;
    
    // Test 1: Pure rotation (orthonormal)
    Eigen::Matrix4d rotation = Eigen::Matrix4d::Identity();
    double angle = M_PI / 4;  // 45 degrees
    rotation(0, 0) = std::cos(angle);
    rotation(0, 1) = -std::sin(angle);
    rotation(1, 0) = std::sin(angle);
    rotation(1, 1) = std::cos(angle);
    
    bool is_ortho = CompatibilityMode::is_orthonormal(rotation);
    std::cout << "  Rotation matrix: " << (is_ortho ? "orthonormal" : "non-orthonormal") << std::endl;
    assert(is_ortho && "Rotation should be orthonormal");
    
    // Test 2: Uniform scaling (non-orthonormal)
    Eigen::Matrix4d scaling = Eigen::Matrix4d::Identity();
    scaling(0, 0) = 2.0;
    scaling(1, 1) = 2.0;
    scaling(2, 2) = 2.0;
    
    is_ortho = CompatibilityMode::is_orthonormal(scaling);
    std::cout << "  Scaling matrix: " << (is_ortho ? "orthonormal" : "non-orthonormal") << std::endl;
    assert(!is_ortho && "Scaling should be non-orthonormal");
    
    // Test 3: Shear (non-orthonormal)
    Eigen::Matrix4d shear = Eigen::Matrix4d::Identity();
    shear(1, 2) = -1.0;  // Y = Y - Z (shear)
    
    is_ortho = CompatibilityMode::is_orthonormal(shear);
    std::cout << "  Shear matrix: " << (is_ortho ? "orthonormal" : "non-orthonormal") << std::endl;
    assert(!is_ortho && "Shear should be non-orthonormal");
    
    std::cout << "✓ Orthonormal detection correct" << std::endl;
}

void test_extrusion_recalculation() {
    std::cout << "\n=== Extrusion Recalculation Test ===" << std::endl;
    
    // Original segment: 10mm long, 0.5mm extrusion
    double extrusion_pre = 0.5;
    double length_pre = 10.0;
    
    // After 2x scaling: 20mm long
    double length_post = 20.0;
    
    double extrusion_post = CompatibilityMode::recalculate_extrusion(
        extrusion_pre, length_pre, length_post);
    
    std::cout << "  Pre-transform: " << length_pre << "mm, E=" << extrusion_pre << std::endl;
    std::cout << "  Post-transform: " << length_post << "mm, E=" << extrusion_post << std::endl;
    
    // Should be 0.5 * (20/10) = 1.0
    assert(std::abs(extrusion_post - 1.0) < 1e-6 && "Extrusion should double");
    
    std::cout << "✓ Extrusion recalculation correct" << std::endl;
}

void test_segment_transform_with_scaling() {
    std::cout << "\n=== Segment Transform with Scaling Test ===" << std::endl;
    
    // Create 2x uniform scaling transform
    Eigen::Matrix4d T = Eigen::Matrix4d::Identity();
    T(0, 0) = 2.0;
    T(1, 1) = 2.0;
    T(2, 2) = 2.0;
    
    CompatibilityTransform compat = CompatibilityTransform::create_from_matrix(T);
    
    std::cout << "  Is orthonormal: " << compat.is_orthonormal << std::endl;
    std::cout << "  Requires extrusion recalc: " << compat.requires_extrusion_recalc << std::endl;
    
    assert(!compat.is_orthonormal && "2x scaling should be non-orthonormal");
    assert(compat.requires_extrusion_recalc && "Should require extrusion recalc");
    
    // Apply to segment
    Eigen::Vector3d start(0, 0, 0);
    Eigen::Vector3d end(10, 0, 0);
    double extrusion = 0.5;
    
    CompatibilitySegment segment = CompatibilityMode::apply_to_segment(
        start, end, extrusion, compat);
    
    std::cout << "  Pre-transform length: " << segment.length_pre << "mm" << std::endl;
    std::cout << "  Post-transform length: " << segment.length_post << "mm" << std::endl;
    std::cout << "  Pre-transform extrusion: " << segment.extrusion_pre << std::endl;
    std::cout << "  Post-transform extrusion: " << segment.extrusion_post << std::endl;
    
    assert(std::abs(segment.length_pre - 10.0) < 1e-6 && "Pre length should be 10mm");
    assert(std::abs(segment.length_post - 20.0) < 1e-6 && "Post length should be 20mm");
    assert(std::abs(segment.extrusion_post - 1.0) < 1e-6 && "Extrusion should be recalculated");
    
    std::cout << "✓ Segment transform with scaling correct" << std::endl;
}

void test_legacy_shear_transform() {
    std::cout << "\n=== Legacy Shear Transform Test ===" << std::endl;
    
    // Create legacy shear for 45° belt printer (Y-axis belt)
    CompatibilityTransform compat = CompatibilityMode::create_legacy_shear_transform(45.0, 1);
    
    std::cout << "  Is orthonormal: " << compat.is_orthonormal << std::endl;
    std::cout << "  Output frame: " << compat.output_frame << std::endl;
    
    // Shear transform is NOT orthonormal (it includes shear)
    assert(!compat.is_orthonormal && "Shear should be non-orthonormal");
    assert(compat.output_frame == "F" && "Should output to firmware frame");
    
    // Test shear: Point at (0, 10, 10) should become (0, 10-10*tan(45°), 10) = (0, 0, 10)
    Eigen::Vector3d point(0, 10, 10);
    Eigen::Vector3d transformed = CompatibilityMode::apply_transform(point, compat);
    
    std::cout << "  Original: " << point.transpose() << std::endl;
    std::cout << "  Transformed: " << transformed.transpose() << std::endl;
    
    // Y should be approximately 0 (10 - 10*1.0)
    assert(std::abs(transformed.y() - 0.0) < 0.1 && "Y should be sheared");
    assert(std::abs(transformed.z() - 10.0) < 1e-6 && "Z should be unchanged");
    
    std::cout << "✓ Legacy shear transform correct" << std::endl;
}

void test_scale_factor_computation() {
    std::cout << "\n=== Scale Factor Computation Test ===" << std::endl;
    
    // Uniform 2x scaling
    Eigen::Matrix4d T_uniform = Eigen::Matrix4d::Identity();
    T_uniform(0, 0) = 2.0;
    T_uniform(1, 1) = 2.0;
    T_uniform(2, 2) = 2.0;
    
    double scale = CompatibilityMode::compute_scale_factor(T_uniform);
    std::cout << "  Uniform 2x scaling: " << scale << std::endl;
    assert(std::abs(scale - 2.0) < 0.1 && "Should be approximately 2.0");
    
    // Identity (scale = 1)
    Eigen::Matrix4d T_identity = Eigen::Matrix4d::Identity();
    scale = CompatibilityMode::compute_scale_factor(T_identity);
    std::cout << "  Identity: " << scale << std::endl;
    assert(std::abs(scale - 1.0) < 1e-6 && "Should be 1.0");
    
    std::cout << "✓ Scale factor computation correct" << std::endl;
}

void test_warning_message_generation() {
    std::cout << "\n=== Warning Message Generation Test ===" << std::endl;
    
    // Non-orthonormal transform
    Eigen::Matrix4d T = Eigen::Matrix4d::Identity();
    T(0, 0) = 1.5;  // Scaling
    
    CompatibilityTransform compat = CompatibilityTransform::create_from_matrix(T);
    
    std::string warning = CompatibilityMode::generate_warning_message(compat);
    
    if (!warning.empty()) {
        std::cout << warning << std::endl;
        assert(warning.find("WARNING") != std::string::npos && "Should contain warning");
        assert(warning.find("recalculated") != std::string::npos && "Should mention recalculation");
    }
    
    std::cout << "✓ Warning message generation correct" << std::endl;
}

int main() {
    std::cout << "==================================================" << std::endl;
    std::cout << "Belt Printer T07 Compatibility Mode Tests" << std::endl;
    std::cout << "==================================================" << std::endl;
    
    try {
        test_identity_transform();
        test_orthonormal_detection();
        test_extrusion_recalculation();
        test_segment_transform_with_scaling();
        test_legacy_shear_transform();
        test_scale_factor_computation();
        test_warning_message_generation();
        
        std::cout << "\n==================================================" << std::endl;
        std::cout << "✓ ALL COMPATIBILITY MODE TESTS PASSED" << std::endl;
        std::cout << "==================================================" << std::endl;
        
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n✗ TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
}
