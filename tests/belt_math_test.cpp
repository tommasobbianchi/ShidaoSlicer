#include <iostream>
#include <cmath>
#include <Eigen/Dense>
#include <Eigen/Geometry>

// Minimal types to check logic
typedef Eigen::Vector3d Vec3d;
typedef Eigen::Transform<double, 3, Eigen::Affine> Transform3d;

double deg2rad(double deg) { return deg * M_PI / 180.0; }

int main() {
    // 1. Config
    double belt_angle = 45.0;
    double angle_rad = deg2rad(belt_angle);
    double s = std::sin(angle_rad);
    double c = std::cos(angle_rad);

    // Normal roughly Forward-Up (Y-Up Belt)
    // Belt Axis Y. Normal has (0, Y, Z) components.
    // If Belt is Y (Forward), Bed is Z (Up).
    // Gantry is 45 deg Up/Back.
    // Slicing Plane Normal is 45 deg Up/Forward.
    Vec3d normal(0, s, c);
    std::cout << "Normal: " << normal.transpose() << std::endl;

    // 2. TriangleMeshSlicer Rotation Logic
    Vec3d z_axis(0, 0, 1);
    Eigen::Matrix3d rot = Eigen::Quaterniond::FromTwoVectors(normal, z_axis).toRotationMatrix();
    Transform3d basis_change = Transform3d::Identity();
    basis_change.rotate(rot);

    std::cout << "Basis Change Matrix (Linear):\n" << basis_change.linear() << std::endl;

    // 3. Test Point: Vertical Tower Point
    // P_world at height 100 on Z.
    Vec3d p_world(0, 0, 100); 
    Vec3d p_slice = basis_change * p_world;
    
    std::cout << "P_world: " << p_world.transpose() << std::endl;
    std::cout << "P_slice: " << p_slice.transpose() << std::endl;

    // 4. GCode Shear Logic (My implementation)
    // tan = normal.y / normal.z
    double tan_alpha = normal.y() / normal.z();
    std::cout << "Tan Alpha: " << tan_alpha << std::endl;

    double scale_z = 1.0 / normal.z();
    std::cout << "Scale Z: " << scale_z << std::endl;

    // Shear Calculation
    // Y_gcode = Y_slice + Z_slice * tan
    // Z_gcode = Z_slice * scale_z
    
    double y_slice = p_slice.y();
    double z_slice = p_slice.z();

    double y_gcode = y_slice + z_slice * tan_alpha;
    double z_gcode = z_slice * scale_z;

    std::cout << "Y_gcode (Should be 0 for Vertical): " << y_gcode << std::endl;
    std::cout << "Z_gcode (Should be 100 for Vertical): " << z_gcode << std::endl;

    // 5. Test Inverse Normal (Back-Facing)
    std::cout << "\n--- Test Inverse Normal ---" << std::endl;
    Vec3d normal_inv(0, -s, c); // Back-Up
    std::cout << "Normal Inv: " << normal_inv.transpose() << std::endl;
    
    rot = Eigen::Quaterniond::FromTwoVectors(normal_inv, z_axis).toRotationMatrix();
    basis_change = Transform3d::Identity();
    basis_change.rotate(rot);
    
    p_slice = basis_change * p_world;
    std::cout << "P_slice Inv: " << p_slice.transpose() << std::endl;
    
    tan_alpha = normal_inv.y() / normal_inv.z(); // -s / c = -tan
    std::cout << "Tan Alpha Inv: " << tan_alpha << std::endl;
    
    y_slice = p_slice.y();
    z_slice = p_slice.z();
    y_gcode = y_slice + z_slice * tan_alpha;
    std::cout << "Y_gcode Inv: " << y_gcode << std::endl;

    return 0;
}
