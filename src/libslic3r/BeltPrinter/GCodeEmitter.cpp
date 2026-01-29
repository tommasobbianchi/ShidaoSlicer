#include "GCodeEmitter.hpp"
#include <iomanip>
#include <cmath>

namespace Slic3r {
namespace BeltPrinter {

std::string GCodeEmitter::emit_move(
    const GCodeMove& move,
    const BeltMachineProfile& profile,
    const GCodeEmissionSettings& settings)
{
    // Apply contact-specific parameters if enabled
    GCodeMove adjusted_move = move;
    if (settings.apply_contact_params) {
        adjusted_move = apply_contact_parameters(move, settings);
    }
    
    std::ostringstream gcode;
    gcode << "G1";
    
    // Emit position with V→F mapping
    if (settings.use_V_to_F_mapping) {
        gcode << " " << emit_position(adjusted_move.position_V, profile);
    }
    
    // Emit extrusion
    if (adjusted_move.extrusion_mm > 0.0) {
        gcode << " E" << format_coordinate(adjusted_move.extrusion_mm, 5);
    }
    
    // Emit feedrate
    if (adjusted_move.feedrate_mm_s > 0.0) {
        gcode << " " << format_feedrate(adjusted_move.feedrate_mm_s);
    }
    
    // Emit comment if enabled
    if (settings.emit_comments) {
        gcode << " ; V=(" 
              << format_coordinate(move.position_V.x()) << "," 
              << format_coordinate(move.position_V.y()) << "," 
              << format_coordinate(move.position_V.z()) << ")";
        
        if (move.contact_class == ContactClass::BELT_CONTACT) {
            gcode << " BELT_CONTACT";
        }
    }
    
    return gcode.str();
}

std::string GCodeEmitter::emit_position(
    const PointV& position_V,
    const BeltMachineProfile& profile)
{
    // Apply V→F mapping
    PointF position_F = BeltTransforms::apply_V_to_F_mapping(position_V, profile);
    
    std::ostringstream pos;
    
    // Emit in firmware axis order (X, Y, Z)
    // Determine which V axis maps to each F axis
    for (int f_axis = 0; f_axis < 3; ++f_axis) {
        char axis_letter = BeltMachineProfile::axis_letter_to_char(
            static_cast<FirmwareAxisLetter>(f_axis));
        
        double value = position_F[f_axis];
        pos << axis_letter << format_coordinate(value);
        
        if (f_axis < 2) {
            pos << " ";
        }
    }
    
    return pos.str();
}

GCodeMove GCodeEmitter::apply_contact_parameters(
    const GCodeMove& move,
    const GCodeEmissionSettings& settings)
{
    GCodeMove adjusted = move;
    
    // Get parameter set for this contact class
    ContactParameterSet params = BeltContactClassifier::get_parameter_set(
        move.contact_class, settings.contact_settings);
    
    // Apply speed multiplier
    adjusted.feedrate_mm_s *= params.speed_multiplier;
    
    // Apply flow multiplier (affects extrusion)
    adjusted.extrusion_mm *= params.flow_multiplier;
    
    // Note: Fan multiplier would be applied separately in fan control G-code
    
    return adjusted;
}

std::string GCodeEmitter::emit_profile_metadata(
    const BeltMachineProfile& profile)
{
    std::ostringstream metadata;
    
    metadata << "; Belt Printer Profile Metadata\n";
    metadata << "; Machine ID: " << profile.machine_id << "\n";
    metadata << "; Gantry Angle: " << profile.gantry_angle_theta_deg << " degrees\n";
    metadata << "; Belt Axis (Firmware): " 
             << BeltMachineProfile::axis_letter_to_char(profile.belt_axis_letter) << "\n";
    metadata << "; Normal Axis (Firmware): " 
             << BeltMachineProfile::axis_letter_to_char(profile.normal_axis_letter) << "\n";
    metadata << "; Width Axis (Firmware): " 
             << BeltMachineProfile::axis_letter_to_char(profile.width_axis_letter) << "\n";
    
    metadata << "; V→F Mapping Matrix:\n";
    for (int i = 0; i < 3; ++i) {
        metadata << ";   [";
        for (int j = 0; j < 3; ++j) {
            metadata << std::setw(4) << profile.M_VF(i, j);
            if (j < 2) metadata << ",";
        }
        metadata << "]\n";
    }
    
    metadata << "; V→F Translation: ["
             << profile.t_VF.x() << ", "
             << profile.t_VF.y() << ", "
             << profile.t_VF.z() << "]\n";
    
    return metadata.str();
}

std::string GCodeEmitter::generate_safe_ejection_sequence(
    const BeltMachineProfile& profile,
    double safe_height_mm,
    double eject_distance_mm,
    double retract_mm)
{
    std::ostringstream gcode;
    
    gcode << "; Safe Belt Ejection Sequence\n";
    
    // Step 1: Retract filament
    gcode << "G1 E" << format_coordinate(-retract_mm, 5) 
          << " F1800 ; Retract filament\n";
    
    // Step 2: Lift along Zv (normal axis)
    // Create a move in V frame: lift by safe_height_mm in Zv
    PointV lift_position(0, 0, safe_height_mm);
    PointF lift_F = BeltTransforms::apply_V_to_F_mapping(lift_position, profile);
    
    // Emit relative move for normal axis only
    char normal_axis = BeltMachineProfile::axis_letter_to_char(profile.normal_axis_letter);
    int normal_axis_index = static_cast<int>(profile.normal_axis_letter);
    
    gcode << "G91 ; Relative positioning\n";
    gcode << "G1 " << normal_axis << format_coordinate(lift_F[normal_axis_index]) 
          << " F3000 ; Lift along normal axis\n";
    gcode << "G90 ; Absolute positioning\n";
    
    // Step 3: Advance belt
    // Create a move in V frame: advance by eject_distance_mm in Yv
    PointV eject_position(0, eject_distance_mm, 0);
    PointF eject_F = BeltTransforms::apply_V_to_F_mapping(eject_position, profile);
    
    char belt_axis = BeltMachineProfile::axis_letter_to_char(profile.belt_axis_letter);
    int belt_axis_index = static_cast<int>(profile.belt_axis_letter);
    
    gcode << "G91 ; Relative positioning\n";
    gcode << "G1 " << belt_axis << format_coordinate(eject_F[belt_axis_index]) 
          << " F1800 ; Advance belt\n";
    gcode << "G90 ; Absolute positioning\n";
    
    gcode << "; End Safe Ejection\n";
    
    return gcode.str();
}

char GCodeEmitter::get_firmware_axis_letter(
    int v_axis,
    const BeltMachineProfile& profile)
{
    // v_axis: 0=Xv, 1=Yv, 2=Zv
    // Find which firmware axis this V axis maps to
    
    // M_VF maps V to F: pF = M_VF * pV
    // Column v_axis of M_VF tells us which F axis Xv/Yv/Zv maps to
    
    for (int f_axis = 0; f_axis < 3; ++f_axis) {
        if (std::abs(profile.M_VF(f_axis, v_axis)) > 0.5) {
            return BeltMachineProfile::axis_letter_to_char(
                static_cast<FirmwareAxisLetter>(f_axis));
        }
    }
    
    return 'X';  // Fallback
}

std::string GCodeEmitter::format_coordinate(
    double value,
    int precision)
{
    std::ostringstream ss;
    ss << std::fixed << std::setprecision(precision) << value;
    return ss.str();
}

std::string GCodeEmitter::format_feedrate(
    double feedrate_mm_s)
{
    // Convert mm/s to mm/min
    double feedrate_mm_min = feedrate_mm_s * 60.0;
    
    std::ostringstream ss;
    ss << "F" << static_cast<int>(std::round(feedrate_mm_min));
    return ss.str();
}

} // namespace BeltPrinter
} // namespace Slic3r
