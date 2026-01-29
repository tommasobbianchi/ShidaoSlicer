#include "../src/libslic3r/BeltPrinter/GCodeEmitter.hpp"
#include "../src/libslic3r/BeltPrinter/MachineProfile.hpp"
#include <iostream>
#include <cassert>
#include <string>

using namespace Slic3r::BeltPrinter;

void test_coordinate_formatting() {
    std::cout << "\n=== Coordinate Formatting Test ===" << std::endl;
    
    std::string coord1 = GCodeEmitter::format_coordinate(10.5, 3);
    std::cout << "  10.5 (3 decimals): " << coord1 << std::endl;
    assert(coord1 == "10.500" && "Should format to 3 decimals");
    
    std::string coord2 = GCodeEmitter::format_coordinate(0.12345, 5);
    std::cout << "  0.12345 (5 decimals): " << coord2 << std::endl;
    assert(coord2 == "0.12345" && "Should format to 5 decimals");
    
    std::cout << "✓ Coordinate formatting correct" << std::endl;
}

void test_feedrate_formatting() {
    std::cout << "\n=== Feedrate Formatting Test ===" << std::endl;
    
    // 50 mm/s = 3000 mm/min
    std::string feedrate = GCodeEmitter::format_feedrate(50.0);
    std::cout << "  50 mm/s: " << feedrate << std::endl;
    assert(feedrate == "F3000" && "Should convert to mm/min");
    
    std::cout << "✓ Feedrate formatting correct" << std::endl;
}

void test_position_emission_CR30() {
    std::cout << "\n=== Position Emission (CR30) Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    
    // CR30 mapping: Xv→X, Yv→Z, Zv→Y
    // Point in V: (10, 20, 5)
    // Should map to F: (10, 5, 20)
    PointV point_V(10.0, 20.0, 5.0);
    
    std::string position = GCodeEmitter::emit_position(point_V, profile);
    std::cout << "  V=(10,20,5) → " << position << std::endl;
    
    // Should emit: X10.000 Y5.000 Z20.000
    assert(position.find("X10.000") != std::string::npos && "X should be 10");
    assert(position.find("Y5.000") != std::string::npos && "Y should be 5");
    assert(position.find("Z20.000") != std::string::npos && "Z should be 20");
    
    std::cout << "✓ Position emission correct for CR30" << std::endl;
}

void test_move_emission_basic() {
    std::cout << "\n=== Basic Move Emission Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    GCodeEmissionSettings settings;
    settings.use_V_to_F_mapping = true;
    settings.emit_comments = false;
    settings.apply_contact_params = false;
    
    GCodeMove move;
    move.position_V = PointV(10.0, 20.0, 5.0);
    move.extrusion_mm = 0.5;
    move.feedrate_mm_s = 50.0;  // 3000 mm/min
    
    std::string gcode = GCodeEmitter::emit_move(move, profile, settings);
    std::cout << "  " << gcode << std::endl;
    
    assert(gcode.find("G1") != std::string::npos && "Should start with G1");
    assert(gcode.find("E0.50000") != std::string::npos && "Should have extrusion");
    assert(gcode.find("F3000") != std::string::npos && "Should have feedrate");
    
    std::cout << "✓ Basic move emission correct" << std::endl;
}

void test_move_emission_with_comments() {
    std::cout << "\n=== Move Emission with Comments Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    GCodeEmissionSettings settings;
    settings.use_V_to_F_mapping = true;
    settings.emit_comments = true;
    settings.apply_contact_params = false;
    
    GCodeMove move;
    move.position_V = PointV(10.0, 20.0, 5.0);
    move.extrusion_mm = 0.5;
    move.feedrate_mm_s = 50.0;
    move.contact_class = ContactClass::BELT_CONTACT;
    
    std::string gcode = GCodeEmitter::emit_move(move, profile, settings);
    std::cout << "  " << gcode << std::endl;
    
    assert(gcode.find("; V=(") != std::string::npos && "Should have V coordinate comment");
    assert(gcode.find("BELT_CONTACT") != std::string::npos && "Should have contact class comment");
    
    std::cout << "✓ Move emission with comments correct" << std::endl;
}

