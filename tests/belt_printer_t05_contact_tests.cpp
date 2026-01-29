#include "../src/libslic3r/BeltPrinter/BeltContactClassifier.hpp"
#include "../src/libslic3r/BeltPrinter/BeltRaft.hpp"
#include <iostream>
#include <cassert>
#include <cmath>

using namespace Slic3r::BeltPrinter;

void test_belt_plane_detection() {
    std::cout << "\n=== Belt Plane Detection Test ===" << std::endl;
    
    // Point exactly on belt plane
    assert(BeltContactClassifier::is_on_belt_plane(0.0, 0.05) && 
           "Zv=0 should be on belt plane");
    
    // Point within epsilon
    assert(BeltContactClassifier::is_on_belt_plane(0.03, 0.05) && 
           "Zv=0.03 should be on belt plane (within epsilon)");
    
    // Point outside epsilon
    assert(!BeltContactClassifier::is_on_belt_plane(0.1, 0.05) && 
           "Zv=0.1 should NOT be on belt plane");
    
    std::cout << "  ✓ Zv=0.0: on belt plane" << std::endl;
    std::cout << "  ✓ Zv=0.03: on belt plane (within epsilon)" << std::endl;
    std::cout << "  ✓ Zv=0.1: NOT on belt plane" << std::endl;
    std::cout << "✓ Belt plane detection correct" << std::endl;
}

void test_raft_surface_detection() {
    std::cout << "\n=== Raft Surface Detection Test ===" << std::endl;
    
    double raft_surface = 0.6;  // 0.6mm raft
    
    // Point exactly on raft surface
    assert(BeltContactClassifier::is_on_raft_surface(0.6, raft_surface, 0.05) && 
           "Zv=0.6 should be on raft surface");
    
    // Point within epsilon
    assert(BeltContactClassifier::is_on_raft_surface(0.58, raft_surface, 0.05) && 
           "Zv=0.58 should be on raft surface (within epsilon)");
    
    // Point outside epsilon
    assert(!BeltContactClassifier::is_on_raft_surface(0.7, raft_surface, 0.05) && 
           "Zv=0.7 should NOT be on raft surface");
    
    std::cout << "  ✓ Zv=0.6: on raft surface" << std::endl;
    std::cout << "  ✓ Zv=0.58: on raft surface (within epsilon)" << std::endl;
    std::cout << "  ✓ Zv=0.7: NOT on raft surface" << std::endl;
    std::cout << "✓ Raft surface detection correct" << std::endl;
}

void test_segment_classification_no_raft() {
    std::cout << "\n=== Segment Classification (No Raft) Test ===" << std::endl;
    
    ContactClassificationSettings settings;
    settings.raft_enabled = false;
    settings.epsilon_mm = 0.05;
    
    // First layer segment (on belt plane)
    ToolpathSegment first_layer(
        PointV(10.0, 20.0, 0.0),
        PointV(15.0, 25.0, 0.0)
    );
    
    ContactClass class1 = BeltContactClassifier::classify_segment(first_layer, settings);
    std::cout << "  First layer (Zv=0): " 
              << (class1 == ContactClass::BELT_CONTACT ? "BELT_CONTACT" : "NON_CONTACT") 
              << std::endl;
    assert(class1 == ContactClass::BELT_CONTACT && "First layer should be BELT_CONTACT");
    
    // Second layer segment (on previous plastic)
    ToolpathSegment second_layer(
        PointV(10.0, 20.0, 0.2),
        PointV(15.0, 25.0, 0.2)
    );
    
    ContactClass class2 = BeltContactClassifier::classify_segment(second_layer, settings);
    std::cout << "  Second layer (Zv=0.2): " 
              << (class2 == ContactClass::BELT_CONTACT ? "BELT_CONTACT" : "NON_CONTACT") 
              << std::endl;
    assert(class2 == ContactClass::NON_CONTACT && "Second layer should be NON_CONTACT");
    
    // Segment near belt (within epsilon)
    ToolpathSegment near_belt(
        PointV(10.0, 20.0, 0.03),
        PointV(15.0, 25.0, 0.03)
    );
    
    ContactClass class3 = BeltContactClassifier::classify_segment(near_belt, settings);
    std::cout << "  Near belt (Zv=0.03): " 
              << (class3 == ContactClass::BELT_CONTACT ? "BELT_CONTACT" : "NON_CONTACT") 
              << std::endl;
    assert(class3 == ContactClass::BELT_CONTACT && "Near belt should be BELT_CONTACT");
    
    std::cout << "✓ Segment classification (no raft) correct" << std::endl;
}

