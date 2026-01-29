#include "BeltBed3D.hpp"
#include "GLCanvas3D.hpp"
#include <boost/log/trivial.hpp>

namespace Slic3r {
namespace GUI {

void BeltBed3D::load_belt_profile(const DynamicPrintConfig& config)
{
    try {
        // Convert DynamicPrintConfig to PrintConfig
        PrintConfig print_config;
        print_config.apply(config, true);
        
        // Create belt profile from config
        m_belt_profile = BeltPrinter::BeltMachineProfile::create_from_config(print_config);
        
        // Validate profile (returns bool)
        bool is_valid = m_belt_profile.validate();
        if (!is_valid) {
            BOOST_LOG_TRIVIAL(error) << "BeltBed3D: Invalid belt profile - " << m_belt_profile.validation_error;
            m_belt_profile_loaded = false;
            return;
        }
        
        m_belt_profile_loaded = true;
        BOOST_LOG_TRIVIAL(info) << "BeltBed3D: Loaded belt profile - " << m_belt_profile.machine_id;
        
    } catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(error) << "BeltBed3D: Failed to load belt profile - " << e.what();
        m_belt_profile_loaded = false;
    }
}

Transform3d BeltBed3D::compute_belt_transform() const
{
    if (!m_belt_profile_loaded) {
        return Transform3d::Identity();
    }
    
    // Rotate the bed to match the belt gantry angle (typically 45 degrees)
    // This provides a visual representation consistent with the physical machine
    double angle_rad = Slic3r::Geometry::deg2rad(m_belt_profile.gantry_angle_theta_deg);
    return Eigen::AngleAxisd(angle_rad, Vec3d::UnitX()) * Transform3d::Identity();
}

void BeltBed3D::render(GLCanvas3D& canvas, const Transform3d& view_matrix, const Transform3d& projection_matrix,
                       bool bottom, float scale_factor, bool show_axes)
{
    // Check if this is a belt printer
    if (!m_belt_profile_loaded) {
        // Not a belt printer or profile not loaded, use default rendering
        Bed3D::render(canvas, view_matrix, projection_matrix, bottom, scale_factor, show_axes);
        return;
    }
    
    // CRITICAL: Apply SAME transform in BOTH Prepare and Preview
    // This ensures object position consistency
    Transform3d belt_transform = compute_belt_transform();
    
    // Render with belt-aware logic
    // For now, delegate to parent but with our transform
    // TODO: Implement custom belt bed rendering
    Bed3D::render(canvas, view_matrix * belt_transform, projection_matrix, bottom, scale_factor, show_axes);
    
    BOOST_LOG_TRIVIAL(debug) << "BeltBed3D: Rendered with belt transform (canvas type: " 
                             << (canvas.get_canvas_type() == GLCanvas3D::CanvasPreview ? "Preview" : "Prepare") << ")";
}

void BeltBed3D::render_belt_bed(const Transform3d& view_matrix, const Transform3d& projection_matrix)
{
    // TODO: Implement custom belt bed rendering
    // This will:
    // 1. Create long/infinite bed geometry along belt axis
    // 2. Add grid lines showing belt direction
    // 3. Optionally add belt texture
    // 4. Render using our BeltPrinter profile dimensions
    
    BOOST_LOG_TRIVIAL(info) << "BeltBed3D: Custom belt bed rendering not yet implemented";
}

} // namespace GUI
} // namespace Slic3r
