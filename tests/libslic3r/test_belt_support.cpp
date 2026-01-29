#include <catch2/catch_all.hpp>
#include <libslic3r/Support/SupportMaterial.hpp>
#include <libslic3r/Model.hpp>
#include <libslic3r/Print.hpp>
#include <libslic3r/Geometry.hpp>
#include <libslic3r/Utils.hpp>

using namespace Slic3r;

TEST_CASE("Belt support trimming", "[belt_support]") {
    // 1. Setup Configuration
    DynamicPrintConfig print_config;
    print_config.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.4}));
    print_config.set_key_value("filament_diameter", new ConfigOptionFloats({1.75}));
    print_config.set_key_value("layer_height", new ConfigOptionFloat(0.2));
    print_config.set_key_value("first_layer_height", new ConfigOptionFloat(0.2));
    print_config.set_key_value("skirts", new ConfigOptionInt(0));
    
    // Enable Belt Printer
    print_config.set_key_value("belt_printer", new ConfigOptionBool(true));
    print_config.set_key_value("belt_angle", new ConfigOptionFloat(45.0));
    // Usually Y axis is the default for belt motion in Orca/S3D
    // Assuming default belt_axis is Y (implied by logic if not set, or default enum)
    
    // 2. Mock Model and Print Object
    Model model;
    ModelObject* mod_obj = model.add_object();
    mod_obj->add_volume(TriangleMesh()); // dummy
    
    Print print;
    print.apply(model, print_config);
    print.validate(); // Ensure config is consistent
    
    PrintObject* print_object = print.get_object(0);
    
    // 3. Initialize SupportMaterial
    SlicingParameters slicing_params = print_object->slicing_parameters();
    PrintObjectSupportMaterial support_material(print_object, slicing_params);
    
    // 4. Create a Support Layer
    SupportGeneratorLayerStorage storage;
    SupportGeneratorLayer& layer = storage.allocate(SupporLayerType::Base);
    layer.print_z = 10.0; // Z = 10.0 mm
    layer.height = 0.2;
    layer.bottom_z = 9.8;
    
    // Create a polygon spanning Y from -20 to +20.
    // X from 0 to 10.
    // Belt Mask should cut everything where Y <= Z * tan(45) = 10.0 * 1.0 = 10.0.
    // So the resulting polygon should start at Y >= 10.0 (minus/plus tolerance).
    // The implementation subtracts { Y <= belt_pos - threshold }. 
    // Threshold is 0.2. Belt pos = 10.0. Limit = 9.8.
    // So it subtracts Y <= 9.8.
    // So the polygon should be cut at Y=9.8.
    
    Polygon poly;
    poly.points.reserve(4);
    poly.points.push_back(Point(coord_t(0), coord_t(scale_(-20.0))));
    poly.points.push_back(Point(coord_t(scale_(10.0)), coord_t(scale_(-20.0))));
    poly.points.push_back(Point(coord_t(scale_(10.0)), coord_t(scale_(20.0))));
    poly.points.push_back(Point(coord_t(0), coord_t(scale_(20.0))));
    
    layer.polygons.clear();
    layer.polygons.push_back(poly);
    
    SupportGeneratorLayersPtr layers;
    layers.push_back(&layer);
    
    // 5. Call trimming function
    // gaps are 0 for simplicity
    support_material.trim_support_layers_by_object(*print_object, layers, 0.0, 0.0, 0.0);
    
    // 6. Verify result
    REQUIRE(layers.size() == 1);
    REQUIRE(!layers[0]->polygons.empty());
    
    BoundingBox bbox = get_extents(layers[0]->polygons);
    double min_y = unscale<double>(bbox.min.y());
    
    // Expected: The box starts around Y = 10.0 (the belt plane).
    // But implementation logic says:
    // belt_limit = scale_(belt_pos - threshold)
    // belt_mask removes Y <= belt_limit.
    // So resulting Y must be > belt_limit.
    // belt_pos = 10.0. threshold = 0.2. belt_limit = 9.8.
    // So result min_y should be approx 9.8.
    
    INFO("Layer Z: " << layer.print_z);
    INFO("Belt Angle: " << print.config().belt_angle.value);
    INFO("Min Y after trim: " << min_y);
    
    CHECK(min_y >= Catch::Approx(9.8).margin(0.01));
    CHECK(min_y < Catch::Approx(10.0).margin(0.2)); // Shouldn't be too far
    
    // Test with Z=0 (Contact with start of belt)
    SupportGeneratorLayer& layer0 = storage.allocate(SupporLayerType::Base);
    layer0.print_z = 0.2; // First layer
    layer0.height = 0.2;
    layer0.bottom_z = 0.0;
    
    // Polygon at Y=0 centered
    poly.points.clear();
    poly.points.push_back(Point(coord_t(0), coord_t(scale_(-10.0))));
    poly.points.push_back(Point(coord_t(scale_(10.0)), coord_t(scale_(-10.0))));
    poly.points.push_back(Point(coord_t(scale_(10.0)), coord_t(scale_(10.0))));
    poly.points.push_back(Point(coord_t(0), coord_t(scale_(10.0))));

    layer0.polygons.clear();
    layer0.polygons.push_back(poly);

    SupportGeneratorLayersPtr layers0;
    layers0.push_back(&layer0);
    
    support_material.trim_support_layers_by_object(*print_object, layers0, 0.0, 0.0, 0.0);
    
    // Z = 0.2. Belt pos = 0.2. Threshold = 0.2. Limit = 0.0.
    // Sub mask Y <= 0.0.
    // Result min_y should be approx 0.0.
    if (!layers0[0]->polygons.empty()) {
        bbox = get_extents(layers0[0]->polygons);
        min_y = unscale<double>(bbox.min.y());
        INFO("Layer 0 Min Y: " << min_y);
        CHECK(min_y >= Catch::Approx(0.0).margin(0.01));
    } else {
        // If empty, it means everything was trimmed (Y < 0).
        // Our poly goes from -10 to 10. Mask removes Y<=0.
        // It should leave 0 to 10.
        FAIL("Layer 0 polygons shouldn't be empty");
    }
}