void test_segment_classification_with_raft() {
    std::cout << "\n=== Segment Classification (With Raft) Test ===" << std::endl;
    
    ContactClassificationSettings settings;
    settings.raft_enabled = true;
    settings.raft_surface_Zv = 0.6;
    settings.epsilon_mm = 0.05;
    
    // Raft layer (on belt plane)
    ToolpathSegment raft_layer(
        PointV(10.0, 20.0, 0.0),
        PointV(15.0, 25.0, 0.0)
    );
    
    ContactClass class1 = BeltContactClassifier::classify_segment(raft_layer, settings);
    std::cout << "  Raft layer (Zv=0): " 
              << (class1 == ContactClass::BELT_CONTACT ? "BELT_CONTACT" : "NON_CONTACT") 
              << std::endl;
    assert(class1 == ContactClass::BELT_CONTACT && "Raft layer should be BELT_CONTACT");
    
    // First model layer (on raft surface)
    ToolpathSegment first_model_layer(
        PointV(10.0, 20.0, 0.6),
        PointV(15.0, 25.0, 0.6)
    );
    
    ContactClass class2 = BeltContactClassifier::classify_segment(first_model_layer, settings);
    std::cout << "  First model layer (Zv=0.6, on raft): " 
              << (class2 == ContactClass::BELT_CONTACT ? "BELT_CONTACT" : "NON_CONTACT") 
              << std::endl;
    assert(class2 == ContactClass::BELT_CONTACT && "First model layer should be BELT_CONTACT");
    
    // Second model layer (on previous plastic)
    ToolpathSegment second_model_layer(
        PointV(10.0, 20.0, 0.8),
        PointV(15.0, 25.0, 0.8)
    );
    
    ContactClass class3 = BeltContactClassifier::classify_segment(second_model_layer, settings);
    std::cout << "  Second model layer (Zv=0.8): " 
              << (class3 == ContactClass::BELT_CONTACT ? "BELT_CONTACT" : "NON_CONTACT") 
              << std::endl;
    assert(class3 == ContactClass::NON_CONTACT && "Second model layer should be NON_CONTACT");
    
    std::cout << "✓ Segment classification (with raft) correct" << std::endl;
}

void test_parameter_sets() {
    std::cout << "\n=== Parameter Sets Test ===" << std::endl;
    
    ContactClassificationSettings settings;
    settings.belt_contact_params = ContactParameterSet(0.5, 1.2, 0.0);
    settings.normal_params = ContactParameterSet(1.0, 1.0, 1.0);
    
    // Get belt contact parameters
    ContactParameterSet belt_params = BeltContactClassifier::get_parameter_set(
        ContactClass::BELT_CONTACT, settings);
    
    std::cout << "  BELT_CONTACT params: speed=" << belt_params.speed_multiplier 
              << ", flow=" << belt_params.flow_multiplier 
              << ", fan=" << belt_params.fan_multiplier << std::endl;
    
    assert(std::abs(belt_params.speed_multiplier - 0.5) < 1e-6 && "Speed should be 0.5x");
    assert(std::abs(belt_params.flow_multiplier - 1.2) < 1e-6 && "Flow should be 1.2x");
    assert(std::abs(belt_params.fan_multiplier - 0.0) < 1e-6 && "Fan should be 0.0x");
    
    // Get normal parameters
    ContactParameterSet normal_params = BeltContactClassifier::get_parameter_set(
        ContactClass::NON_CONTACT, settings);
    
    std::cout << "  NON_CONTACT params: speed=" << normal_params.speed_multiplier 
              << ", flow=" << normal_params.flow_multiplier 
              << ", fan=" << normal_params.fan_multiplier << std::endl;
    
    assert(std::abs(normal_params.speed_multiplier - 1.0) < 1e-6 && "Speed should be 1.0x");
    assert(std::abs(normal_params.flow_multiplier - 1.0) < 1e-6 && "Flow should be 1.0x");
    assert(std::abs(normal_params.fan_multiplier - 1.0) < 1e-6 && "Fan should be 1.0x");
    
    std::cout << "✓ Parameter sets correct" << std::endl;
}

