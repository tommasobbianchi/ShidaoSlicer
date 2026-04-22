#include "MCP/CommandDispatch.h"
#include "MCP/ToolSchemas.h"
#include "GUI/GUI_App.hpp"
#include "GUI/MainFrame.hpp"
#include "GUI/Plater.hpp"
#include "GUI/GLCanvas3D.hpp"
#include "GUI/Camera.hpp"
#include "GUI/GCodeViewer.hpp"
#include "GUI/GUI_Preview.hpp"
#include "GUI/IMSlider.hpp"
#include "GUI/MainFrame.hpp"
#include <cmath>
#include <wx/window.h>
#include "libslic3r/Model.hpp"
#include "libslic3r/TriangleMesh.hpp"
#include "libslic3r/PrintConfig.hpp"
#include "libslic3r/Print.hpp"
#include "libslic3r/GCode/ThumbnailData.hpp"
#include <miniz.h>
#include <GL/glew.h>

#include <future>
#include <set>
#include <wx/app.h>
#include "GUI/OpenGLManager.hpp"
#include "GUI/Tab.hpp"

using namespace nlohmann;

namespace Slic3r { namespace GUI {

// Helper: build a JSON response
static McpApiServer::Response json_response(const std::string& body, int status = 200) {
    McpApiServer::Response resp;
    resp.status_code = status;
    resp.status_text = (status == 200) ? "OK" : "Bad Request";
    resp.content_type = "application/json";
    resp.body = body;
    return resp;
}

CommandDispatch& CommandDispatch::instance() {
    static CommandDispatch inst;
    return inst;
}

CommandDispatch::json CommandDispatch::call_on_gui_thread(std::function<json()> fn) {
    std::promise<json> promise;
    auto future = promise.get_future();
    wxGetApp().CallAfter([&promise, fn = std::move(fn)]() {
        try {
            promise.set_value(fn());
        } catch (const std::exception& e) {
            json err;
            err["error"] = e.what();
            promise.set_value(err);
        }
    });
    return future.get();
}

void CommandDispatch::register_command(const std::string& action, handler_fn fn) {
    m_commands[action] = std::move(fn);
}

CommandDispatch::json CommandDispatch::dispatch(const std::string& action, const json& params) {
    auto it = m_commands.find(action);
    if (it == m_commands.end()) {
        return json{{"error", "Unknown action: " + action}};
    }
    return it->second(params);
}

static int parse_query_int(const std::string& url, const std::string& key, int default_val) {
    auto pos = url.find(key + "=");
    if (pos == std::string::npos) return default_val;
    pos += key.size() + 1;
    auto end = url.find('&', pos);
    std::string val = (end == std::string::npos) ? url.substr(pos) : url.substr(pos, end - pos);
    try { return std::stoi(val); } catch (...) { return default_val; }
}

McpApiServer::Response CommandDispatch::handle_screenshot(const std::string& url) {
    std::string mode = "viewport";
    {
        auto pos = url.find("mode=");
        if (pos != std::string::npos) {
            auto end = url.find('&', pos + 5);
            mode = (end == std::string::npos) ? url.substr(pos + 5) : url.substr(pos + 5, end - pos - 5);
        }
    }

    int req_width = parse_query_int(url, "width", 0);
    int req_height = parse_query_int(url, "height", 0);

    std::vector<unsigned char> png_bytes;
    std::string error_msg;
    bool ok = false;

    call_on_gui_thread([&]() -> json {
        auto* plater = wxGetApp().plater();
        if (!plater) { error_msg = "No plater"; return json{}; }

        auto* canvas = plater->get_view3D_canvas3D();
        if (!canvas) { error_msg = "No canvas"; return json{}; }

        // Ensure GL context is current and scene is rendered
        canvas->set_as_dirty();
        canvas->render();

        if (mode == "thumbnail") {
            // Legacy FBO thumbnail mode
            int tw = (req_width > 0) ? std::max(64, std::min(req_width, 2048)) : 800;
            int th = (req_height > 0) ? std::max(64, std::min(req_height, 2048)) : 600;

            ThumbnailData thumb;
            auto& plate_list = plater->get_partplate_list();
            ThumbnailsParams params = { {}, false, true, true, true,
                                        plate_list.get_curr_plate_index() };
            canvas->render_thumbnail(thumb, (unsigned)tw, (unsigned)th,
                                     params, Camera::EType::Ortho);

            if (!thumb.is_valid() || thumb.pixels.empty()) {
                error_msg = "Thumbnail render produced no data";
                return json{};
            }

            size_t png_size = 0;
            void* png_data = tdefl_write_image_to_png_file_in_memory_ex(
                thumb.pixels.data(), thumb.width, thumb.height, 4,
                &png_size, MZ_DEFAULT_LEVEL, 1);

            if (png_data && png_size > 0) {
                png_bytes.assign((unsigned char*)png_data,
                                 (unsigned char*)png_data + png_size);
                mz_free(png_data);
                ok = true;
            } else {
                error_msg = "PNG encoding failed";
            }
        } else {
            // Default: capture actual viewport via glReadPixels
            Size cnv_size = canvas->get_canvas_size();
            int vp_w = cnv_size.get_width();
            int vp_h = cnv_size.get_height();

            if (vp_w <= 0 || vp_h <= 0) {
                error_msg = "Canvas size is zero";
                return json{};
            }

            // Unbind any FBO to ensure we read from the default framebuffer
            glsafe(::glBindFramebuffer(GL_FRAMEBUFFER, 0));

            std::vector<unsigned char> pixels(vp_w * vp_h * 4);
            glsafe(::glReadPixels(0, 0, vp_w, vp_h, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data()));

            // Encode to PNG (flip=1 for GL bottom-up to top-down)
            size_t png_size = 0;
            void* png_data = tdefl_write_image_to_png_file_in_memory_ex(
                pixels.data(), vp_w, vp_h, 4,
                &png_size, MZ_DEFAULT_LEVEL, 1);

            if (png_data && png_size > 0) {
                png_bytes.assign((unsigned char*)png_data,
                                 (unsigned char*)png_data + png_size);
                mz_free(png_data);
                ok = true;
            } else {
                error_msg = "PNG encoding failed";
            }
        }
        return json{};
    });

    if (!ok) {
        json resp;
        resp["ok"] = false;
        resp["error"] = error_msg.empty() ? "Screenshot capture failed" : error_msg;
        return json_response(resp.dump(), 500);
    }

    McpApiServer::Response resp;
    resp.status_code = 200;
    resp.status_text = "OK";
    resp.content_type = "image/png";
    resp.is_binary = true;
    resp.binary_body = std::move(png_bytes);
    return resp;
}

McpApiServer::Response CommandDispatch::handle_api_request(
    const std::string& method, const std::string& url, const std::string& body,
    const std::map<std::string, std::string>& headers)
{
    // MCP protocol endpoint
    if (method == "POST" && url == "/mcp") {
        return m_mcp_protocol.handle_mcp_request(body, headers);
    }

    // GET /api/screenshot?width=W&height=H
    if (url.find("/api/screenshot") == 0) {
        return handle_screenshot(url);
    }

    // POST /api/execute
    if (url.find("/api/execute") == 0 && method == "POST") {
        try {
            auto req = json::parse(body);
            std::string action = req.value("action", "");
            json params = req.value("params", json::object());

            json result = dispatch(action, params);

            if (result.contains("error") && !result.contains("ok")) {
                json resp;
                resp["ok"] = false;
                resp["error"] = result["error"];
                return json_response(resp.dump(), 400);
            }

            json resp;
            resp["ok"] = true;
            resp["result"] = result;
            return json_response(resp.dump());
        } catch (const json::exception& e) {
            json resp;
            resp["ok"] = false;
            resp["error"] = std::string("JSON parse error: ") + e.what();
            return json_response(resp.dump(), 400);
        }
    }

    // Unknown route
    json resp;
    resp["ok"] = false;
    resp["error"] = "Not found: " + url;
    return json_response(resp.dump(), 404);
}

// ---------------------------------------------------------------------------
// Model commands
// ---------------------------------------------------------------------------
void CommandDispatch::register_model_commands() {
    register_command("model.list", [this](const json& /*params*/) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* plater = wxGetApp().plater();
            const auto& model = plater->model();
            json objects = json::array();
            for (size_t i = 0; i < model.objects.size(); ++i) {
                const auto* obj = model.objects[i];
                json o;
                o["index"] = i;
                o["name"] = obj->name;
                o["volumes"] = obj->volumes.size();
                auto bb = obj->bounding_box_approx();
                o["bounding_box"] = {
                    {"min", {bb.min.x(), bb.min.y(), bb.min.z()}},
                    {"max", {bb.max.x(), bb.max.y(), bb.max.z()}}
                };
                objects.push_back(o);
            }
            return json{{"objects", objects}};
        });
    });

    register_command("model.add_primitive", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            std::string type = params.value("type", "cube");
            double x = params.value("x", 10.0);
            double y = params.value("y", 10.0);
            double z = params.value("z", 10.0);

            TriangleMesh mesh;
            if (type == "cube")
                mesh = make_cube(x, y, z);
            else if (type == "cylinder")
                mesh = make_cylinder(x, z); // x=radius, z=height
            else if (type == "sphere")
                mesh = make_sphere(x);      // x=radius
            else
                return json{{"error", "Unknown primitive type: " + type}};

            auto* plater = wxGetApp().plater();
            auto& model = plater->model();

            ModelObject* obj = model.add_object();
            obj->name = type + "_" + std::to_string(model.objects.size());
            obj->add_volume(std::move(mesh));
            obj->add_instance();

            // Register new instance with the current plate so has_printable_instances()
            // returns true and slicing / preview work. Without this the plate's
            // obj_to_instance_set stays empty and set_current_panel's do_reslice
            // lambda resets the gcode toolpaths at Plater.cpp:8608.
            int new_obj_idx = (int)model.objects.size() - 1;
            for (size_t i = 0; i < obj->instances.size(); ++i)
                plater->get_partplate_list().notify_instance_update(new_obj_idx, (int)i, true);

            // Reload the 3D scene so GL volumes are created
            plater->get_view3D_canvas3D()->reload_scene(true, true);

            json result;
            result["object_index"] = new_obj_idx;
            result["name"] = obj->name;
            return result;
        });
    });

    register_command("model.load_file", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            std::string path = params.value("path", "");
            if (path.empty())
                return json{{"error", "No path provided"}};

            // Bypass Plater::load_files to avoid modal dialogs (version check,
            // restore previous project, 3MF customized preset warnings, etc.)
            // that block MCP clients running under xvfb/headless contexts.
            Model loaded;
            try {
                loaded = Model::read_from_file(
                    path, nullptr, nullptr,
                    LoadStrategy::AddDefaultInstances | LoadStrategy::LoadModel);
            } catch (const std::exception& e) {
                return json{{"error", std::string("Failed to load: ") + e.what()}};
            }

            if (loaded.objects.empty())
                return json{{"error", "File contained no objects: " + path}};

            auto* plater = wxGetApp().plater();
            auto& model = plater->model();
            size_t start_index = model.objects.size();

            // ORCA_BELT: detect belt printer — if so we'll keel-align below.
            bool is_belt = false;
            if (auto* bundle = wxGetApp().preset_bundle) {
                const auto& pcfg = bundle->printers.get_edited_preset().config;
                if (auto* ps = pcfg.option<ConfigOptionEnum<PrinterStructure>>("printer_structure"))
                    is_belt = (ps->value == psBelt);
            }
            // Compute bed center X (for belt placement). Build volume is in plate coords.
            double bed_center_x = 0.0;
            if (is_belt) {
                auto bb2d = plater->build_volume().bounding_volume2d();
                bed_center_x = (bb2d.min.x() + bb2d.max.x()) * 0.5;
            }

            for (ModelObject* obj : loaded.objects) {
                ModelObject* new_obj = model.add_object(*obj);
                if (new_obj->instances.empty())
                    new_obj->add_instance();

                // ORCA_BELT: place centered meshes at (X=bed_center, Y_min=0, Z_min=0)
                // so they sit flush on the belt keel with X centered. Without this,
                // MCP-loaded meshes end up at world origin (X=0, Y=±extent/2), which
                // puts half the mesh off the belt's X range [0, 250] and below the
                // keel at Y<0 — Orca refuses to slice with "over the boundary".
                if (is_belt && !new_obj->instances.empty()) {
                    ModelInstance* inst = new_obj->instances.back();
                    BoundingBoxf3 wbb = new_obj->instance_bounding_box(
                        new_obj->instances.size() - 1);
                    Vec3d off = inst->get_offset();
                    // Center X on the belt bed center
                    double mesh_cx = (wbb.min.x() + wbb.max.x()) * 0.5;
                    off.x() += (bed_center_x - mesh_cx);
                    // Keel-align Y and Z
                    if (wbb.min.y() < 0.0) off.y() -= wbb.min.y();
                    if (wbb.min.z() < 0.0) off.z() -= wbb.min.z();
                    inst->set_offset(off);
                }
            }

            // Register all new instances with the current plate (see add_primitive).
            auto& plates = plater->get_partplate_list();
            for (size_t i = start_index; i < model.objects.size(); ++i) {
                ModelObject* o = model.objects[i];
                for (size_t k = 0; k < o->instances.size(); ++k)
                    plates.notify_instance_update((int)i, (int)k, true);
            }

            plater->get_view3D_canvas3D()->reload_scene(true, true);

            json result;
            result["loaded_objects"] = loaded.objects.size();
            json indices = json::array();
            for (size_t i = start_index; i < model.objects.size(); ++i)
                indices.push_back(i);
            result["object_indices"] = indices;
            return result;
        });
    });

    register_command("model.delete", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            int index = params.value("index", -1);
            auto* plater = wxGetApp().plater();
            if (index < 0 || index >= (int)plater->model().objects.size())
                return json{{"error", "Invalid object index"}};
            plater->delete_object_from_model(index);
            return json{{"deleted", index}};
        });
    });

    register_command("model.transform", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            int index = params.value("index", -1);
            auto* plater = wxGetApp().plater();
            auto& model = plater->model();
            if (index < 0 || index >= (int)model.objects.size())
                return json{{"error", "Invalid object index"}};

            auto* obj = model.objects[index];
            if (obj->instances.empty())
                return json{{"error", "Object has no instances"}};

            auto* inst = obj->instances[0];

            // Apply rotation/scale first so the bbox used by pivot is correct.
            if (params.contains("scale")) {
                auto s = params["scale"];
                inst->set_scaling_factor(Vec3d(s[0].get<double>(), s[1].get<double>(), s[2].get<double>()));
            }
            if (params.contains("rotate")) {
                auto r = params["rotate"];
                // MCP schema documents rotate as DEGREES; ModelInstance::set_rotation
                // expects RADIANS. Convert — otherwise e.g. rotate=[0,0,90] winds up
                // applying 90 radians (≈ 116.7° mod 2π) instead of a clean 90°.
                constexpr double d2r = M_PI / 180.0;
                inst->set_rotation(Vec3d(
                    r[0].get<double>() * d2r,
                    r[1].get<double>() * d2r,
                    r[2].get<double>() * d2r));
            }

            if (params.contains("translate")) {
                auto t = params["translate"];
                Vec3d target(t[0].get<double>(), t[1].get<double>(), t[2].get<double>());
                // pivot selects which point of the instance's world-space bbox the
                // target refers to. Primitives (make_cube) sit with origin at the
                // mesh MIN corner; loaded meshes often have an origin near their
                // bbox center — the default "as-is" keeps the historical behavior.
                std::string pivot = params.value("pivot", std::string("as-is"));
                if (pivot == "as-is") {
                    inst->set_offset(target);
                } else {
                    BoundingBoxf3 bb = obj->instance_bounding_box(0, /*dont_translate=*/true);
                    Vec3d ref;
                    if (pivot == "min")         ref = bb.min;
                    else if (pivot == "max")    ref = bb.max;
                    else if (pivot == "center") ref = 0.5 * (bb.min + bb.max);
                    else if (pivot == "bed-min") {
                        // Land bbox.min_z on the bed; XY uses min corner.
                        ref = Vec3d(bb.min.x(), bb.min.y(), bb.min.z());
                        target = Vec3d(target.x(), target.y(), 0.0);
                    } else {
                        return json{{"error", "Unknown pivot: " + pivot +
                            " (valid: as-is, min, max, center, bed-min)"}};
                    }
                    inst->set_offset(target - ref);
                }
            }

            obj->invalidate_bounding_box();
            plater->update();

            json result;
            result["transformed"] = index;
            auto final_bb = obj->instance_bounding_box(0);
            result["bounding_box"] = {
                {"min", {final_bb.min.x(), final_bb.min.y(), final_bb.min.z()}},
                {"max", {final_bb.max.x(), final_bb.max.y(), final_bb.max.z()}}
            };
            return result;
        });
    });

    register_command("model.export", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            std::string path = params.value("path", "");
            std::string format = params.value("format", "3mf");
            if (path.empty())
                return json{{"error", "No path provided"}};

            auto* plater = wxGetApp().plater();
            if (format == "3mf") {
                int result = plater->export_3mf(boost::filesystem::path(path));
                if (result < 0)
                    return json{{"error", "Failed to export 3MF"}};
                return json{{"exported", path}, {"format", "3mf"}};
            } else if (format == "stl") {
                plater->export_stl();
                return json{{"exported", path}, {"format", "stl"}};
            }
            return json{{"error", "Unknown format: " + format}};
        });
    });
}

