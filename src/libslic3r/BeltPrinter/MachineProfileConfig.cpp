// BeltMachineProfile::create_from_config and transform helpers implementation

#include "MachineProfile.hpp"
#include "../PrintConfig.hpp"
#include <cmath>
#include <limits>

namespace Slic3r {
namespace BeltPrinter {

// Factory method to create profile from PrintConfig
// NOTE: belt_angle and belt_axis config options not yet added to PrintConfig.
// For now, this returns a CR30-like default profile.
// TODO: Add belt_angle and belt_axis to PrintConfig.hpp and uncomment the config-based logic.
BeltPrinter::BeltMachineProfile BeltMachineProfile::create_from_config(const PrintConfig& /* config */) {
    // Until config options are added, use the CR30 example as default
    return create_CR30_example();
    
    /* Original config-based implementation (requires PrintConfig changes):
    BeltPrinter::BeltMachineProfile profile;
    
    profile.machine_id = "CONFIG_BASED_BELT_PRINTER";
    profile.gantry_angle_theta_deg = config.belt_angle.value;
    
    // ... rest of config-based logic ...
    */
}

// Helper methods for V↔F transformations
Eigen::Affine3d BeltMachineProfile::get_V_to_F_transform() const {
    Eigen::Affine3d transform = Eigen::Affine3d::Identity();
    transform.linear() = M_VF;
    transform.translation() = t_VF;
    return transform;
}

Eigen::Affine3d BeltMachineProfile::get_F_to_V_transform() const {
    Eigen::Affine3d transform = Eigen::Affine3d::Identity();
    transform.linear() = M_VF.transpose(); // Orthonormal: inverse = transpose
    transform.translation() = -M_VF.transpose() * t_VF;
    return transform;
}

} // namespace Belt Printer
} // namespace Slic3r
