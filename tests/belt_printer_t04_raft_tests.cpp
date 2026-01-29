#include "../src/libslic3r/BeltPrinter/BeltRaft.hpp"
#include "../src/libslic3r/BeltPrinter/MachineProfile.hpp"
#include <iostream>
#include <cassert>
#include <cmath>

using namespace Slic3r::BeltPrinter;

void test_raft_generation_basic() {
    std::cout << "\n=== Basic Raft Generation Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    
    // Simple rectangular model footprint: 20x30mm at origin
    Polygon2D model_footprint = BeltRaft::create_rectangle(0, 20, 0, 30);
    
    RaftSettings settings;
    settings.enabled = true;
    settings.raft_offset_mm = 3.0;
    settings.lead_in_length_mm = 10.0;
    settings.raft_thickness_mm = 0.6;
    settings.raft_layers = 3;
    
    RaftGeometry raft = BeltRaft::generate_raft_geometry(
        model_footprint, profile, settings);
    
    std::cout << "  Model footprint: [0,20] x [0,30]" << std::endl;
    std::cout << "  Raft Yv range: [" << raft.min_Yv << ", " << raft.max_Yv << "]" << std::endl;
    std::cout << "  Raft surface Zv: " << raft.raft_surface_Zv << " mm" << std::endl;
    std::cout << "  Raft layers: " << raft.layer_heights_Zv.size() << std::endl;
    
    // Raft is clipped to printable region (starts at 0 for CR30 profile)
    assert(raft.min_Yv >= 0 && "Raft should be clipped to printable region");
    assert(raft.max_Yv > 30 && "Raft should extend beyond model");
    assert(std::abs(raft.raft_surface_Zv - 0.6) < 1e-6 && "Raft surface should be at 0.6mm");
    assert(raft.layer_heights_Zv.size() == 3 && "Should have 3 raft layers");
    
    std::cout << "✓ Basic raft generation correct" << std::endl;
}

void test_upstream_extension() {
    std::cout << "\n=== Upstream Extension Test ===" << std::endl;
    
    // Rectangle at [10,30] x [20,40]
    Polygon2D rect = BeltRaft::create_rectangle(10, 30, 20, 40);
    
    std::cout << "  Original Y range: [20, 40]" << std::endl;
    
    // Extend upstream by 15mm (belt_positive = +1, so upstream is -Y)
    Polygon2D extended = BeltRaft::extend_upstream(rect, 15.0, 1);
    
    auto bbox = BeltRaft::compute_bbox_2d(extended);
    double min_y = bbox[2];
    double max_y = bbox[3];
    
    std::cout << "  Extended Y range: [" << min_y << ", " << max_y << "]" << std::endl;
    
    // Should extend to 20 - 15 = 5
    assert(std::abs(min_y - 5.0) < 1.0 && "Should extend upstream to ~5");
    assert(std::abs(max_y - 40.0) < 1.0 && "Max Y should remain ~40");
    
    std::cout << "✓ Upstream extension correct" << std::endl;
}

void test_polygon_expansion() {
    std::cout << "\n=== Polygon Expansion Test ===" << std::endl;
    
    // Small rectangle: [10,20] x [10,20]
    Polygon2D rect = BeltRaft::create_rectangle(10, 20, 10, 20);
    
    auto bbox_orig = BeltRaft::compute_bbox_2d(rect);
    std::cout << "  Original bbox: [" << bbox_orig[0] << "," << bbox_orig[1] 
              << "] x [" << bbox_orig[2] << "," << bbox_orig[3] << "]" << std::endl;
    
    // Expand by 5mm
    Polygon2D expanded = BeltRaft::expand_polygon(rect, 5.0);
    
    auto bbox_exp = BeltRaft::compute_bbox_2d(expanded);
    std::cout << "  Expanded bbox: [" << bbox_exp[0] << "," << bbox_exp[1] 
              << "] x [" << bbox_exp[2] << "," << bbox_exp[3] << "]" << std::endl;
    
    // Should be approximately [5,25] x [5,25]
    assert(bbox_exp[0] < bbox_orig[0] && "Min X should decrease");
    assert(bbox_exp[1] > bbox_orig[1] && "Max X should increase");
    assert(bbox_exp[2] < bbox_orig[2] && "Min Y should decrease");
    assert(bbox_exp[3] > bbox_orig[3] && "Max Y should increase");
    
    std::cout << "✓ Polygon expansion correct" << std::endl;
}