void test_batch_classification() {
    std::cout << "\n=== Batch Classification Test ===" << std::endl;
    
    ContactClassificationSettings settings;
    settings.raft_enabled = false;
    settings.epsilon_mm = 0.05;
    
    // Create multiple segments
    std::vector<ToolpathSegment> segments;
    segments.push_back(ToolpathSegment(PointV(0,0,0.0), PointV(10,0,0.0)));  // BELT_CONTACT
    segments.push_back(ToolpathSegment(PointV(10,0,0.0), PointV(20,0,0.0))); // BELT_CONTACT
    segments.push_back(ToolpathSegment(PointV(0,0,0.2), PointV(10,0,0.2)));  // NON_CONTACT
    segments.push_back(ToolpathSegment(PointV(10,0,0.2), PointV(20,0,0.2))); // NON_CONTACT
    segments.push_back(ToolpathSegment(PointV(0,0,0.4), PointV(10,0,0.4)));  // NON_CONTACT
    
    // Classify all segments
    BeltContactClassifier::classify_segments(segments, settings);
    
    // Count by class
    auto [belt_count, non_count] = BeltContactClassifier::count_by_class(segments);
    
    std::cout << "  Total segments: " << segments.size() << std::endl;
    std::cout << "  BELT_CONTACT: " << belt_count << std::endl;
    std::cout << "  NON_CONTACT: " << non_count << std::endl;
    
    assert(belt_count == 2 && "Should have 2 BELT_CONTACT segments");
    assert(non_count == 3 && "Should have 3 NON_CONTACT segments");
    
    std::cout << "✓ Batch classification correct" << std::endl;
}

void test_settings_from_raft() {
    std::cout << "\n=== Settings from Raft Test ===" << std::endl;
    
    RaftGeometry raft;
    raft.raft_surface_Zv = 0.6;
    
    ContactClassificationSettings settings = 
        BeltContactClassifier::create_settings_from_raft(raft, true);
    
    std::cout << "  Raft enabled: " << settings.raft_enabled << std::endl;
    std::cout << "  Raft surface Zv: " << settings.raft_surface_Zv << " mm" << std::endl;
    std::cout << "  Belt contact speed: " << settings.belt_contact_params.speed_multiplier << "x" << std::endl;
    std::cout << "  Belt contact flow: " << settings.belt_contact_params.flow_multiplier << "x" << std::endl;
    std::cout << "  Belt contact fan: " << settings.belt_contact_params.fan_multiplier << "x" << std::endl;
    
    assert(settings.raft_enabled && "Raft should be enabled");
    assert(std::abs(settings.raft_surface_Zv - 0.6) < 1e-6 && "Raft surface should be 0.6mm");
    assert(std::abs(settings.belt_contact_params.speed_multiplier - 0.5) < 1e-6 && 
           "Belt contact speed should be 0.5x");
    
    std::cout << "✓ Settings from raft correct" << std::endl;
}

int main() {
    std::cout << "==================================================" << std::endl;
    std::cout << "Belt Printer T05 Contact Classification Tests" << std::endl;
    std::cout << "==================================================" << std::endl;
    
    try {
        test_belt_plane_detection();
        test_raft_surface_detection();
        test_segment_classification_no_raft();
        test_segment_classification_with_raft();
        test_parameter_sets();
        test_batch_classification();
        test_settings_from_raft();
        
        std::cout << "\n==================================================" << std::endl;
        std::cout << "✓ ALL CONTACT CLASSIFICATION TESTS PASSED" << std::endl;
        std::cout << "==================================================" << std::endl;
        
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n✗ TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
}
