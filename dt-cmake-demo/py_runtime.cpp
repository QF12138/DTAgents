/**
 * @ Author: WouRaoyu
 * @ Create Time: 2024-05-17 19:37:29
 * @ Modified by: WouRaoyu
 * @ Modified time: 2026-03-25 13:06:51
 * @ Description:
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <component/extlogic_mesh.h>
#include <component/extlogic_param.h>
#include <component/extlogic_points.h>
#include <component/mdllogic_mesh.h>
#include <component/mdllogic_shape.h>
#include <component/scene_anime.h>
#include <component/scene_config.h>
#include <component/semantic_base.h>
#include <component/semantic_config.h>
#include <component/semantic_texture.h>
#include <component/structure_drill.h>
#include <component/structure_image.h>
#include <component/structure_mesh.h>
#include <component/structure_points.h>
#include <component/structure_section.h>
#include <component/structure_shape.h>
#include <component/structure_spine.h>
#include <component/structure_volume.h>

#include <platform/application.h>
#include <platform/document.h>
#include <platform/progress_control.h>
#include <platform/widget_graph.h>
#include <platform/widget_dtgl.h>
#include <platform/widget_view.h>

#include <systems/system_import.h>
#include <systems/system_base.h>

#include <QApplication>
#include <QDebug>
#include <QThread>

namespace py = pybind11;

static const std::vector<uint32_t> ALGO_TYPES =
{
    entt::tuid<ParamFromAGPRaw>(),
    entt::tuid<SingleMeshFromShape>(),
    entt::tuid<SingleMeshFromVolume>(),
    entt::tuid<MultiMeshFromVolume>()
};

static const std::vector<uint32_t> STTE_TYPES =
{
    entt::type_hash<StructureDrill>::value(),
    entt::type_hash<StructureMesh>::value(),
    entt::type_hash<StructureImage>::value(),
    entt::type_hash<StructurePoints>::value(),
    entt::type_hash<StructureSection>::value(),
    entt::type_hash<StructureShape>::value(),
    entt::type_hash<StructureSpine>::value(),
    entt::type_hash<StructureVolume>::value()
};

static const std::unordered_map<std::string, std::pair<uint8_t, uint8_t>> DATA_TYPE_NAME_OPMAP =
{
    { "DEM", { 0, ImportSystem::GGERepMethod::GRI } },
    { "DOM", { 0, ImportSystem::GGERepMethod::GRI } },
    { "DRL", { 0, ImportSystem::GGERepMethod::DRL } },
    { "EGM", { 0, ImportSystem::GGERepMethod::GRS } },
    { "BIM", { 0, ImportSystem::GGERepMethod::SHP } },
    { "PRF", { 0, ImportSystem::GGERepMethod::PRL } },
    { "ECL", { 0, ImportSystem::GGERepMethod::SPN } },
    { "MSH", { 0, ImportSystem::GGERepMethod::MSH } },

    { "TSP", { 1, ImportSystem::AGPExpMethod::TSP } },
    { "TEM", { 1, ImportSystem::AGPExpMethod::TEM } },
    { "GPR", { 1, ImportSystem::AGPExpMethod::GPR } },
    { "AHD", { 1, ImportSystem::AGPExpMethod::AHD } },
    { "DBH", { 1, ImportSystem::AGPExpMethod::DBH } },
    { "TFR", { 1, ImportSystem::AGPExpMethod::TFS } },

    { "TBM", { 2, 0 } },
    { "RDR", { 2, 0 } },
    { "IST", { 2, 0 } },
    { "EMS", { 2, 0 } },
};

static const std::unordered_map<std::string, uint32_t> DATA_TYPE_NAME_CODE_MAP =
{
    { "DEM", entt::type_hash<SemanticTexture>::value() },
    { "DOM", entt::type_hash<SemanticTexture>::value() },
    { "DRL", entt::type_hash<StructureDrill>::value() },
    { "EGM", entt::type_hash<StructureShape>::value() },
    { "BIM", entt::type_hash<StructureShape>::value() },
    { "PRF", entt::type_hash<StructureShape>::value() },
    { "ECL", entt::type_hash<StructureSpine>::value() },
    { "MSH", entt::type_hash<StructureMesh>::value() },

    { "TSP", entt::type_hash<SemanticDetect>::value() },
    { "TEM", entt::type_hash<SemanticDetect>::value() },
    { "GPR", entt::type_hash<SemanticDetect>::value() },
    { "AHD", entt::type_hash<SemanticDetect>::value() },
    { "DBH", entt::type_hash<SemanticDetect>::value() },
    { "TFR", entt::type_hash<SemanticDetect>::value() },

    //! TODO Real time data should have specific type
    { "TBM", entt::type_hash<StructurePoints>::value() },
    { "RDR", entt::type_hash<StructurePoints>::value() },
    { "IST", entt::type_hash<StructurePoints>::value() },
    { "EMS", entt::type_hash<StructurePoints>::value() },
};

static const bool EntityTypeVerify(const entt::registry* reg, const uint32_t type, entt::entity ent) {
    if (auto store = reg->storage(type)) {
        if (store->contains(ent)) {
            return true;
        }
    }
    return false;
}

static const uint32_t StructureType(const entt::registry* reg, entt::entity ent) {
    for (auto type : STTE_TYPES) {
        if (auto store = reg->storage(type)) {
            if (store->contains(ent)) {
                return type;
            }
        }
    }
    return entt::null;
}

PYBIND11_MODULE(DTPyRuntime, m) {
    m.def("hello", []() { qDebug() << "Hello scripts"; }, "hello function");

    m.attr("server_thread") = py::none();

    py::class_<Application>(m, "Application")
        .def(py::init<>());

    static Application* aptr = nullptr;
    m.def("init_app", [](Application* a) { aptr = a; });

    m.def("open_view", []()
        {
            if (aptr == nullptr) return;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    if (auto reg = doc->getRegistryPtr()) {
                        auto& cfg = SceneConfig::Instance(*reg);
                        doc->syncSceneConfig(cfg);
                        cfg.arrangement = true;
                        cfg.viewports.emplace_back();
                        graph->notifySceneControl(
                            entt::ouid<SceneConfig>(entt::null)
                        );
                    }
                }
            }
        }
    );

    m.def("read_data", [](const std::string& path, const std::string& type) -> uint32_t
        {
            if (aptr == nullptr) return entt::null;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto reg = doc->getRegistryPtr()) {
                    auto itr = DATA_TYPE_NAME_OPMAP.find(type);
                    if (DATA_TYPE_NAME_OPMAP.end() == itr) {
                        return entt::null;
                    }

                    uint32_t tcode = DATA_TYPE_NAME_CODE_MAP.find(type)->second;

                    auto graphUi = doc->getGraphEditor(); //! TODO

                    std::unique_ptr<ProgressControl> pg(new ProgressControl);
                    pg->setTitle(ImportSystem::ProgressTitle(
                        itr->second.first, itr->second.second));

                    entt::entity entId = entt::null;

                    if (itr->second.first == 0) {
                        entId = ImportSystem::ImportGGEData(*reg, pg.get(),
                            nullptr, path, itr->second.second, false
                        ).front();
                    }
                    else if (itr->second.first == 1) {
                        entId = ImportSystem::ImportAGPData(*reg, path);
                    }

                    if (entId != entt::null) {
                        graphUi->notifyNodeSelected({ entt::comuid(tcode, entId) });
                        return static_cast<uint32_t>(entId);
                    }
                }
            }
            return entt::null;
        }
    );

    m.def("preprocess", [](const uint32_t raw, const uint32_t cln, const uint32_t prf) -> uint32_t
        {
            if (aptr == nullptr) return entt::null;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    auto tuid = graph->constructByType(entt::tuid<ParamFromAGPRaw>());
                    if (auto reg = doc->getRegistryPtr()) {
                        auto param = reg->try_get<ParamFromAGPRaw>(tuid.second);
                        if (nullptr == param) return entt::null;

                        auto graphUi = doc->getGraphEditor(); //! TODO
                        graphUi->notifyNodeSelected({ tuid });

                        entt::entity rawEnt{ raw }; param->input = rawEnt;
                        graph->constructRelation(entt::ouid<SemanticDetect>(rawEnt), tuid);

                        entt::entity clnEnt{ cln }; param->mileage = clnEnt;
                        if (!reg->try_get<StructureSpine>(clnEnt)) return entt::null;
                        graph->constructRelation(entt::ouid<StructureSpine>(clnEnt), tuid);

                        entt::entity prfEnt{ prf }; param->tunnel = prfEnt;
                        if (!reg->try_get<StructureShape>(prfEnt)) return entt::null;
                        graph->constructRelation(entt::ouid<StructureShape>(prfEnt), tuid);

                        ProgressControl ctrl; //! ui progress
                        if (graph->executeLogic(tuid, &ctrl)) {
                            return raw;
                        }
                    }
                }
            }

            return entt::null;
        }
    );

    m.def("surface_25d", [](const uint32_t rasterID, const std::optional<float> precision,
        const std::optional<uint32_t> constraintID, const bool uvCoords) -> uint32_t
        {
            if (aptr == nullptr) return entt::null;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    auto tuid = graph->constructByType(entt::tuid<MeshDEMSurfaceParam>());
                    if (auto reg = doc->getRegistryPtr()) {
                        auto param = reg->try_get<MeshDEMSurfaceParam>(tuid.second);
                        if (nullptr == param) return entt::null;

                        auto graphUi = doc->getGraphEditor(); //! TODO
                        graphUi->notifyNodeSelected({ tuid });

                        entt::entity rasterEnt{ rasterID }; param->input = rasterEnt;
                        graph->constructRelation(entt::ouid<SemanticTexture>(rasterEnt), tuid);

                        if (constraintID) {
                            entt::entity constraintEnt{ constraintID.value() }; param->footprint = constraintEnt;
                            graph->constructRelation(entt::ouid<StructureShape>(constraintEnt), tuid);
                        }
                        param->precision = precision.has_value() ? precision.value() : 0.0;
                        param->withUV = uvCoords;

                        ProgressControl ctrl; //! ui progress
                        if (graph->executeLogic(tuid, &ctrl)) {
                            return static_cast<uint32_t>(param->output);
                        }
                    }
                }
            }
            return entt::null;
        }
    );

    m.def("bind_texture", [](const uint32_t entityID, const uint32_t textureID) -> uint32_t
        {
            if (aptr == nullptr) return entt::null;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    if (auto reg = doc->getRegistryPtr()) {
                        auto graphUi = doc->getGraphEditor(); //! TODO
                        entt::entity inputEnt{ entityID }, texEnt{ textureID };
                        if (EntityTypeVerify(reg, entt::tuid<StructureMesh>(), inputEnt)) {
                            auto tuid = graph->constructByType(entt::tuid<TopoMergeParam>());
                            auto param = reg->try_get<TopoMergeParam>(tuid.second);
                            if (nullptr == param) return entt::null;

                            graphUi->notifyNodeSelected({ tuid });

                            param->inputs.push_back(inputEnt);
                            graph->constructRelation(entt::ouid<StructureMesh>(inputEnt), tuid);
                            ProgressControl ctrl; //! ui progress
                            if (graph->executeLogic(tuid, &ctrl)) {
                                inputEnt = param->output;
                            }
                        }

                        if (EntityTypeVerify(reg, entt::tuid<StructureShape>(), inputEnt)) {

                            graphUi->notifyNodeSelected({ entt::ouid<StructureShape>(inputEnt) });

                            // 将 texEnt (SemanticTexture entity) 包装为 StructureImage wrapper entity
                            entt::entity rectEnt = reg->create();
                            reg->emplace<StructureImage>(rectEnt);
                            reg->emplace<SemanticTexture>(rectEnt, reg->get<SemanticTexture>(texEnt));
                            auto& texIds = reg->get_or_emplace<SemanticTexIds>(inputEnt);
                            texIds.textures.push_back(rectEnt);
                            texIds.texidx = static_cast<int32_t>(texIds.textures.size() - 1);
                            graph->constructRelation(entt::ouid<StructureImage>(rectEnt),
                                entt::ouid<StructureShape>(inputEnt));
                            return static_cast<uint32_t>(inputEnt);
                        }
                    }
                }
            }
            return entt::null;
        }
    );

    m.def("focus_scene", [](const std::vector<uint32_t>&, const int windowIndex, const uint32_t type) -> void
        {
            if (aptr == nullptr) return;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    if (auto reg = doc->getRegistryPtr()) {
                        auto tuid = graph->constructByType(entt::tuid<SceneCameraView>());
                        auto param = reg->try_get<SceneCameraView>(tuid.second);
                        if (nullptr == param) return;
                        param->cameraType = type;
                        param->viewIndex = windowIndex;
                        graph->executeLogic(tuid, nullptr);
                    }
                }
            }
        }
    );

    m.def("set_visibility", [](const uint32_t id, bool show) -> void
        {
            if (aptr == nullptr) return;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    if (auto reg = doc->getRegistryPtr()) {
                        entt::entity ent{ id };
                        auto itrp = reg->try_get<SemanticItemRep>(ent);
                        if (nullptr == itrp) return; //! invalid entity or not visualizable
                        itrp->visible = show;
                        graph->notifyEntityUpdated({ 0, ent });
                    }
                }
            }
        }
    );

    m.def("orbit_entity", [](const std::vector<uint32_t>& ids, int viewIndex) -> void
        {
            if (aptr == nullptr) return;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    if (auto reg = doc->getRegistryPtr()) {
                        auto tuid = graph->constructByType(entt::tuid<SceneOrbitObject>());
                        auto param = reg->try_get<SceneOrbitObject>(tuid.second);
                        if (nullptr == param) return;

                        auto graphUi = doc->getGraphEditor(); //! TODO
                        graphUi->notifyNodeSelected({ tuid });

                        for (auto id : ids) {
                            entt::entity entId{ id };
                            if (uint32_t type = StructureType(reg, entId); type != entt::null) {
                                graph->constructRelation({ type, entId }, tuid);
                            }
                        }
                        param->viewIndex = viewIndex;
                        graph->executeLogic(tuid, nullptr);
                    }
                }
            }
        }
    );

    m.def("create_algo", [](uint32_t type) -> uint32_t
        {
            if (aptr == nullptr) return entt::null;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    auto tuid = graph->constructByType(ALGO_TYPES[type]);
                    doc->getGraphEditor()->notifyNodeSelected({ tuid });
                    return static_cast<uint32_t>(tuid.second);
                }
            }
            return entt::null;
        }
    );

    m.def("exec_algo", [](uint32_t type, uint32_t id) -> uint32_t
        {
            if (aptr == nullptr) return entt::null;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    graph->executeLogic(entt::comuid{
                        ALGO_TYPES[type],
                        entt::entity(id) }
                        );
                }
            }
            return entt::null;
        }
    );

    // ─── Preprocessing interfaces ──────────────────────────────────────────

    // project_transform: mileage_to_spatial mode
    // Converts mileage-coordinate AGP detect data to 3D spatial coordinates.
    // dataset_id: SemanticDetect entity, centerline_id: StructureSpine entity,
    // profile_id: StructureShape entity. Returns dataset_id on success.
    m.def("trsf_mile2geo", [](const uint32_t datasetId,
        const uint32_t centerlineId, const uint32_t profileId) -> uint32_t
        {
            if (aptr == nullptr) return entt::null;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    auto tuid = graph->constructByType(entt::tuid<ParamFromAGPRaw>());
                    if (auto reg = doc->getRegistryPtr()) {
                        auto param = reg->try_get<ParamFromAGPRaw>(tuid.second);
                        if (nullptr == param) return entt::null;

                        auto graphUi = doc->getGraphEditor();
                        graphUi->notifyNodeSelected({ tuid });

                        entt::entity rawEnt{ datasetId }; param->input = rawEnt;
                        graph->constructRelation(entt::ouid<SemanticDetect>(rawEnt), tuid);

                        entt::entity clnEnt{ centerlineId }; param->mileage = clnEnt;
                        if (!reg->try_get<StructureSpine>(clnEnt)) return entt::null;
                        graph->constructRelation(entt::ouid<StructureSpine>(clnEnt), tuid);

                        entt::entity prfEnt{ profileId }; param->tunnel = prfEnt;
                        if (!reg->try_get<StructureShape>(prfEnt)) return entt::null;
                        graph->constructRelation(entt::ouid<StructureShape>(prfEnt), tuid);

                        ProgressControl ctrl;
                        if (graph->executeLogic(tuid, &ctrl)) {
                            return datasetId;
                        }
                    }
                }
            }
            return entt::null;
        }
    );

    // clip_to_boundary: creates a boundary shape along the centerline with a buffer.
    // clip_mode: "regional" -> 2D buffer (Buffer2DParam), "tunnel" -> 3D buffer (Wire3DParam).
    // mileage_range: optional [start, end] mileage for tunnel mode.
    // Returns the output boundary entity ID on success.
    m.def("clip_to_boundary", [](const uint32_t datasetId, const uint32_t centerlineId,
        const double coverageRange, const std::string& clipMode,
        const std::optional<std::vector<double>> mileageRange) -> uint32_t
        {
            if (aptr == nullptr) return entt::null;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    if (auto reg = doc->getRegistryPtr()) {
                        auto graphUi = doc->getGraphEditor();
                        entt::entity clnEnt{ centerlineId };

                        if (clipMode == "regional") {
                            auto tuid = graph->constructByType(entt::tuid<Buffer2DParam>());
                            auto param = reg->try_get<Buffer2DParam>(tuid.second);
                            if (nullptr == param) return entt::null;

                            graphUi->notifyNodeSelected({ tuid });
                            param->input = clnEnt;
                            param->width = coverageRange;
                            graph->constructRelation(entt::ouid<StructureSpine>(clnEnt), tuid);

                            ProgressControl ctrl;
                            if (graph->executeLogic(tuid, &ctrl)) {
                                return static_cast<uint32_t>(param->output);
                            }
                        }
                        else if (clipMode == "tunnel") {
                            auto tuid = graph->constructByType(entt::tuid<Wire3DParam>());
                            auto param = reg->try_get<Wire3DParam>(tuid.second);
                            if (nullptr == param) return entt::null;

                            graphUi->notifyNodeSelected({ tuid });
                            param->input = clnEnt;
                            param->width = coverageRange;
                            param->buffer = true;

                            if (mileageRange && mileageRange->size() >= 2) {
                                param->startFrom = (*mileageRange)[0];
                                param->length = (*mileageRange)[1] - (*mileageRange)[0];
                            }

                            graph->constructRelation(entt::ouid<StructureSpine>(clnEnt), tuid);

                            ProgressControl ctrl;
                            if (graph->executeLogic(tuid, &ctrl)) {
                                return static_cast<uint32_t>(param->output);
                            }
                        }
                    }
                }
            }
            return entt::null;
        }
    );

    // spatial_sample: extracts sampled points from a dataset entity at given resolution.
    // Applicable to borehole/profile detect data (AHD, DBH, DRL, TEM, GPR, TFR).
    // boundary_entity_id: optional StructureShape boundary produced by clip_to_boundary.
    // Returns the output StructurePoints entity ID on success.
    m.def("spatial_sample", [](const uint32_t datasetId, const float resolution,
        const std::optional<uint32_t> boundaryEntityId) -> uint32_t
        {
            if (aptr == nullptr) return entt::null;
            if (auto doc = aptr->getActiveDocument()) {
                if (auto graph = doc->getGraphSystem()) {
                    auto tuid = graph->constructByType(entt::tuid<PointsFromStructures>());
                    if (auto reg = doc->getRegistryPtr()) {
                        auto param = reg->try_get<PointsFromStructures>(tuid.second);
                        if (nullptr == param) return entt::null;

                        auto graphUi = doc->getGraphEditor();
                        graphUi->notifyNodeSelected({ tuid });

                        entt::entity dataEnt{ datasetId };
                        param->inputs.push_back(dataEnt);
                        param->precision = resolution;

                        uint32_t dataType = StructureType(reg, dataEnt);
                        if (dataType != entt::null) {
                            graph->constructRelation({ dataType, dataEnt }, tuid);
                        }

                        if (boundaryEntityId) {
                            entt::entity boundaryEnt{ boundaryEntityId.value() };
                            uint32_t boundaryType = StructureType(reg, boundaryEnt);
                            if (boundaryType != entt::null) {
                                param->inputs.push_back(boundaryEnt);
                                graph->constructRelation({ boundaryType, boundaryEnt }, tuid);
                            }
                        }

                        ProgressControl ctrl;
                        if (graph->executeLogic(tuid, &ctrl)) {
                            return static_cast<uint32_t>(param->output);
                        }
                    }
                }
            }
            return entt::null;
        }
    );
}