#include <catch2/catch_all.hpp>
#include "libslic3r/BeltMachineProfile.hpp"
#include "libslic3r/PrintConfig.hpp"
#include <iostream>

using namespace Slic3r;

TEST_CASE("BeltMachineProfile Validation", "[belt_profile]") {
    BeltMachineProfile profile;
    
    SECTION("Valid Identity Matrix") {
        profile.V_to_F.M_VF = Eigen::Matrix3d::Identity();
        REQUIRE_NOTHROW(profile.validate());
    }

    SECTION("Invalid Determinant") {
        profile.V_to_F.M_VF = Eigen::Matrix3d::Identity();
        profile.V_to_F.M_VF(0,0) = 2.0;
        REQUIRE_THROWS_AS(profile.validate(), std::runtime_error);
    }
    
    SECTION("Non-Orthonormal (Shear)") {
        profile.V_to_F.M_VF = Eigen::Matrix3d::Identity();
        profile.V_to_F.M_VF(0,1) = 0.5;
        REQUIRE_THROWS_AS(profile.validate(), std::runtime_error);
    }
}

TEST_CASE("BeltMachineProfile Config Mapping", "[belt_profile]") {
    PrintConfig config;
    config.belt_printer.value = true;
    config.belt_angle.value = 45.0;

    SECTION("Z-Axis Belt (Standard)") {
        config.belt_axis.value = BeltAxis::Z;
        auto profile = BeltMachineProfile::from_config(config);
        
        // Check M_VF
        // Xv -> Xf (1,0,0)
        // Yv -> Zf (0,0,1)
        // Zv -> Yf (0,1,0)
        
        Eigen::Matrix3d m = profile.V_to_F.M_VF;
        CHECK(m(0,0) == Catch::Approx(1.0));
        CHECK(m(2,1) == Catch::Approx(1.0));
        CHECK(m(1,2) == Catch::Approx(1.0));
        CHECK(profile.axis_role_letters.belt_axis_letter == "Z");
    }

    SECTION("Y-Axis Belt") {
        config.belt_axis.value = BeltAxis::Y;
        auto profile = BeltMachineProfile::from_config(config);
        
        // Xv -> Xf
        // Yv -> Yf
        // Zv -> Zf
        Eigen::Matrix3d m = profile.V_to_F.M_VF;
        CHECK(m(0,0) == Catch::Approx(1.0));
        CHECK(m(1,1) == Catch::Approx(1.0));
        CHECK(m(2,2) == Catch::Approx(1.0));
        CHECK(profile.axis_role_letters.belt_axis_letter == "Y");
    }
    
    SECTION("Spec Compatibility for T01") {
        // T01 requires validation and config mapping
        BeltMachineProfile p;
        p.V_to_F.M_VF = Eigen::Matrix3d::Identity();
        REQUIRE_NOTHROW(p.validate());
    }
}
