#include "MachineProfile.hpp"
#include <cmath>
#include <sstream>

namespace Slic3r {
namespace BeltPrinter {

// === BeltPrinter::BeltMachineProfile Implementation ===

BeltMachineProfile::BeltMachineProfile()
    : machine_id("UNKNOWN")
    , gantry_angle_theta_deg(45.0)
    , belt_axis_letter(FirmwareAxisLetter::Z)
    , normal_axis_letter(FirmwareAxisLetter::Y)
    , width_axis_letter(FirmwareAxisLetter::X)
    , M_VF(Eigen::Matrix3d::Identity())
    , t_VF(Eigen::Vector3d::Zero())
    , Xv_min_mm(0.0)
    , Xv_max_mm(200.0)
    , Zv_min_mm(0.0)
    , Zv_max_mm(200.0)
    , Yv_mode(BeltAxisMode::Infinite)
    , Yv_preview_window_mm(400.0)
    , belt_leading_edge_Yv_mm(0.0)
    , belt_printable_Yv_min_mm(0.0)
    , belt_printable_Yv_max_mm(std::numeric_limits<double>::infinity())
    , roller_clearance_Yv_mm(15.0)
    , belt_positive_direction_in_V(1)
    , belt_positive_direction_in_firmware(1)
    , compatibility_mode_enabled(false)
    , T_compat_4x4(Eigen::Matrix4d::Identity())
    , is_validated(false)
{
    belt_axis_limits.max_feedrate_mm_s = 60.0;
    belt_axis_limits.max_accel_mm_s2 = 300.0;
    belt_axis_limits.max_jerk_mm_s = 6.0;
    
    non_belt_axes_limits.max_feedrate_mm_s = 120.0;
    non_belt_axes_limits.max_accel_mm_s2 = 1500.0;
    non_belt_axes_limits.max_jerk_mm_s = 10.0;
}

BeltPrinter::BeltMachineProfile BeltMachineProfile::create_CR30_example()
{
    BeltPrinter::BeltMachineProfile profile;
    
    profile.machine_id = "CR30_LIKE_EXAMPLE";
    profile.gantry_angle_theta_deg = 45.0;
    
    // CR30 mapping: Xv→X, Yv→Z, Zv→Y
    profile.belt_axis_letter = FirmwareAxisLetter::Z;
    profile.normal_axis_letter = FirmwareAxisLetter::Y;
    profile.width_axis_letter = FirmwareAxisLetter::X;
    
    // M_VF matrix: [[1,0,0], [0,0,1], [0,1,0]]
    // This maps: Xv→Xf, Yv→Zf, Zv→Yf
    profile.M_VF << 1, 0, 0,
                    0, 0, 1,
                    0, 1, 0;
    
    profile.t_VF = Eigen::Vector3d::Zero();
    
    // Build volume
    profile.Xv_min_mm = 0.0;
    profile.Xv_max_mm = 200.0;
    profile.Zv_min_mm = 0.0;
    profile.Zv_max_mm = 200.0;
    profile.Yv_mode = BeltAxisMode::Infinite;
    profile.Yv_preview_window_mm = 400.0;
    
    // Belt geometry
    profile.belt_leading_edge_Yv_mm = 0.0;
    profile.belt_printable_Yv_min_mm = 0.0;
    profile.belt_printable_Yv_max_mm = std::numeric_limits<double>::infinity();
    profile.roller_clearance_Yv_mm = 15.0;
    
    // Directions
    profile.belt_positive_direction_in_V = 1;
    profile.belt_positive_direction_in_firmware = 1;
    
    // Dynamics
    profile.belt_axis_limits.max_feedrate_mm_s = 60.0;
    profile.belt_axis_limits.max_accel_mm_s2 = 300.0;
    profile.belt_axis_limits.max_jerk_mm_s = 6.0;
    
    profile.non_belt_axes_limits.max_feedrate_mm_s = 120.0;
    profile.non_belt_axes_limits.max_accel_mm_s2 = 1500.0;
    profile.non_belt_axes_limits.max_jerk_mm_s = 10.0;
    
    // Compatibility mode disabled
    profile.compatibility_mode_enabled = false;
    
    profile.validate();
    
    return profile;
}

bool BeltMachineProfile::validate()
{
    validation_error.clear();
    is_validated = false;
    
    ValidationResult result;
    
    // 1. Check M_VF is orthonormal
    Eigen::Matrix3d M_VF_transpose = M_VF.transpose();
    Eigen::Matrix3d product = M_VF * M_VF_transpose;
    Eigen::Matrix3d identity = Eigen::Matrix3d::Identity();
    
    double orthonormal_error = (product - identity).norm();
    if (orthonormal_error > 1e-6) {
        result.add_error("M_VF is not orthonormal: M_VF * M_VF^T != I (error: " + 
                        std::to_string(orthonormal_error) + ")");
    }
    
    // 2. Check determinant is ±1
    double det = M_VF.determinant();
    if (std::abs(std::abs(det) - 1.0) > 1e-6) {
        result.add_error("M_VF determinant is not ±1: det = " + std::to_string(det));
    }
    
    // 3. Check each row and column has exactly one non-zero entry
    for (int i = 0; i < 3; ++i) {
        int row_nonzero_count = 0;
        int col_nonzero_count = 0;
        
        for (int j = 0; j < 3; ++j) {
            if (std::abs(M_VF(i, j)) > 1e-6) row_nonzero_count++;
            if (std::abs(M_VF(j, i)) > 1e-6) col_nonzero_count++;
        }
        
        if (row_nonzero_count != 1) {
            result.add_error("M_VF row " + std::to_string(i) + " has " + 
                           std::to_string(row_nonzero_count) + " non-zero entries (expected 1)");
        }
        if (col_nonzero_count != 1) {
            result.add_error("M_VF column " + std::to_string(i) + " has " + 
                           std::to_string(col_nonzero_count) + " non-zero entries (expected 1)");
        }
    }
    
    // 4. Check axis letters are distinct
    if (belt_axis_letter == normal_axis_letter || 
        belt_axis_letter == width_axis_letter || 
        normal_axis_letter == width_axis_letter) {
        result.add_error("Axis letters must be distinct (belt=" + 
                        std::string(1, axis_letter_to_char(belt_axis_letter)) + 
                        ", normal=" + std::string(1, axis_letter_to_char(normal_axis_letter)) + 
                        ", width=" + std::string(1, axis_letter_to_char(width_axis_letter)) + ")");
    }
    
    // 5. Check build volume constraints
    if (Xv_max_mm <= Xv_min_mm) {
        result.add_error("Invalid Xv range: max=" + std::to_string(Xv_max_mm) + 
                        " <= min=" + std::to_string(Xv_min_mm));
    }
    
    if (Zv_max_mm <= Zv_min_mm) {
        result.add_error("Invalid Zv range: max=" + std::to_string(Zv_max_mm) + 
                        " <= min=" + std::to_string(Zv_min_mm));
    }
    
    if (Zv_min_mm != 0.0) {
        result.add_warning("Zv_min_mm should be 0 (belt plane), got " + std::to_string(Zv_min_mm));
    }
    
    // 6. Check belt direction signs
    if (belt_positive_direction_in_V != 1 && belt_positive_direction_in_V != -1) {
        result.add_error("belt_positive_direction_in_V must be +1 or -1, got " + 
                        std::to_string(belt_positive_direction_in_V));
    }
    
    if (belt_positive_direction_in_firmware != 1 && belt_positive_direction_in_firmware != -1) {
        result.add_error("belt_positive_direction_in_firmware must be +1 or -1, got " + 
                        std::to_string(belt_positive_direction_in_firmware));
    }
    
    // 7. Check gantry angle is reasonable
    if (gantry_angle_theta_deg < 0.0 || gantry_angle_theta_deg > 90.0) {
        result.add_warning("Unusual gantry angle: " + std::to_string(gantry_angle_theta_deg) + 
                          "° (expected 0-90°)");
    }
    
    // Store result
    is_validated = result.valid;
    if (!result.valid) {
        validation_error = result.to_string();
    }
    
    return result.valid;
}

char BeltMachineProfile::axis_letter_to_char(FirmwareAxisLetter letter)
{
    switch (letter) {
        case FirmwareAxisLetter::X: return 'X';
        case FirmwareAxisLetter::Y: return 'Y';
        case FirmwareAxisLetter::Z: return 'Z';
        default: return '?';
    }
}

FirmwareAxisLetter BeltMachineProfile::char_to_axis_letter(char c)
{
    switch (c) {
        case 'X': case 'x': return FirmwareAxisLetter::X;
        case 'Y': case 'y': return FirmwareAxisLetter::Y;
        case 'Z': case 'z': return FirmwareAxisLetter::Z;
        default: return FirmwareAxisLetter::X;  // Default fallback
    }
}

int BeltMachineProfile::get_firmware_axis_index(VirtualAxisRole role) const
{
    switch (role) {
        case VirtualAxisRole::BeltAxis:
            return static_cast<int>(belt_axis_letter);
        case VirtualAxisRole::NormalAxis:
            return static_cast<int>(normal_axis_letter);
        case VirtualAxisRole::WidthAxis:
            return static_cast<int>(width_axis_letter);
        default:
            return 0;
    }
}

// === ValidationResult Implementation ===

std::string ValidationResult::to_string() const
{
    std::ostringstream oss;
    
    if (valid) {
        oss << "Validation PASSED";
    } else {
        oss << "Validation FAILED";
    }
    
    if (!errors.empty()) {
        oss << "\n\nErrors:";
        for (const auto& err : errors) {
            oss << "\n  - " << err;
        }
    }
    
    if (!warnings.empty()) {
        oss << "\n\nWarnings:";
        for (const auto& warn : warnings) {
            oss << "\n  - " << warn;
        }
    }
    
    return oss.str();
}

} // namespace BeltPrinter
} // namespace Slic3r