// ---------------------------------------------------------------------------
// Config commands
// ---------------------------------------------------------------------------
void CommandDispatch::register_config_commands() {
    register_command("config.get", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            auto config = wxGetApp().preset_bundle->full_config();
            json result;
            if (!params.contains("keys"))
                return json{{"error", "No keys provided"}};
            for (const auto& key : params["keys"]) {
                std::string k = key.get<std::string>();
                if (config.has(k)) {
                    result[k] = config.opt_serialize(k);
                }
            }
            return result;
        });
    });

    register_command("config.set", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            const json& settings = unwrap_config_settings(params);
            DynamicPrintConfig new_config;
            for (auto it = settings.begin(); it != settings.end(); ++it) {
                const std::string& key = it.key();
                const std::string val = it.value().is_string() ? it.value().get<std::string>() : it.value().dump();
                if (print_config_def.has(key)) {
                    new_config.set_deserialize_strict(key, val);
                }
            }

            // Apply to the appropriate Tab so changes persist in the preset system.
            // Try print tab first (most settings), then filament, then printer.
            for (auto type : {Preset::TYPE_PRINT, Preset::TYPE_FILAMENT, Preset::TYPE_PRINTER}) {
                Tab* tab = wxGetApp().get_tab(type);
                if (!tab) continue;
                DynamicPrintConfig tab_subset;
                for (auto& opt_key : new_config.keys()) {
                    if (tab->get_config()->has(opt_key))
                        tab_subset.set_key_value(opt_key, new_config.option(opt_key)->clone());
                }
                if (!tab_subset.empty())
                    tab->load_config(tab_subset);
            }

            return json{{"updated", true}};
        });
    });

    register_command("config.list", [](const json& params) -> json {
        std::string filter = params.value("filter", "");
        json result = json::array();
        for (const auto& [key, def] : print_config_def.options) {
            if (!filter.empty() && key.find(filter) == std::string::npos)
                continue;
            json entry;
            entry["key"] = key;
            entry["type"] = static_cast<int>(def.type);
            if (!def.tooltip.empty())
                entry["tooltip"] = def.tooltip;
            result.push_back(entry);
        }
        return json{{"options", result}};
    });

    register_command("config.load_profile", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            std::string name = params.value("name", "");
            std::string path = params.value("path", "");
            bool list_only = params.value("list", false);

            auto* preset_bundle = wxGetApp().preset_bundle;

            // Debug/introspection: return all currently-loaded presets.
            if (list_only) {
                json out;
                for (auto& [label, coll] : std::initializer_list<std::pair<std::string, PresetCollection*>>{
                        {"printers",  &preset_bundle->printers},
                        {"prints",    &preset_bundle->prints},
                        {"filaments", &preset_bundle->filaments}}) {
                    json arr = json::array();
                    for (const Preset& p : *coll) arr.push_back(p.name);
                    out[label] = arr;
                }
                json vendors = json::array();
                for (const auto& v : preset_bundle->vendors) vendors.push_back(v.first);
                out["vendors"] = vendors;
                return out;
            }

            if (name.empty() && path.empty())
                return json{{"error", "Provide either 'name', 'path', or 'list: true'"}};
            if (!name.empty()) {
                bool found = false;
                for (auto* collection : {
                    &preset_bundle->prints,
                    &preset_bundle->filaments
                }) {
                    const Preset* preset = collection->find_preset(name);
                    if (preset != nullptr) {
                        collection->select_preset_by_name(name, true);
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    const Preset* preset = preset_bundle->printers.find_preset(name);
                    if (preset != nullptr) {
                        preset_bundle->printers.select_preset_by_name(name, true);
                        found = true;
                    }
                }
                if (!found)
                    return json{{"error", "Profile not found: " + name}};

                wxGetApp().plater()->on_config_change(preset_bundle->full_config());
                return json{{"loaded", name}};
            }

            return json{{"error", "Loading profiles from file path is not yet supported"}};
        });
    });
}

