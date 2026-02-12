// BeltMachineProfile::create_from_config and transform helpers implementation

#include "MachineProfile.hpp"
#include "../PrintConfig.hpp"
#include <cmath>
#include <limits>

namespace Slic3r {
namespace BeltPrinter {

BeltPrinter::BeltMachineProfile BeltMachineProfile::create_from_config(const PrintConfig& config) {
    BeltMachineProfile profile;

    // 1. Identity & gantry angle
    profile.machine_id = "CONFIG_BELT_PRINTER";
    profile.gantry_angle_theta_deg = config.belt_angle.value;

    // 2. Axis mapping from belt_axis
    //    Convention: width is always X. The remaining axis is normal.
    BeltAxis belt = config.belt_axis.value;
    switch (belt) {
        case BeltAxis::Y:
            // IdeaFormer-style: Belt=Y, Normal=Z, Width=X → M_VF = Identity
            profile.belt_axis_letter   = FirmwareAxisLetter::Y;
            profile.normal_axis_letter = FirmwareAxisLetter::Z;
            profile.width_axis_letter  = FirmwareAxisLetter::X;
            profile.M_VF = Eigen::Matrix3d::Identity();
            break;
        case BeltAxis::Z:
            // CR30-style: Belt=Z, Normal=Y, Width=X → M_VF swaps Yv↔Zv
            profile.belt_axis_letter   = FirmwareAxisLetter::Z;
            profile.normal_axis_letter = FirmwareAxisLetter::Y;
            profile.width_axis_letter  = FirmwareAxisLetter::X;
            profile.M_VF << 1, 0, 0,
                            0, 0, 1,
                            0, 1, 0;
            break;
        case BeltAxis::X:
            // Unusual: Belt=X, Normal=Z, Width=Y → M_VF swaps Xv↔Yv
            profile.belt_axis_letter   = FirmwareAxisLetter::X;
            profile.normal_axis_letter = FirmwareAxisLetter::Z;
            profile.width_axis_letter  = FirmwareAxisLetter::Y;
            profile.M_VF << 0, 1, 0,
                            1, 0, 0,
                            0, 0, 1;
            break;
    }
    profile.t_VF = Eigen::Vector3d::Zero();

    // 3. Build volume from printable_area (firmware XY polygon) and printable_height (firmware Z)
    const auto& pts = config.printable_area.values;
    double fw_x_min = 1e9, fw_x_max = -1e9;
    double fw_y_min = 1e9, fw_y_max = -1e9;
    for (const auto& p : pts) {
        fw_x_min = std::min(fw_x_min, p.x());
        fw_x_max = std::max(fw_x_max, p.x());
        fw_y_min = std::min(fw_y_min, p.y());
        fw_y_max = std::max(fw_y_max, p.y());
    }
    double fw_z_max = config.printable_height.value;

    // Map firmware bbox to virtual frame: pV = M_VF^T * pF
    Eigen::Vector3d fw_min(fw_x_min, fw_y_min, 0.0);
    Eigen::Vector3d fw_max(fw_x_max, fw_y_max, fw_z_max);
    Eigen::Vector3d v_min = profile.M_VF.transpose() * fw_min;
    Eigen::Vector3d v_max = profile.M_VF.transpose() * fw_max;

    profile.Xv_min_mm = std::min(v_min.x(), v_max.x());
    profile.Xv_max_mm = std::max(v_min.x(), v_max.x());
    profile.Zv_min_mm = 0.0;
    profile.Zv_max_mm = std::max(v_min.z(), v_max.z());

    // 4. Belt axis is infinite
    profile.Yv_mode = BeltAxisMode::Infinite;
    profile.Yv_preview_window_mm = std::max(std::abs(v_max.y() - v_min.y()), 400.0);

    // 5. Belt geometry defaults
    profile.belt_leading_edge_Yv_mm    = 0.0;
    profile.belt_printable_Yv_min_mm   = 0.0;
    profile.belt_printable_Yv_max_mm   = std::numeric_limits<double>::infinity();
    profile.roller_clearance_Yv_mm     = 15.0;

    // 6. Belt direction (positive = forward)
    profile.belt_positive_direction_in_V        = 1;
    profile.belt_positive_direction_in_firmware  = 1;

    // 7. Dynamics defaults (can be refined with per-axis config later)
    profile.belt_axis_limits.max_feedrate_mm_s    = 60.0;
    profile.belt_axis_limits.max_accel_mm_s2      = 300.0;
    profile.belt_axis_limits.max_jerk_mm_s        = 6.0;
    profile.non_belt_axes_limits.max_feedrate_mm_s = 120.0;
    profile.non_belt_axes_limits.max_accel_mm_s2   = 1500.0;
    profile.non_belt_axes_limits.max_jerk_mm_s     = 10.0;

    // 8. No compatibility mode
    profile.compatibility_mode_enabled = false;

    profile.validate();
    return profile;
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
