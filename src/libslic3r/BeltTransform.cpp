#include "BeltTransform.hpp"
#include <cmath>
#include "Geometry.hpp"
#include <fstream>
#include <iostream>
#include <string>
#include <algorithm>

namespace Slic3r {

// ============================================================================
// LOCKED TRANSFORM COEFFICIENTS — derived from IdeaFormer IR3 V2 (CoreXY, no
// firmware belt compensation). Fixed 2026-02-23: old f_zy=+0.707, i_zy=-1.0
// caused 65° ZY shear on physical prints (belt moved during gantry sweep).
// ============================================================================
//
// Forward: model → virtual slicing space
//   Y_virt = Y_model / √2                 (project height onto gantry axis)
//   Z_virt = -Y_model + Z_model           (compensates 45° gantry arm depth)
//
// Inverse: virtual gcode → machine coordinates
//   Y_mach = 2 × Y_gcode                  (gantry travel along 45° incline)
//   Z_mach = Z_gcode                       (belt position = constant per layer)
//
// Physical geometry proof (f_zy=-1, i_zy=0):
//   depth_phys = Z_mach + Y_mach/√2 = (-Y+Z) + √2×Y/√2 = Z  ← correct!
//   height_phys = Y_mach/√2 = √2×Y/√2 = Y                    ← correct!
// With f_zy=+1: depth = 2Y+Z (sheared). With f_zy=+0.707: depth = 1.707Y+Z (sheared).
// Only f_zy=-1 gives depth = Z_model (no shear, 90° angles).
//
// trafo_centered must NOT shift Z_virt: keel (Y=0) is naturally at Z_virt=0.
// Front face overhang (Z_virt<0) is clipped — inherent 45° belt limitation.
//
static constexpr double BELT_F_YY =  0.70710678;   // cos(45°) = 1/√2
static constexpr double BELT_F_YZ =  0.0;
static constexpr double BELT_F_ZY = -1.0;           // Z_virt = -Y + Z (depth = Z_model, no shear)
static constexpr double BELT_F_ZZ =  1.0;

static constexpr double BELT_I_YY =  2.0;           // gantry travel = 2 × Y_gcode
static constexpr double BELT_I_YZ =  0.0;
static constexpr double BELT_I_ZY =  0.0;           // Z_mach = Z_gcode (no Y coupling)
static constexpr double BELT_I_ZZ =  1.0;

// Tunable offsets — these CAN be adjusted via belt_transform.ini
struct BeltConfig {
    double f_y_shift = 0.0;
    double i_y_shift = 0.0;
    double f_z_shift = 0.0;
    double i_z_shift = 0.0;
    double z_mach_offset = 0.0;     // Z offset applied to Z_mach
    double y_mach_offset = 0.0;     // Y offset applied to Y_mach
    double trafo_z_shift = 0.0;     // Z-shift in trafo_centered()

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
                    key.erase(0, key.find_first_not_of(" \t"));
                    key.erase(key.find_last_not_of(" \t") + 1);
                    double val = 0.0;
                    try {
                        val = std::stod(line.substr(pos + 1));
                    } catch (...) { continue; }

                    // Only tunable offsets — transform coefficients are LOCKED
                    if      (key == "f_y_shift")     f_y_shift = val;
                    else if (key == "i_y_shift")     i_y_shift = val;
                    else if (key == "f_z_shift")     f_z_shift = val;
                    else if (key == "i_z_shift")     i_z_shift = val;
                    else if (key == "trafo_z_shift") trafo_z_shift = val;
                    else if (key == "z_mach_offset") z_mach_offset = val;
                    else if (key == "y_mach_offset") y_mach_offset = val;
                    else if (key == "y_shift") { f_y_shift = val; i_y_shift = val; }
                    // Transform coefficients (f_yy, i_yy, etc.) are intentionally
                    // NOT loaded from ini — they are locked constants above.
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
    Transform3d t = Transform3d::Identity();

    t.matrix()(1, 1) = BELT_F_YY;
    t.matrix()(1, 2) = BELT_F_YZ;
    t.matrix()(2, 1) = BELT_F_ZY;
    t.matrix()(2, 2) = BELT_F_ZZ;

    t.translate(Vec3d(0, g_belt_config.f_y_shift, 0));

    return t;
}

Transform3d BeltTransform::make_inverse_transform(double angle_degrees)
{
    ensure_config();
    Transform3d t = Transform3d::Identity();

    t.matrix()(1, 1) = BELT_I_YY;
    t.matrix()(1, 2) = BELT_I_YZ;
    t.matrix()(2, 1) = BELT_I_ZY;
    t.matrix()(2, 2) = BELT_I_ZZ;

    t.translate(Vec3d(0, -g_belt_config.i_y_shift, 0));

    return t;
}

Vec3d BeltTransform::inverse_transform_point(const Vec3d& pt, double angle_degrees)
{
    if (angle_degrees == 0.0) return pt;
    ensure_config();

    double y_virt = pt.y() - g_belt_config.i_y_shift;
    double z_virt = pt.z() + g_belt_config.i_z_shift;

    double y_mach = BELT_I_YY * y_virt + BELT_I_YZ * z_virt + g_belt_config.y_mach_offset;
    double z_mach = BELT_I_ZY * y_virt + BELT_I_ZZ * z_virt + g_belt_config.z_mach_offset;

    // Clamp Y_mach >= 0 — gantry cannot go below belt surface.
    if (y_mach < 0.0)
        y_mach = 0.0;

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
