#include "../src/libslic3r/BeltPrinter/BeltPlacement.hpp"
#include "../src/libslic3r/BeltPrinter/MachineProfile.hpp"
#include <iostream>
#include <cassert>
#include <cmath>

using namespace Slic3r::BeltPrinter;

void test_drop_to_belt() {
    std::cout << "\n=== Drop to Belt Test ===" << std::endl;
    
    // Mesh with min_Zv = 5.0 mm (floating above belt)
    BoundingBoxV bbox(
        PointV(0.0, 0.0, 5.0),   // min
        PointV(20.0, 30.0, 25.0) // max
    );
    
    std::cout << "  Initial bbox: Zv=[" << bbox.min_Zv() << ", " << bbox.max_Zv() << "]" << std::endl;
    
    // Drop to belt (air_gap = 0)
    VectorV translation = BeltPlacement::compute_drop_to_belt_translation(bbox, 0.0);
    
    std::cout << "  Translation: " << translation.transpose() << std::endl;
    assert(std::abs(translation.z() + 5.0) < 1e-6 && "Should translate down by 5mm");
    
    // Apply translation
    bbox.min_point += translation;
    bbox.max_point += translation;
    
    std::cout << "  After drop: Zv=[" << bbox.min_Zv() << ", " << bbox.max_Zv() << "]" << std::endl;
    assert(std::abs(bbox.min_Zv()) < 1e-6 && "min_Zv should be 0");
    assert(std::abs(bbox.max_Zv() - 20.0) < 1e-6 && "max_Zv should be 20");
    
    std::cout << "✓ Drop to belt works correctly" << std::endl;
}

void test_belt_offset() {
    std::cout << "\n=== Belt Offset Test ===" << std::endl;
    
    BoundingBoxV bbox(
        PointV(0.0, 0.0, 0.0),
        PointV(20.0, 30.0, 20.0)
    );
    
    std::cout << "  Initial bbox: Yv=[" << bbox.min_Yv() << ", " << bbox.max_Yv() << "]" << std::endl;
    
    // Apply belt offset of 10mm
    VectorV translation = BeltPlacement::compute_belt_offset_translation(10.0);
    
    std::cout << "  Translation: " << translation.transpose() << std::endl;
    assert(std::abs(translation.y() - 10.0) < 1e-6 && "Should translate along Yv by 10mm");
    
    bbox.min_point += translation;
    bbox.max_point += translation;
    
    std::cout << "  After offset: Yv=[" << bbox.min_Yv() << ", " << bbox.max_Yv() << "]" << std::endl;
    assert(std::abs(bbox.min_Yv() - 10.0) < 1e-6 && "min_Yv should be 10");
    assert(std::abs(bbox.max_Yv() - 40.0) < 1e-6 && "max_Yv should be 40");
    
    std::cout << "✓ Belt offset works correctly" << std::endl;
}

void test_air_start_warning() {
    std::cout << "\n=== AIR_START Warning Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    PlacementSettings settings;
    settings.raft_enabled = false;
    
    // Mesh floating 2mm above belt
    BoundingBoxV bbox(
        PointV(10.0, 10.0, 2.0),
        PointV(30.0, 40.0, 22.0)
    );
    
    auto warnings = BeltPlacement::validate_printable_region(bbox, profile, settings);
    
    bool found_air_start = false;
    for (const auto& warning : warnings) {
        std::cout << "  Warning: " << warning.message << std::endl;
        if (warning.type == PlacementWarningType::AIR_START) {
            found_air_start = true;
        }
    }
    
    assert(found_air_start && "Should warn about air start");
    std::cout << "✓ AIR_START warning detected correctly" << std::endl;
    
    // With raft enabled, no warning
    settings.raft_enabled = true;
    warnings = BeltPlacement::validate_printable_region(bbox, profile, settings);
    
    found_air_start = false;
    for (const auto& warning : warnings) {
        if (warning.type == PlacementWarningType::AIR_START) {
            found_air_start = true;
        }
    }
    
    assert(!found_air_start && "Should not warn with raft enabled");
    std::cout << "✓ No AIR_START warning with raft enabled" << std::endl;
}

