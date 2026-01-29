#ifndef slic3r_BeltPrinter_GCodeEmitter_hpp_
#define slic3r_BeltPrinter_GCodeEmitter_hpp_

#include "MachineProfile.hpp"
#include "BeltTransforms.hpp"
#include "BeltContactClassifier.hpp"
#include <string>
#include <sstream>

namespace Slic3r {
namespace BeltPrinter {

/// G-code move command
struct GCodeMove {
    PointV position_V;              // Position in Virtual Belt Frame
    double extrusion_mm;            // Extrusion amount (E axis)
    double feedrate_mm_s;           // Feedrate in mm/s
    ContactClass contact_class;     // Contact classification
    
    GCodeMove()
        : position_V(PointV::Zero())
        , extrusion_mm(0.0)
        , feedrate_mm_s(0.0)
        , contact_class(ContactClass::NON_CONTACT)
    {}
    
    GCodeMove(const PointV& pos, double e, double f)
        : position_V(pos)
        , extrusion_mm(e)
        , feedrate_mm_s(f)
        , contact_class(ContactClass::NON_CONTACT)
    {}
};

/// G-code emission settings
struct GCodeEmissionSettings {
    bool use_V_to_F_mapping;        // Use V→F mapping (vs legacy transform)
    bool emit_comments;             // Emit coordinate comments
    bool apply_contact_params;      // Apply contact-specific parameters
    ContactClassificationSettings contact_settings;
    
    GCodeEmissionSettings()
        : use_V_to_F_mapping(true)
        , emit_comments(false)
        , apply_contact_params(true)
    {}
};

/// G-code emitter for belt printers
class GCodeEmitter {
public:
    /**
     * Emit a G1 move command with V→F mapping
     * 
     * @param move Move command in V frame
     * @param profile Machine profile for V→F mapping
     * @param settings Emission settings
     * @return G-code string (e.g., "G1 X10.5 Z20.3 Y15.2 E0.5 F3000")
     */
    static std::string emit_move(
        const GCodeMove& move,
        const BeltMachineProfile& profile,
        const GCodeEmissionSettings& settings
    );
    
    /**
     * Emit position in firmware frame
     * Applies V→F mapping and uses correct axis letters
     * 
     * @param position_V Position in V frame
     * @param profile Machine profile
     * @return Position string (e.g., "X10.5 Z20.3 Y15.2")
     */
    static std::string emit_position(
        const PointV& position_V,
        const BeltMachineProfile& profile
    );
    
    /**
     * Apply contact-specific parameter adjustments
     * 
     * @param move Move command with contact classification
     * @param settings Emission settings with contact parameters
     * @return Adjusted move command
     */
    static GCodeMove apply_contact_parameters(
        const GCodeMove& move,
        const GCodeEmissionSettings& settings
    );
    
    /**
     * Emit belt printer profile metadata as G-code comments
     * Should be emitted in G-code header
     * 
     * @param profile Machine profile
     * @return Multi-line comment string
     */
    static std::string emit_profile_metadata(
        const BeltMachineProfile& profile
    );
    
    /**
     * Generate safe ejection sequence
     * 
     * Algorithm:
     * 1. Retract filament
     * 2. Lift along Zv (normal axis) to safe_height_mm
     * 3. Advance belt by eject_distance_mm
     * 
     * @param profile Machine profile
     * @param safe_height_mm Lift height in Zv
     * @param eject_distance_mm Belt advance distance in Yv
     * @param retract_mm Retraction amount
     * @return G-code sequence
     */
    static std::string generate_safe_ejection_sequence(
        const BeltMachineProfile& profile,
        double safe_height_mm = 10.0,
        double eject_distance_mm = 50.0,
        double retract_mm = 5.0
    );
    
    /**
     * Get firmware axis letter for a V-frame axis
     * 
     * @param v_axis 0=Xv, 1=Yv, 2=Zv
     * @param profile Machine profile
     * @return Firmware axis letter ('X', 'Y', or 'Z')
     */
    static char get_firmware_axis_letter(
        int v_axis,
        const BeltMachineProfile& profile
    );
    
    /**
     * Format a coordinate value for G-code
     * 
     * @param value Coordinate value
     * @param precision Decimal places (default 3)
     * @return Formatted string (e.g., "10.500")
     */
    static std::string format_coordinate(
        double value,
        int precision = 3
    );
    
    /**
     * Format feedrate for G-code (convert mm/s to mm/min)
     * 
     * @param feedrate_mm_s Feedrate in mm/s
     * @return Formatted string (e.g., "F3000")
     */
    static std::string format_feedrate(
        double feedrate_mm_s
    );
};

} // namespace BeltPrinter
} // namespace Slic3r

#endif // slic3r_BeltPrinter_GCodeEmitter_hpp_
