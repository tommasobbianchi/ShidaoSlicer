#include "BeltTransform.hpp"
#include <cmath>
#include "Geometry.hpp"
#include <fstream>
#include <iostream>
#include <string>
#include <algorithm>

namespace Slic3r {

struct BeltConfig {
    // IdeaFormer IR3 V2: X=lateral, Y=gantry(45° to belt surface), Z=belt(infinite)
    //
    // Forward transform: Machine → Virtual (for slicing)
    //   Y_virt = Z_mach, Z_virt = Y_mach + Z_mach
    double f_yy = 0.0;
    double f_yz = 1.0;
    double f_zy = 1.0;
    double f_zz = 1.0;

    // Inverse transform: Virtual → Machine (for G-code output)
    // With compute_belt_inclined_z (Z_input = m_nominal_z + Y_gcode):
    //   Y_mach = (i_yy+i_yz)*Y_gcode + i_yz*m_nominal_z + y_mach_offset
    //   Z_mach = (i_zy+i_zz)*Y_gcode + i_zz*m_nominal_z + z_mach_offset
    // i_yy+i_yz=0 keeps Y_mach constant per layer.
    // i_yz=√2 gives ΔY_mach = √2 × Δlayer = 0.283mm per 0.2mm layer (45° gantry scaling).
    double i_yy = -1.41421356; // -√2
    double i_yz =  1.41421356; //  √2
    double i_zy =  1.0;
    double i_zz =  0.0;

    double f_y_shift = 0.0;
    double i_y_shift = 0.0;
    double f_z_shift = 0.0;
    double i_z_shift = 0.0;
    double z_mach_offset = 2.5;     // Z offset for belt position (ensures positive Z_mach after prime)
    double y_mach_offset = 0.0;     // Y offset: 0 → first layer at Y=0.283 (correct belt-normal)
    double trafo_z_shift = -990.0;  // Z-shift applied in trafo_centered() after belt transform

    bool loaded = false;
    
    void load() {
        if (loaded) return;
        std::ifstream f("/home/user/projects/ORCA_BELT/belt_transform.ini");
        if (f.is_open()) {
            std::string line;
            while (std::getline(f, line)) {
                if (line.empty() || line[0] == '#') continue;
                auto pos = line.find('=');
                if (pos != std::string::npos) {
                    std::string key = line.substr(0, pos);
                    // trim key
                    key.erase(0, key.find_first_not_of(" \t"));
                    key.erase(key.find_last_not_of(" \t") + 1);
                    double val = 0.0;
                    try {
                        val = std::stod(line.substr(pos + 1));
                    } catch (...) { continue; }
                    
                    if (key == "f_yy") f_yy = val;
                    else if (key == "f_yz") f_yz = val;
                    else if (key == "f_zy") f_zy = val;
                    else if (key == "f_zz") f_zz = val;
                    else if (key == "i_yy") i_yy = val;
                    else if (key == "i_yz") i_yz = val;
                    else if (key == "i_zy") i_zy = val;
                    else if (key == "i_zz") i_zz = val;
                    else if (key == "f_y_shift") f_y_shift = val;
                    else if (key == "i_y_shift") i_y_shift = val;
                    else if (key == "f_z_shift") f_z_shift = val;
                    else if (key == "i_z_shift") i_z_shift = val;
                    else if (key == "trafo_z_shift") trafo_z_shift = val;
                    else if (key == "z_mach_offset") z_mach_offset = val;
                    else if (key == "y_mach_offset") y_mach_offset = val;
                    // Legacy support or alias
                    else if (key == "y_shift") { f_y_shift = val; i_y_shift = val; }
                }
            }
        }
        loaded = true;
    }
};

static BeltConfig g_belt_config;

void ensure_config() {
    g_belt_config.load();
}

Transform3d BeltTransform::make_forward_transform(double angle_degrees)
{
    ensure_config();
    // Forward Transform: Machine -> Virtual
    Transform3d t = Transform3d::Identity();

    // Linear part
    t.matrix()(1, 1) = g_belt_config.f_yy; 
    t.matrix()(1, 2) = g_belt_config.f_yz;
    t.matrix()(2, 1) = g_belt_config.f_zy; 
    t.matrix()(2, 2) = g_belt_config.f_zz;
    
    // Translation: Y_virt += f_y_shift
    // Typically used to center the object (remove Machine Y offset)
    t.translate(Vec3d(0, g_belt_config.f_y_shift, 0));
    
    return t;
}

Transform3d BeltTransform::make_inverse_transform(double angle_degrees)
{
    ensure_config();
    // Inverse Transform: Virtual -> Machine
    
    Transform3d t = Transform3d::Identity();
    
    // Linear part
    t.matrix()(1, 1) = g_belt_config.i_yy;
    t.matrix()(1, 2) = g_belt_config.i_yz;
    t.matrix()(2, 1) = g_belt_config.i_zy;     
    t.matrix()(2, 2) = g_belt_config.i_zz;
    
    // Apply shift: Linear * Translate(-i_y_shift)
    t.translate(Vec3d(0, -g_belt_config.i_y_shift, 0));
    
    return t;
}

Vec3d BeltTransform::inverse_transform_point(const Vec3d& pt, double angle_degrees)
{
    if (angle_degrees == 0.0) return pt;
    ensure_config();

    // Add back shifts (to undo forward transform's subtractions)
    double y_virt = pt.y() - g_belt_config.i_y_shift;
    double z_virt = pt.z() + g_belt_config.i_z_shift;

    // Then apply inverse linear transform
    double y_mach = g_belt_config.i_yy * y_virt + g_belt_config.i_yz * z_virt + g_belt_config.y_mach_offset;
    double z_mach = g_belt_config.i_zy * y_virt + g_belt_config.i_zz * z_virt + g_belt_config.z_mach_offset;

    return Vec3d(pt.x(), y_mach, z_mach);
}

double BeltTransform::get_trafo_z_shift()
{
    ensure_config();
    return g_belt_config.trafo_z_shift;
}

void BeltTransform::reload_config()
{
    g_belt_config.loaded = false;
    ensure_config();
}

}