// ---------------------------------------------------------------------------
// Diagnostics commands
// ---------------------------------------------------------------------------
void CommandDispatch::register_diagnostics_commands() {
    register_command("diagnostics.state", [this](const json& /*params*/) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* plater = wxGetApp().plater();
            const auto& model = plater->model();
            auto* preset_bundle = wxGetApp().preset_bundle;

            json result;
            result["object_count"] = model.objects.size();

            // Object details
            json objects = json::array();
            for (size_t i = 0; i < model.objects.size(); ++i) {
                const auto* obj = model.objects[i];
                json o;
                o["index"] = i;
                o["name"] = obj->name;
                auto bb = obj->bounding_box_approx();
                o["bounding_box"] = {
                    {"min", {bb.min.x(), bb.min.y(), bb.min.z()}},
                    {"max", {bb.max.x(), bb.max.y(), bb.max.z()}}
                };
                objects.push_back(o);
            }
            result["objects"] = objects;

            // Plate info
            auto config = preset_bundle->full_config();
            json plate;
            plate["index"] = plater->get_partplate_list().get_curr_plate_index();
            plate["printable_area"] = config.opt_serialize("printable_area");
            result["plate"] = plate;

            // Camera info
            const auto& camera = plater->get_camera();
            json cam;
            cam["type"] = camera.get_type_as_string();
            auto pos = camera.get_position();
            cam["position"] = {pos.x(), pos.y(), pos.z()};
            auto target = const_cast<Camera&>(plater->get_camera()).get_target();
            cam["target"] = {target.x(), target.y(), target.z()};
            cam["zoom"] = camera.get_zoom();
            result["camera"] = cam;

            // Active profiles
            result["printer"] = preset_bundle->printers.get_selected_preset().name;
            result["filament"] = preset_bundle->filaments.get_selected_preset().name;
            result["process"] = preset_bundle->prints.get_selected_preset().name;

            // Status
            result["slicing"] = plater->is_background_process_slicing();

            return result;
        });
    });

    register_command("diagnostics.mesh_stats", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            int index = params.value("index", -1);
            auto* plater = wxGetApp().plater();
            const auto& model = plater->model();
            if (index < 0 || index >= (int)model.objects.size())
                return json{{"error", "Invalid object index"}};

            const auto* obj = model.objects[index];
            json result;
            result["name"] = obj->name;
            result["volumes"] = json::array();
            for (size_t vi = 0; vi < obj->volumes.size(); ++vi) {
                const auto* vol = obj->volumes[vi];
                const auto& stats = vol->mesh().stats();
                json vs;
                vs["index"] = vi;
                vs["name"] = vol->name;
                vs["facets"] = stats.number_of_facets;
                vs["volume"] = stats.volume;
                vs["open_edges"] = stats.open_edges;
                result["volumes"].push_back(vs);
            }
            auto bb = obj->bounding_box_approx();
            result["bounding_box"] = {
                {"min", {bb.min.x(), bb.min.y(), bb.min.z()}},
                {"max", {bb.max.x(), bb.max.y(), bb.max.z()}}
            };
            return result;
        });
    });

    register_command("diagnostics.validate", [this](const json& /*params*/) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* plater = wxGetApp().plater();
            // Use the current plate's Print — p->fff_print (plater-level) is stale;
            // the background process slices partplate->m_print.
            const auto& print = plater->get_partplate_list().get_current_fff_print();
            StringObjectException warning;
            auto err = print.validate(&warning);
            json result;
            result["valid"] = err.string.empty();
            if (!err.string.empty())
                result["error"] = err.string;
            if (!warning.string.empty())
                result["warning"] = warning.string;
            return result;
        });
    });

    register_command("diagnostics.slice", [this](const json& /*params*/) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* plater = wxGetApp().plater();
            plater->reslice();
            return json{{"slicing", "started"}};
        });
    });

    register_command("diagnostics.slice_status", [this](const json& /*params*/) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* plater = wxGetApp().plater();
            // Use the current plate's Print — p->fff_print (plater-level) is stale;
            // the background process slices partplate->m_print and only that one
            // gets psGCodeExport set done when export completes.
            auto& plate_list = plater->get_partplate_list();
            const auto& print = plate_list.get_current_fff_print();
            bool slicing = plater->is_background_process_slicing();
            bool finished = print.finished();

            json result;
            result["slicing"] = slicing;
            result["finished"] = finished;
            result["plate_index"] = plate_list.get_curr_plate_index();

            const auto& stats = print.print_statistics();
            if (!stats.estimated_normal_print_time.empty()) {
                result["print_time"] = stats.estimated_normal_print_time;
                result["filament_used_mm"] = stats.total_used_filament;
                result["filament_used_cm3"] = stats.total_extruded_volume;
                result["filament_cost"] = stats.total_cost;
                result["filament_weight_g"] = stats.total_weight;
                result["total_toolchanges"] = stats.total_toolchanges;
            }

            // Check for validation errors
            StringObjectException warning;
            auto err = print.validate(&warning);
            if (!err.string.empty())
                result["error"] = err.string;
            if (!warning.string.empty())
                result["warning"] = warning.string;

            return result;
        });
    });
}

