#ifndef slic3r_BeltPrinter_MachineProfile_hpp_
#define slic3r_BeltPrinter_MachineProfile_hpp_

#include <string>
#include <array>
#include <Eigen/Dense>

namespace Slic3r {
class PrintConfig;
namespace BeltPrinter {

/// Axis role in the Virtual Belt Frame (V)
enum class VirtualAxisRole {
    BeltAxis,    // Yv - along belt travel direction (effectively unbounded)
    NormalAxis,  // Zv - normal to belt plane (layer height axis)
    WidthAxis    // Xv - across belt width (finite)
};

/// Firmware axis letter (X, Y, or Z)
enum class FirmwareAxisLetter {
    X = 0,
    Y = 1,
    Z = 2
};

/// Build volume mode for belt axis
enum class BeltAxisMode {
    Infinite,   // Unbounded build length
    Bounded     // Finite build length (for testing/preview)
};

/// Belt machine profile matching the specification schema
struct BeltMachineProfile {
    EIGEN_MAKE_ALIGNED_OPERATOR_NEW
    
    // === Identity ===
    std::string machine_id;
    
    // === Gantry Geometry ===
    double gantry_angle_theta_deg;  // Typically 45°
    
    // === Axis Role Mapping ===
    // Which firmware axis letter corresponds to each virtual role
    FirmwareAxisLetter belt_axis_letter;     // e.g., Z for CR30
    FirmwareAxisLetter normal_axis_letter;   // e.g., Y for CR30
    FirmwareAxisLetter width_axis_letter;    // e.g., X for CR30
    
    // === V→F Coordinate Mapping ===
    // Orthonormal permutation matrix: pF = M_VF * pV + t_VF
    // M_VF must have exactly one non-zero entry per row/column, each ±1
    Eigen::Matrix3d M_VF;
    Eigen::Vector3d t_VF;
    
    // === Build Volume in Virtual Frame ===
    double Xv_min_mm;
    double Xv_max_mm;
    double Zv_min_mm;  // Always 0 (belt plane)
    double Zv_max_mm;
    
    BeltAxisMode Yv_mode;
    double Yv_preview_window_mm;  // For visualization when infinite
    
    // === Belt Geometry ===
    double belt_leading_edge_Yv_mm;      // Where printable region starts
    double belt_printable_Yv_min_mm;     // Minimum printable Yv
    double belt_printable_Yv_max_mm;     // Maximum printable Yv (or infinity)
    double roller_clearance_Yv_mm;       // Safety margin near rollers
    
    // === Belt Direction ===
    // Sign of belt positive direction in V and firmware frames
    int belt_positive_direction_in_V;         // +1 or -1
    int belt_positive_direction_in_firmware;  // +1 or -1
    
    // === Dynamics Limits (optional) ===
    struct AxisLimits {
        double max_feedrate_mm_s;
        double max_accel_mm_s2;
        double max_jerk_mm_s;  // 0 if not used
    };
    
    AxisLimits belt_axis_limits;
    AxisLimits non_belt_axes_limits;
    
    // === Compatibility Mode (optional) ===
    bool compatibility_mode_enabled;
    Eigen::Matrix4d T_compat_4x4;  // Affine transform (may include scale/shear)
    
    // === Validation State ===
    bool is_validated;
    std::string validation_error;
    
    // === Constructors ===
    BeltMachineProfile();
    
    /// Create example CR30-like profile from specification
    static BeltMachineProfile create_CR30_example();
    
    /// Create profile from PrintConfig
    static BeltMachineProfile create_from_config(const Slic3r::PrintConfig& config);
    
    /// Validate the profile (orthonormality, axis constraints, etc.)
    bool validate();
    
    /// Get axis letter as char ('X', 'Y', or 'Z')
    static char axis_letter_to_char(FirmwareAxisLetter letter);
    
    /// Parse axis letter from char
    static FirmwareAxisLetter char_to_axis_letter(char c);
    
    /// Get the firmware axis index (0=X, 1=Y, 2=Z) for a virtual role
    int get_firmware_axis_index(VirtualAxisRole role) const;
    
    /// Check if Yv axis is infinite
    bool is_infinite_belt() const { return Yv_mode == BeltAxisMode::Infinite; }
    
    /// Get V→F transformation (rotation + translation)
    Eigen::Affine3d get_V_to_F_transform() const;
    
    /// Get F→V transformation (inverse of V→F)
    Eigen::Affine3d get_F_to_V_transform() const;
    
    /// Get V→F rotation matrix only
    Eigen::Matrix3d V_to_F_rotation() const { return M_VF; }
};

/// Validation result with detailed error reporting
struct ValidationResult {
    bool valid;
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
    
    ValidationResult() : valid(true) {}
    
    void add_error(const std::string& msg) {
        errors.push_back(msg);
        valid = false;
    }
    
    void add_warning(const std::string& msg) {
        warnings.push_back(msg);
    }
    
    std::string to_string() const;
};

} // namespace BeltPrinter
} // namespace Slic3r

#endif // slic3r_BeltPrinter_MachineProfile_hpp_
