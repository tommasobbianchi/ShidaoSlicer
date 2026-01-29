#include <iostream>
#include <cassert>
#include <limits>
#include "libslic3r/BeltMachineProfile.hpp"
#include "libslic3r/PrintConfig.hpp"

// Mock PrintConfig if linking fails, but we try to link first.
// If we link libslic3r, we have PrintConfig.

void test_validation() {
    std::cout << "Testing validation..." << std::endl;
    Slic3r::BeltMachineProfile profile;
    
    // Identity is valid
    profile.V_to_F.M_VF = Eigen::Matrix3d::Identity();
    profile.validate(); // Should pass
    
    // Invalid (Det != 1)
    profile.V_to_F.M_VF(0,0) = 2.0;
    bool caught = false;
    try {
        profile.validate();
    } catch (...) {
        caught = true;
    }
    assert(caught);
    
    // Invalid (Non-orthonormal)
    profile.V_to_F.M_VF = Eigen::Matrix3d::Identity();
    profile.V_to_F.M_VF(0,1) = 0.5; // Shear
    caught = false;
    try {
        profile.validate();
    } catch (...) {
        caught = true;
    }
    assert(caught);
    
    std::cout << "Validation tests passed." << std::endl;
}

void test_config_mapping() {
    std::cout << "Testing config mapping..." << std::endl;
    
    Slic3r::PrintConfig config;
    config.belt_printer.value = true;
    config.belt_angle.value = 45.0;
    
    // Case 1: Belt Axis Z (CR-30 style)
    config.belt_axis.value = Slic3r::BeltAxis::Z;
    auto p1 = Slic3r::BeltMachineProfile::from_config(config);
    
    // Expected M_VF:
    // Xv(1,0,0) -> Xf(1,0,0)
    // Yv(0,1,0) -> Zf(0,0,1)
    // Zv(0,0,1) -> Yf(0,1,0) (Gantry)
    
    Eigen::Matrix3d m = p1.V_to_F.M_VF;
    assert(std::abs(m(0,0) - 1.0) < 1e-5); // X -> X
    assert(std::abs(m(2,1) - 1.0) < 1e-5); // Yv -> Zf
    assert(std::abs(m(1,2) - 1.0) < 1e-5); // Zv -> Yf
    
    std::cout << "Config mapping (Z-belt) passed." << std::endl;
}

int main() {
    try {
        test_validation();
        test_config_mapping();
    } catch (const std::exception& e) {
        std::cerr << "Test failed with exception: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