// ---------------------------------------------------------------------------
// Viewport commands
// ---------------------------------------------------------------------------
void CommandDispatch::register_viewport_commands() {
    register_command("viewport.select_view", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            std::string view = params.value("view", "");
            if (view.empty())
                return json{{"error", "No view specified"}};

            static const std::set<std::string> valid_views = {
                "front", "rear", "top", "bottom", "left", "right", "iso", "topfront"
            };
            if (valid_views.find(view) == valid_views.end())
                return json{{"error", "Invalid view: " + view + ". Valid: front, rear, top, bottom, left, right, iso, topfront"}};

            auto* canvas = wxGetApp().plater()->get_view3D_canvas3D();
            if (!canvas) return json{{"error", "No canvas"}};

            canvas->select_view(view);
            canvas->set_as_dirty();
            canvas->render();

            return json{{"view", view}};
        });
    });

    register_command("viewport.zoom_to_bed", [this](const json& /*params*/) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* canvas = wxGetApp().plater()->get_view3D_canvas3D();
            if (!canvas) return json{{"error", "No canvas"}};

            canvas->zoom_to_bed();
            canvas->set_as_dirty();
            canvas->render();

            return json{{"zoomed", "bed"}};
        });
    });

    register_command("viewport.zoom_to_volumes", [this](const json& /*params*/) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* canvas = wxGetApp().plater()->get_view3D_canvas3D();
            if (!canvas) return json{{"error", "No canvas"}};

            canvas->zoom_to_volumes();
            canvas->set_as_dirty();
            canvas->render();

            return json{{"zoomed", "volumes"}};
        });
    });

    register_command("viewport.zoom", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            double delta = params.value("delta", 0.0);
            if (delta == 0.0)
                return json{{"error", "No delta specified"}};

            auto& camera = wxGetApp().plater()->get_camera();
            camera.update_zoom(delta);

            auto* canvas = wxGetApp().plater()->get_view3D_canvas3D();
            if (canvas) {
                canvas->set_as_dirty();
                canvas->render();
            }

            return json{{"zoom", camera.get_zoom()}};
        });
    });

    register_command("viewport.select_tab", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            std::string tab = params.value("tab", "");
            static const std::set<std::string> valid = {"3D", "Preview", "Assemble", "Home", "Device"};
            if (valid.count(tab) == 0) {
                return json{{"error", "tab must be one of: 3D, Preview, Assemble, Home, Device"}};
            }
            auto* plater = wxGetApp().plater();
            auto* mainframe = wxGetApp().mainframe;

            // Two-level navigation in OrcaSlicer:
            //   (1) MainFrame tabs: Home / 3DEditor (Prepare) / Preview / Device / Project
            //   (2) Plater internal panel: view3D / preview / assemble (within 3DEditor)
            // Without switching the MainFrame tab first, the plater panel change is
            // invisible because MainFrame is still showing the Home welcome page.
            if (tab == "Home") {
                mainframe->select_tab(size_t(MainFrame::tpHome));
            } else if (tab == "Preview") {
                mainframe->select_tab(size_t(MainFrame::tpPreview));
                plater->select_view_3D("Preview");
            } else if (tab == "Device") {
                // ORCA_BELT: Device tab (Klipper/Moonraker panel). The panel is
                // only inserted for non-Bambu printers via show_device(false);
                // if it's missing, fall back to the Home tab.
                mainframe->select_tab(size_t(MainFrame::tpMonitor));
            } else {  // "3D" or "Assemble"
                mainframe->select_tab(size_t(MainFrame::tp3DEditor));
                plater->select_view_3D(tab);
            }

            // Render a frame so the newly-active canvas is drawn.
            // Device/Home tabs have no 3D canvas — skip the redraw.
            if (tab != "Device" && tab != "Home") {
                auto* canvas = (tab == "Preview")
                    ? plater->get_preview_canvas3D()
                    : plater->get_view3D_canvas3D();
                if (canvas) {
                    canvas->set_as_dirty();
                    canvas->render();
                }
            }
            return json{{"tab", tab}};
        });
    });

    register_command("viewport.set_preview_style", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* plater = wxGetApp().plater();
            auto* canvas = plater->get_preview_canvas3D();
            if (!canvas) return json{{"error", "No preview canvas (slice first?)"}};
            auto& gv = canvas->get_gcode_viewer();

            // view_type: FeatureType is default but colors walls solid blue which
            // hides infill; Feedrate colors every toolpath by speed (more
            // informative for screenshot validation).
            std::string view_type = params.value("view_type", std::string(""));
            static const std::map<std::string, GCodeViewer::EViewType> view_map = {
                {"feature_type",    GCodeViewer::EViewType::FeatureType},
                {"height",          GCodeViewer::EViewType::Height},
                {"width",           GCodeViewer::EViewType::Width},
                {"feedrate",        GCodeViewer::EViewType::Feedrate},
                {"fan_speed",       GCodeViewer::EViewType::FanSpeed},
                {"temperature",     GCodeViewer::EViewType::Temperature},
                {"volumetric_rate", GCodeViewer::EViewType::VolumetricRate},
                {"tool",            GCodeViewer::EViewType::Tool},
                {"color_print",     GCodeViewer::EViewType::ColorPrint},
                {"filament_id",     GCodeViewer::EViewType::FilamentId},
                {"layer_time",      GCodeViewer::EViewType::LayerTime},
                {"layer_time_log",  GCodeViewer::EViewType::LayerTimeLog},
            };
            if (!view_type.empty()) {
                auto it = view_map.find(view_type);
                if (it == view_map.end())
                    return json{{"error", "Unknown view_type: " + view_type}};
                gv.set_view_type(it->second);
            }

            // Shells are the solid outer mesh walls drawn on top of toolpaths.
            // Disabling them exposes the internal gcode geometry (infill, etc.)
            // which is what we want for validation screenshots.
            if (params.contains("show_shells")) {
                bool show = params["show_shells"].get<bool>();
                unsigned int flags = gv.get_options_visibility_flags();
                unsigned int shell_bit = 1u << static_cast<unsigned int>(Preview::OptionType::Shells);
                if (show) flags |= shell_bit; else flags &= ~shell_bit;
                gv.set_options_visibility_from_flags(flags);
            }
            if (params.contains("show_travel")) {
                bool show = params["show_travel"].get<bool>();
                unsigned int flags = gv.get_options_visibility_flags();
                unsigned int bit = 1u << static_cast<unsigned int>(Preview::OptionType::Travel);
                if (show) flags |= bit; else flags &= ~bit;
                gv.set_options_visibility_from_flags(flags);
            }

            canvas->set_as_dirty();
            if (wxWindow* wxc = reinterpret_cast<wxWindow*>(canvas->get_wxglcanvas())) {
                wxc->Refresh(false);
                wxc->Update();
            }
            canvas->render();

            json result;
            result["view_type"] = gv.get_view_type();
            result["options_flags"] = gv.get_options_visibility_flags();
            return result;
        });
    });

    register_command("viewport.set_preview_layer", [this](const json& params) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* plater = wxGetApp().plater();
            auto* canvas = plater->get_preview_canvas3D();
            if (!canvas) return json{{"error", "No preview canvas (slice first?)"}};
            auto& gv = canvas->get_gcode_viewer();
            auto* slider = gv.get_layers_slider();
            if (!slider) return json{{"error", "Layer slider not available"}};

            int min_v = slider->GetMinValue();
            int max_v = slider->GetMaxValue();
            if (max_v <= min_v) return json{{"error", "No layers to show (empty slice?)"}};

            int target;
            if (params.contains("layer")) {
                target = params["layer"].get<int>();
            } else if (params.contains("percent")) {
                double p = params["percent"].get<double>();
                if (p < 0.0) p = 0.0;
                if (p > 100.0) p = 100.0;
                target = min_v + static_cast<int>(std::round((max_v - min_v) * p / 100.0));
            } else {
                return json{{"error", "Provide 'layer' (int) or 'percent' (0-100)"}};
            }
            if (target < min_v) target = min_v;
            if (target > max_v) target = max_v;

            slider->SetHigherValue(target);
            if (gv.has_data()) {
                gv.set_layers_z_range({
                    static_cast<unsigned int>(slider->GetLowerValue()),
                    static_cast<unsigned int>(target)});
                gv.update_marker_curr_move();
            }
            canvas->set_as_dirty();
            // The _render_gcode path checks `layers_slider->is_dirty()` and
            // calls set_layers_z_range + post EVT_GLCANVAS_UPDATE on true.
            // That event schedules ANOTHER paint, which then actually commits
            // the filtered VBO contents. So one render() is not enough —
            // loop with wx event-pump in between so the posted paint events
            // get processed and the final frame reflects the layer filter.
            wxWindow* wxc = reinterpret_cast<wxWindow*>(canvas->get_wxglcanvas());
            for (int i = 0; i < 4; ++i) {
                canvas->set_as_dirty();
                if (wxc) {
                    wxc->Refresh(false);
                    wxc->Update();
                }
                canvas->render();
                wxGetApp().Yield(true);  // drain pending paint/UI events
            }

            json result;
            result["layer"] = target;
            result["min_layer"] = min_v;
            result["max_layer"] = max_v;
            result["percent"] = (max_v > min_v)
                ? (100.0 * (target - min_v) / (max_v - min_v)) : 100.0;
            return result;
        });
    });

    register_command("viewport.camera_info", [this](const json& /*params*/) -> json {
        return call_on_gui_thread([&]() -> json {
            auto* plater = wxGetApp().plater();
            const auto& camera = plater->get_camera();
            auto* canvas = plater->get_view3D_canvas3D();

            json result;
            result["type"] = camera.get_type_as_string();
            auto pos = camera.get_position();
            result["position"] = {pos.x(), pos.y(), pos.z()};
            auto target = const_cast<Camera&>(plater->get_camera()).get_target();
            result["target"] = {target.x(), target.y(), target.z()};
            result["zoom"] = camera.get_zoom();

            if (canvas) {
                Size cnv_size = canvas->get_canvas_size();
                result["viewport_width"] = cnv_size.get_width();
                result["viewport_height"] = cnv_size.get_height();
            }

            return result;
        });
    });
}

void CommandDispatch::init() {
    register_model_commands();
    register_config_commands();
    register_diagnostics_commands();
    register_viewport_commands();
    m_mcp_protocol.init(get_all_tool_definitions());
}

}} // namespace Slic3r::GUI
