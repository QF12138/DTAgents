"""
AST 参数比对评分器

实现 BFCL 风格的参数结构比对：
- 字段名匹配
- 类型兼容检查（int/float 互兼容，str 大小写不敏感）
- 必填字段检测
- 幻觉字段检测（实际调用了 schema 中不存在的参数）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParamMatchResult:
    """单次工具调用的参数比对结果"""
    tool_name: str
    expected_params: dict[str, Any]
    actual_params: dict[str, Any]
    # 各字段比对
    matched_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)   # 期望有但实际没有
    wrong_value_fields: list[str] = field(default_factory=list)  # 有但值不符
    hallucinated_fields: list[str] = field(default_factory=list) # 实际有但 schema 不认识

    @property
    def param_accuracy(self) -> float:
        """参数精确率 PA：完全正确的字段数 / 期望字段数"""
        total = len(self.expected_params)
        if total == 0:
            return 1.0
        return len(self.matched_fields) / total

    @property
    def hallucination_rate(self) -> float:
        """幻觉参数率 HAL：幻觉字段数 / 实际字段数"""
        total = len(self.actual_params)
        if total == 0:
            return 0.0
        return len(self.hallucinated_fields) / total

    @property
    def is_perfect(self) -> bool:
        return (not self.missing_fields and not self.wrong_value_fields
                and not self.hallucinated_fields)


def _values_match(expected: Any, actual: Any) -> bool:
    """
    类型兼容的值比对：
    - str：大小写不敏感
    - int/float：互兼容（比较数值）
    - list：逐元素比对
    - dict：递归比对
    - None：精确匹配
    """
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False

    # 数值兼容
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) < 1e-9

    # 字符串大小写不敏感
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()

    # 列表：逐元素
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return False
        return all(_values_match(e, a) for e, a in zip(expected, actual))

    # 字典：递归
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k, v in expected.items():
            if k not in actual:
                return False
            if not _values_match(v, actual[k]):
                return False
        return True

    return expected == actual


def compare_params(
    tool_name: str,
    expected_params: dict[str, Any],
    actual_params: dict[str, Any],
    known_schema_fields: set[str] | None = None,
) -> ParamMatchResult:
    """
    比对期望参数与实际参数。

    Args:
        tool_name:          工具名（用于报告）
        expected_params:    测试用例中期望的参数子集（不含可选字段）
        actual_params:      LLM 实际调用时传入的参数
        known_schema_fields: 工具 schema 中所有合法字段名（用于检测幻觉参数）

    Returns:
        ParamMatchResult
    """
    result = ParamMatchResult(
        tool_name=tool_name,
        expected_params=expected_params,
        actual_params=actual_params,
    )

    # 1. 比对期望字段
    for key, exp_val in expected_params.items():
        if key not in actual_params:
            result.missing_fields.append(key)
        elif _values_match(exp_val, actual_params[key]):
            result.matched_fields.append(key)
        else:
            result.wrong_value_fields.append(key)

    # 2. 检测幻觉参数
    if known_schema_fields is not None:
        for key in actual_params:
            if key not in known_schema_fields:
                result.hallucinated_fields.append(key)

    return result


# ── 工具 Schema 字段注册（用于幻觉检测）────────────────────────────────────────

TOOL_SCHEMA_FIELDS: dict[str, set[str]] = {
    "query_hierarchy": {"level", "project_id", "mileage_infos"},
    "query_metadata": {"project_id", "site_ids", "data_type", "time_range",
                       "mileage_range"},
    "import_dataset": {"dataset_path", "dataset_type", "options"},
    "delaunay_triangulation": {"raster_id", "precision", "constraints_id",
                               "with_uvcoords"},
    "extract_isosurface": {"voxel_grid_path", "attribute", "isovalue"},
    "apply_texture": {"surface_entity_id", "dom_dataset_id"},
    "interpolate_spatial": {"control_points_path", "target_grid_path",
                            "attribute", "method", "method_params", "output_path"},
    "classify_lithology": {"feature_grid_path", "training_data_path",
                           "model_type", "model_params", "output_path"},
    "model_geological_body": {"rules", "bbox", "resolution", "output_path"},
    "validate_model": {"model_path", "drillhole_path", "constraints"},
    "boolean_operation": {"mesh_a_path", "mesh_b_path", "operation",
                          "output_path"},
    # ── PreprocessingAgent 工具 ───────────────────────────────────────────────
    "project_transform": {"dataset_id", "transform_type", "centerline_id",
                          "profile_id", "source_crs", "target_crs"},
    "clip_to_boundary": {"dataset_id", "centerline_id", "coverage_range",
                         "clip_mode", "mileage_range"},
    "spatial_sample": {"dataset_id", "resolution", "boundary_entity_id"},
    # ── VisualizationAgent 工具 ───────────────────────────────────────────────
    "configure_entity": {"entity_ids", "visible", "mode", "attribute",
                         "colormap", "value_range", "opacity"},
    "set_voxel_slice": {"entity_id", "enabled", "axis", "position"},
    "create_view": {"view_name", "layout"},
    "set_standard_view": {"direction", "view_id", "projection"},
    "focus_on_entity": {"entity_ids", "view_id", "orbit"},
}


def compare_tool_call(
    tool_name: str,
    expected_params: dict[str, Any],
    actual_params: dict[str, Any],
) -> ParamMatchResult:
    """便捷函数：自动查找 schema 字段并比对参数。"""
    known = TOOL_SCHEMA_FIELDS.get(tool_name)
    return compare_params(tool_name, expected_params, actual_params, known)