void test_out_of_printable_strip_warning() {
    std::cout << "\n=== OUT_OF_PRINTABLE_STRIP Warning Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    PlacementSettings settings;
    
    // Mesh starting before printable region (Yv < 0)
    BoundingBoxV bbox(
        PointV(10.0, -10.0, 0.0),
        PointV(30.0, 20.0, 20.0)
    );
    
    auto warnings = BeltPlacement::validate_printable_region(bbox, profile, settings);
    
    bool found_out_of_strip = false;
    for (const auto& warning : warnings) {
        std::cout << "  Warning: " << warning.message << std::endl;
        if (warning.type == PlacementWarningType::OUT_OF_PRINTABLE_STRIP) {
            found_out_of_strip = true;
        }
    }
    
    assert(found_out_of_strip && "Should warn about out of printable strip");
    std::cout << "✓ OUT_OF_PRINTABLE_STRIP warning detected correctly" << std::endl;
}

void test_auto_shift() {
    std::cout << "\n=== Auto-Shift Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    
    // Mesh starting at Yv = -10 (before printable region at 0)
    BoundingBoxV bbox(
        PointV(10.0, -10.0, 0.0),
        PointV(30.0, 20.0, 20.0)
    );
    
    std::cout << "  Initial Yv range: [" << bbox.min_Yv() << ", " << bbox.max_Yv() << "]" << std::endl;
    
    double shift = BeltPlacement::compute_auto_shift_Yv(bbox, profile);
    
    std::cout << "  Computed shift: " << shift << " mm" << std::endl;
    assert(std::abs(shift - 10.0) < 1e-6 && "Should shift forward by 10mm");
    
    // Apply shift
    bbox.min_point.y() += shift;
    bbox.max_point.y() += shift;
    
    std::cout << "  After shift: Yv range: [" << bbox.min_Yv() << ", " << bbox.max_Yv() << "]" << std::endl;
    assert(std::abs(bbox.min_Yv() - 0.0) < 1e-6 && "Should start at printable region");
    
    std::cout << "✓ Auto-shift works correctly" << std::endl;
}

void test_build_volume_check() {
    std::cout << "\n=== Build Volume Check Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    
    // Valid mesh within build volume
    BoundingBoxV valid_bbox(
        PointV(10.0, 10.0, 0.0),
        PointV(100.0, 100.0, 100.0)
    );
    
    bool is_valid = BeltPlacement::is_within_build_volume(valid_bbox, profile);
    assert(is_valid && "Valid bbox should be within build volume");
    std::cout << "✓ Valid bbox accepted" << std::endl;
    
    // Invalid mesh (exceeds Xv_max)
    BoundingBoxV invalid_bbox_x(
        PointV(10.0, 10.0, 0.0),
        PointV(250.0, 100.0, 100.0)  // Xv_max is 200
    );
    
    is_valid = BeltPlacement::is_within_build_volume(invalid_bbox_x, profile);
    assert(!is_valid && "Bbox exceeding Xv_max should be rejected");
    std::cout << "✓ Bbox exceeding Xv_max rejected" << std::endl;
    
    // Invalid mesh (exceeds Zv_max)
    BoundingBoxV invalid_bbox_z(
        PointV(10.0, 10.0, 0.0),
        PointV(100.0, 100.0, 250.0)  // Zv_max is 200
    );
    
    is_valid = BeltPlacement::is_within_build_volume(invalid_bbox_z, profile);
    assert(!is_valid && "Bbox exceeding Zv_max should be rejected");
    std::cout << "✓ Bbox exceeding Zv_max rejected" << std::endl;
}

int main() {
    std::cout << "==================================================" << std::endl;
    std::cout << "Belt Printer T02 Placement Tests" << std::endl;
    std::cout << "==================================================" << std::endl;
    
    try {
        test_drop_to_belt();
        test_belt_offset();
        test_air_start_warning();
        test_out_of_printable_strip_warning();
        test_auto_shift();
        test_build_volume_check();
        
        std::cout << "\n==================================================" << std::endl;
        std::cout << "✓ ALL PLACEMENT TESTS PASSED" << std::endl;
        std::cout << "==================================================" << std::endl;
        
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n✗ TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
}