void test_layer_heights() {
    std::cout << "\n=== Layer Heights Test ===" << std::endl;
    
    // Generate 3 layers for 0.6mm raft
    auto heights = BeltRaft::generate_layer_heights(0.6, 3);
    
    std::cout << "  Layer heights: ";
    for (double h : heights) {
        std::cout << h << " ";
    }
    std::cout << "mm" << std::endl;
    
    assert(heights.size() == 3 && "Should have 3 layers");
    assert(std::abs(heights[0] - 0.2) < 1e-6 && "First layer at 0.2mm");
    assert(std::abs(heights[1] - 0.4) < 1e-6 && "Second layer at 0.4mm");
    assert(std::abs(heights[2] - 0.6) < 1e-6 && "Third layer at 0.6mm");
    
    std::cout << "✓ Layer heights correct" << std::endl;
}

void test_leading_edge_validation() {
    std::cout << "\n=== Leading Edge Validation Test ===" << std::endl;
    
    BeltMachineProfile profile = BeltMachineProfile::create_CR30_example();
    profile.belt_leading_edge_Yv_mm = 5.0;
    
    RaftGeometry raft1;
    raft1.min_Yv = 10.0;  // Starts after leading edge
    
    bool valid = BeltRaft::validate_leading_edge(raft1, profile);
    std::cout << "  Raft starting at Yv=10 (leading edge at 5): " 
              << (valid ? "VALID" : "INVALID") << std::endl;
    assert(valid && "Should be valid");
    
    RaftGeometry raft2;
    raft2.min_Yv = 2.0;  // Starts before leading edge
    
    valid = BeltRaft::validate_leading_edge(raft2, profile);
    std::cout << "  Raft starting at Yv=2 (leading edge at 5): " 
              << (valid ? "VALID" : "INVALID") << std::endl;
    assert(!valid && "Should be invalid");
    
    std::cout << "✓ Leading edge validation correct" << std::endl;
}

void test_clip_to_printable_strip() {
    std::cout << "\n=== Clip to Printable Strip Test ===" << std::endl;
    
    // Polygon extending from Y=-10 to Y=50
    Polygon2D poly = BeltRaft::create_rectangle(0, 20, -10, 50);
    
    std::cout << "  Original Y range: [-10, 50]" << std::endl;
    
    // Clip to [0, 40]
    Polygon2D clipped = BeltRaft::clip_to_printable_strip(poly, 0, 40);
    
    auto bbox = BeltRaft::compute_bbox_2d(clipped);
    std::cout << "  Clipped Y range: [" << bbox[2] << ", " << bbox[3] << "]" << std::endl;
    
    assert(bbox[2] >= 0 && "Min Y should be >= 0");
    assert(bbox[3] <= 40 && "Max Y should be <= 40");
    
    std::cout << "✓ Clipping to printable strip correct" << std::endl;
}

int main() {
    std::cout << "==================================================" << std::endl;
    std::cout << "Belt Printer T04 Belt Raft Tests" << std::endl;
    std::cout << "==================================================" << std::endl;
    
    try {
        test_raft_generation_basic();
        test_upstream_extension();
        test_polygon_expansion();
        test_layer_heights();
        test_leading_edge_validation();
        test_clip_to_printable_strip();
        
        std::cout << "\n==================================================" << std::endl;
        std::cout << "✓ ALL BELT RAFT TESTS PASSED" << std::endl;
        std::cout << "==================================================" << std::endl;
        
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n✗ TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
}
