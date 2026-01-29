#ifndef slic3r_BeltBed3D_hpp_
#define slic3r_BeltBed3D_hpp_

#include "3DBed.hpp"
#include "libslic3r/BeltPrinter/MachineProfile.hpp"
#include "libslic3r/BeltPrinter/BeltTransforms.hpp"
#include "libslic3r/BeltPrinter/VirtualBeltFrame.hpp"

namespace Slic3r {
namespace GUI {

/**
 * BeltBed3D - Wrapper for Bed3D with proper belt printer support
 * 
 * This class extends Bed3D to provide:
 * - Consistent coordinate visualization between Prepare and Preview tabs
 * - Integration with BeltPrinter modules (MachineProfile, V→F mapping)
 * - Proper infinite/long belt visualization
 * 
 * CRITICAL: Ensures object appears in SAME position in both tabs
 */
class BeltBed3D : public Bed3D
{
private:
    // Belt printer profile from our modules
    BeltPrinter::BeltMachineProfile m_belt_profile;
    bool m_belt_profile_loaded{false};
    
public:
    BeltBed3D() = default;
    ~BeltBed3D() = default;
    
    /**
     * Load belt printer profile from configuration
     * Called when belt printer mode is enabled
     */
    void load_belt_profile(const DynamicPrintConfig& config);
    
    /**
     * Check if belt profile is loaded and valid
     */
    bool has_valid_belt_profile() const { return m_belt_profile_loaded; }
    
    /**
     * Get the belt profile
     */
    const BeltPrinter::BeltMachineProfile& get_belt_profile() const { return m_belt_profile; }
    
    /**
     * Override render to apply correct belt transform
     * CRITICAL: Same transform in BOTH Prepare and Preview
     * Note: Bed3D::render is not virtual, so we "hide" it rather than override
     */
    void render(GLCanvas3D& canvas, const Transform3d& view_matrix, const Transform3d& projection_matrix, 
                bool bottom, float scale_factor, bool show_axes);
    
private:
    /**
     * Compute belt transform for rendering
     * Uses our BeltPrinter modules instead of ad-hoc logic
     */
    Transform3d compute_belt_transform() const;
    
    /**
     * Render belt bed with proper infinite/long visualization
     */
    void render_belt_bed(const Transform3d& view_matrix, const Transform3d& projection_matrix);
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_BeltBed3D_hpp_
