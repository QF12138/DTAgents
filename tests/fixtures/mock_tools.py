"""
Mock 工具返回值工厂

每个工具按 (tool_name, scenario) 返回预定义结果，
用于评测时拦截真实工具调用，使测试不依赖数据库/文件系统。

使用方式：
    from tests.fixtures.mock_tools import get_mock_response
    response = get_mock_response("query_hierarchy", {"level": "project"})
"""
from __future__ import annotations

from typing import Any

# ── 通用响应模板 ───────────────────────────────────────────────────────────────

def _ok(data: Any = None, message: str = "成功", **metadata) -> dict:
    return {"success": True, "data": data, "file_path": None,
            "message": message, "metadata": metadata or {}}


def _err(message: str = "失败") -> dict:
    return {"success": False, "data": None, "file_path": None,
            "message": message, "metadata": {}}


# ── 各工具的预设响应库 ─────────────────────────────────────────────────────────

MOCK_DB = {

    # ── InitializationAgent 工具 ──────────────────────────────────────────────

    "query_hierarchy": {
        # level=project
        "project_list": _ok(
            data=[
                {"project_id": "P001", "name": "隧道工程A", "type": "tunnel",
                 "description": "某高铁隧道工程", "default_crs": "EPSG:4547"},
                {"project_id": "P002", "name": "隧道工程B", "type": "tunnel",
                 "description": "某公路隧道工程", "default_crs": "EPSG:4547"},
            ],
            message="查询到 2 个工程",
            count=2,
        ),
        # level=work_site, project_id=P001
        "work_site_list": _ok(
            data=[
                {"site_id": "S001", "project_id": "P001", "name": "进口段",
                 "type": "entrance", "mileage_prefix": "DK",
                 "start_mileage": 5000.0, "end_mileage": 5500.0},
                {"site_id": "S002", "project_id": "P001", "name": "中间段",
                 "type": "middle", "mileage_prefix": "DK",
                 "start_mileage": 5500.0, "end_mileage": 6500.0},
            ],
            message="查询到 2 个工点",
            count=2,
        ),
        # level=work_site, mileage_infos=[DK5+128,DK5+256]
        "work_site_by_mileage": _ok(
            data=[
                {"site_id": "S001", "project_id": "P001", "name": "进口段",
                 "mileage_prefix": "DK", "start_mileage": 5000.0, "end_mileage": 5500.0 },
            ],
            message="按里程查询到 1 个工点，里程区间 mileage_range=[5128.0, 5256.0]",
            count=1,
        ),
        # 工程不存在
        "not_found": _ok(data=[], message="未找到匹配的工程", count=0),
    },

    "query_metadata": {
        # 正常结果（少量）
        "dem_results": _ok(
            data=[
                {"dataset_id": "D001", "name": "dem_2024.tif", "data_type": "DEM",
                 "file_path": "data/raw/dem_2024.tif", "description": "2024年DEM数据",
                 "survey_date_start": "2024-01-01", "survey_date_end": "2024-01-31"},
            ],
            message="查询到 1 个数据集",
            count=1,
        ),
        "tsp_results": _ok(
            data=[
                {"dataset_id": "D010", "name": "tsp_dk5.csv", "data_type": "TSP",
                 "file_path": "data/raw/tsp_dk5.csv", "description": "DK5段TSP数据",
                 "start_mileage": 5100.0, "end_mileage": 5256.0},
            ],
            message="查询到 1 个数据集",
            count=1,
        ),
        "gpr_results": _ok(
            data=[
                {"dataset_id": "D011", "name": "gpr_dk10_20.dat", "data_type": "GPR",
                 "file_path": "data/raw/gpr_dk10_20.dat", "description": "DK10~20 GPR数据",
                 "start_mileage": 10000.0, "end_mileage": 20000.0},
            ],
            message="查询到 1 个数据集",
            count=1,
        ),
        "dom_results": _ok(
            data=[
                {"dataset_id": "D002", "name": "dom_2024.tif", "data_type": "DOM",
                 "file_path": "data/raw/dom_2024.tif", "description": "2024年正射影像"},
            ],
            message="查询到 1 个数据集",
            count=1,
        ),
        "tbm_results": _ok(
            data=[
                {"dataset_id": "D020", "name": "tbm_20240315.csv", "data_type": "TBM",
                 "file_path": "data/raw/tbm_20240315.csv",
                 "survey_date_start": "2024-03-15", "survey_date_end": "2024-03-15"},
            ],
            message="查询到 1 个数据集",
            count=1,
        ),
        "multi_type_results": _ok(
            data=[
                {"dataset_id": "D010", "name": "tsp_dk5.csv", "data_type": "TSP",
                 "file_path": "data/raw/tsp_dk5.csv"},
                {"dataset_id": "D012", "name": "tem_dk5.dat", "data_type": "TEM",
                 "file_path": "data/raw/tem_dk5.dat"},
            ],
            message="查询到 2 个数据集",
            count=2,
        ),
        # 超阈值（>128 条）
        "over_threshold": {
            "success": True,
            "data": [],
            "file_path": None,
            "message": "查询到 150 个数据集，超过确认阈值（128 条）。按类型分布：DEM×100、DOM×50。请向用户确认或缩小查询范围。",
            "metadata": {"count": 150, "needs_confirmation": True,
                         "by_type": {"DEM": 100, "DOM": 50}},
        },
        # 无数据
        "empty": _ok(data=[], message="未找到匹配的数据集", count=0),
    },

    "import_dataset": {
        "dem_import": _ok(
            data={"entity_id": 1001},
            message="成功加载 DEM 数据，实体 ID: 1001",
        ),
        "dom_import": _ok(
            data={"entity_id": 1002},
            message="成功加载 DOM 数据，实体 ID: 1002",
        ),
        "tsp_import": _ok(
            data={"entity_id": 1010},
            message="成功加载 TSP 数据，实体 ID: 1010",
        ),
        "tbm_import": _ok(
            data={"entity_id": 1020},
            message="成功加载 TBM 数据，实体 ID: 1020",
        ),
        "generic_import": _ok(
            data={"entity_id": 1099},
            message="成功加载数据，实体 ID: 1099",
        ),
    },

    # ── PreprocessingAgent 工具 ──────────────────────────────────────────────

    "project_transform": {
        "mileage_to_spatial": _ok(
            data={"entity_id": 3001},
            message="里程转三维坐标完成，新实体ID: 3001",
        ),
        "crs_transform": _ok(
            data={"entity_id": 3002},
            message="坐标系转换完成，新实体ID: 3002",
        ),
        "failure": _err("坐标转换失败：中线数据无效或坐标系不支持"),
    },

    "clip_to_boundary": {
        "tunnel": _ok(
            data={"boundary_entity_id": 4001},
            message="洞内三维缓冲区裁剪完成，边界实体ID: 4001",
        ),
        "regional": _ok(
            data={"boundary_entity_id": 4002},
            message="工程尺度二维缓冲区裁剪完成，边界实体ID: 4002",
        ),
    },

    "spatial_sample": {
        "success": _ok(
            data={"entity_id": 5001, "sample_count": 1250},
            message="空间采样完成，采样点数: 1250，结果实体ID: 5001",
        ),
        "high_density": _ok(
            data={"entity_id": 5002, "sample_count": 8640},
            message="高密度空间采样完成，采样点数: 8640，结果实体ID: 5002",
        ),
    },

    # ── ModelingAgent 工具 ────────────────────────────────────────────────────

    "delaunay_triangulation": {
        "success": _ok(
            data={"entity_id": 2001},
            message="三角剖分完成，TIN 实体 ID: 2001",
        ),
    },

    "extract_isosurface": {
        "success": _ok(
            data={"entity_id": 2010, "vertex_count": 15432, "face_count": 30864},
            message="等值面提取完成，实体 ID: 2010",
        ),
    },

    "apply_texture": {
        "success": _ok(
            data={"entity_id": 2001},
            message="纹理贴图完成，实体 ID: 2001",
        ),
    },

    "interpolate_spatial": {
        "kriging": _ok(
            data={"grid_shape": [100, 100, 50], "attribute": "lithology"},
            file_path="data/processed/kriging_result.npz",
            message="克里金插值完成",
        ),
        "idw": _ok(
            data={"grid_shape": [100, 100, 50], "attribute": "soil_property"},
            file_path="data/processed/idw_result.npz",
            message="IDW 插值完成",
        ),
    },

    "classify_lithology": {
        "random_forest": _ok(
            data={"accuracy": 0.92, "classes": ["砂岩", "泥岩", "灰岩"]},
            file_path="data/processed/lithology_rf.npz",
            message="岩性分类完成，准确率 92%",
        ),
    },

    "model_geological_body": {
        "success": _ok(
            file_path="data/processed/geo_body.vtk",
            message="地质体建模完成",
        ),
    },

    "validate_model": {
        "success": _ok(
            data={"is_valid": True, "issues": []},
            message="模型验证通过",
        ),
    },

    "boolean_operation": {
        "difference": _ok(
            file_path="data/processed/bool_diff.vtk",
            message="布尔差运算完成",
        ),
        "union": _ok(
            file_path="data/processed/bool_union.vtk",
            message="布尔并运算完成",
        ),
    },

    # ── VisualizationAgent 工具 ───────────────────────────────────────────────

    "configure_entity": {
        "success": _ok(
            data={"updated_entities": [1, 2, 3]},
            message="实体配置更新成功",
        ),
    },

    "set_voxel_slice": {
        "success": _ok(
            data={"entity_id": 2001, "axis": "Z", "position": -50.0},
            message="体素切片设置成功",
        ),
    },

    "create_view": {
        "single": _ok(
            data={"view_id": 1, "layout": "single"},
            message="视图创建成功",
        ),
        "split_h": _ok(
            data={"view_id": 2, "layout": "split_h"},
            message="分割视图创建成功",
        ),
        "quad": _ok(
            data={"view_id": 3, "layout": "quad"},
            message="四分视图创建成功",
        ),
    },

    "set_standard_view": {
        "success": _ok(
            data={"direction": "top", "view_id": -1},
            message="视角切换成功",
        ),
    },

    "focus_on_entity": {
        "success": _ok(
            data={"entity_ids": [1, 2], "view_id": -1},
            message="相机聚焦完成",
        ),
    },
}


def get_mock_response(tool_name: str, scenario: str = "success") -> dict:
    """
    获取指定工具的 Mock 响应。

    Args:
        tool_name: 工具函数名（如 "query_hierarchy"）
        scenario:  场景键（如 "project_list"、"not_found"）

    Returns:
        Mock 响应字典（符合 ToolOutput 结构）
    """
    tool_mocks = MOCK_DB.get(tool_name, {})
    if scenario in tool_mocks:
        return tool_mocks[scenario]
    # 回退到第一个可用 scenario
    if tool_mocks:
        return next(iter(tool_mocks.values()))
    return _err(f"No mock defined for tool '{tool_name}'")