void test_contact_parameter_application() {
    std::cout << "\n=== Contact Parameter Application Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    GCodeEmissionSettings settings;
    settings.use_V_to_F_mapping = true;
    settings.emit_comments = false;
    settings.apply_contact_params = true;
    
    // Set belt contact parameters: 0.5x speed, 1.2x flow
    settings.contact_settings.belt_contact_params = ContactParameterSet(0.5, 1.2, 0.0);
    
    GCodeMove move;
    move.position_V = PointV(10.0, 20.0, 0.0);  // On belt plane
    move.extrusion_mm = 1.0;
    move.feedrate_mm_s = 100.0;  // 6000 mm/min normally
    move.contact_class = ContactClass::BELT_CONTACT;
    
    std::string gcode = GCodeEmitter::emit_move(move, profile, settings);
    std::cout << "  " << gcode << std::endl;
    
    // Speed should be 0.5x: 100 * 0.5 = 50 mm/s = 3000 mm/min
    assert(gcode.find("F3000") != std::string::npos && "Speed should be halved");
    
    // Flow should be 1.2x: 1.0 * 1.2 = 1.2
    assert(gcode.find("E1.20000") != std::string::npos && "Flow should be 1.2x");
    
    std::cout << "✓ Contact parameter application correct" << std::endl;
}

void test_profile_metadata_emission() {
    std::cout << "\n=== Profile Metadata Emission Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    
    std::string metadata = GCodeEmitter::emit_profile_metadata(profile);
    std::cout << metadata << std::endl;
    
    assert(metadata.find("CR30_LIKE_EXAMPLE") != std::string::npos && 
           "Should contain machine ID");
    assert(metadata.find("45") != std::string::npos && 
           "Should contain gantry angle");
    assert(metadata.find("V→F Mapping Matrix") != std::string::npos && 
           "Should contain mapping matrix");
    
    std::cout << "✓ Profile metadata emission correct" << std::endl;
}

void test_safe_ejection_sequence() {
    std::cout << "\n=== Safe Ejection Sequence Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    
    std::string ejection = GCodeEmitter::generate_safe_ejection_sequence(
        profile, 10.0, 50.0, 5.0);
    
    std::cout << ejection << std::endl;
    
    assert(ejection.find("E-5.00000") != std::string::npos && 
           "Should retract filament");
    assert(ejection.find("G91") != std::string::npos && 
           "Should use relative positioning");
    assert(ejection.find("G90") != std::string::npos && 
           "Should return to absolute positioning");
    
    // CR30: Normal axis is Y, Belt axis is Z
    assert(ejection.find("Y10.000") != std::string::npos && 
           "Should lift along Y (normal axis)");
    assert(ejection.find("Z50.000") != std::string::npos && 
           "Should advance Z (belt axis)");
    
    std::cout << "✓ Safe ejection sequence correct" << std::endl;
}

void test_firmware_axis_letter_lookup() {
    std::cout << "\n=== Firmware Axis Letter Lookup Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    
    // CR30: Xv→X, Yv→Z, Zv→Y
    char xv_letter = GCodeEmitter::get_firmware_axis_letter(0, profile);  // Xv
    char yv_letter = GCodeEmitter::get_firmware_axis_letter(1, profile);  // Yv
    char zv_letter = GCodeEmitter::get_firmware_axis_letter(2, profile);  // Zv
    
    std::cout << "  Xv → " << xv_letter << std::endl;
    std::cout << "  Yv → " << yv_letter << std::endl;
    std::cout << "  Zv → " << zv_letter << std::endl;
    
    assert(xv_letter == 'X' && "Xv should map to X");
    assert(yv_letter == 'Z' && "Yv should map to Z");
    assert(zv_letter == 'Y' && "Zv should map to Y");
    
    std::cout << "✓ Firmware axis letter lookup correct" << std::endl;
}

int main() {
    std::cout << "==================================================" << std::endl;
    std::cout << "Belt Printer T06 G-code Emission Tests" << std::endl;
    std::cout << "==================================================" << std::endl;
    
    try {
        test_coordinate_formatting();
        test_feedrate_formatting();
        test_position_emission_CR30();
        test_move_emission_basic();
        test_move_emission_with_comments();
        test_contact_parameter_application();
        test_profile_metadata_emission();
        test_safe_ejection_sequence();
        test_firmware_axis_letter_lookup();
        
        std::cout << "\n==================================================" << std::endl;
        std::cout << "✓ ALL G-CODE EMISSION TESTS PASSED" << std::endl;
        std::cout << "==================================================" << std::endl;
        
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n✗ TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
}
