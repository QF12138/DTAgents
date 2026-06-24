"""工具: 实体显示控制

控制 DTGeoStudio 三维面板中实体的外观（可见性、渲染模式、透明度）和体素切片。
所有操作直接作用于软件内置面板，无需导出文件。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# configure_entity：统一外观控制（可见性 + 渲染模式 + 透明度）
# ─────────────────────────────────────────────────────────────
class ConfigureEntityInput(BaseModel):
    entity_ids: list[int] = Field(description="实体 ID 列表，支持批量操作")
    visible: Optional[bool] = Field(
        default=None,
        description="显示/隐藏：True=显示，False=隐藏，None=不修改",
    )
    mode: Optional[str] = Field(
        default=None,
        description=(
            "渲染模式（None=不修改）：\n"
            "  wireframe — 线框，查看网格结构\n"
            "  solid     — 实体，统一颜色填充\n"
            "  colormap  — 按属性着色，需同时指定 attribute"
        ),
    )
    attribute: Optional[str] = Field(
        default=None,
        description="colormap 模式下的着色属性名，如 'lithology'、'resistivity'、'depth'",
    )
    colormap: str = Field(
        default="lithology",
        description=(
            "色表名称：\n"
            "  lithology            — 地质岩性专用（推荐用于岩性属性）\n"
            "  viridis              — 连续量通用（深度、电阻率等）\n"
            "  jet                  — 彩虹色表\n"
            "  coolwarm             — 冷暖双色（适合正负值对比）"
        ),
    )
    value_range: Optional[list[float]] = Field(
        default=None,
        description="colormap 属性值映射范围 [min, max]，None 则引擎自动计算",
    )
    opacity: Optional[float] = Field(
        default=None,
        description="透明度 0.0～1.0（None=不修改）。常用值：0.3 半透、1.0 不透明",
    )


@tool(args_schema=ConfigureEntityInput)
def configure_entity(
    entity_ids: list[int],
    visible: Optional[bool] = None,
    mode: Optional[str] = None,
    attribute: Optional[str] = None,
    colormap: str = "geological_lithology",
    value_range: Optional[list[float]] = None,
    opacity: Optional[float] = None,
) -> dict[str, Any]:
    """
    统一设置三维面板中实体的外观，控制可见性、渲染模式和透明度。
    除实体列表外，所有参数均为可选（None 表示不修改对应属性），可按需组合使用。
    """
    logger.info(
        "configure_entity | entity_ids=%s, visible=%s, mode=%r, attribute=%r, opacity=%s",
        entity_ids, visible, mode, attribute, opacity,
    )
    valid_modes = ("wireframe", "solid", "colormap")
    if mode is not None and mode not in valid_modes:
        return ToolOutput(
            success=False,
            message=f"不支持的渲染模式: {mode!r}，可选: {valid_modes}",
        ).model_dump()
    if mode == "colormap" and not attribute:
        return ToolOutput(
            success=False,
            message="colormap 模式必须指定 attribute 参数",
        ).model_dump()
    if opacity is not None and not 0.0 <= opacity <= 1.0:
        return ToolOutput(
            success=False,
            message=f"opacity 值 {opacity} 超出范围，须在 [0.0, 1.0] 之间",
        ).model_dump()
    try:
        import DTPyRuntime as dtpr
        for eid in entity_ids:
            if visible is not None:
                dtpr.set_visibility(eid, visible)
            if mode is not None:
                dtpr.set_display_mode(eid, mode, attribute, colormap, value_range)
            if opacity is not None:
                dtpr.set_opacity(eid, opacity)
        changes = []
        if visible is not None:
            changes.append("显示" if visible else "隐藏")
        if mode is not None:
            changes.append(f"{mode} 模式")
        if opacity is not None:
            changes.append(f"透明度 {opacity:.0%}")
        summary = "、".join(changes) if changes else "无变更"
        logger.info("configure_entity 完成 | %d 个实体: %s", len(entity_ids), summary)
        return ToolOutput(
            success=True,
            data={"entity_ids": entity_ids, "visible": visible, "mode": mode, "opacity": opacity},
            message=f"{len(entity_ids)} 个实体已更新: {summary}",
        ).model_dump()
    except Exception as e:
        logger.error("configure_entity 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"实体外观设置失败: {e}").model_dump()


# ─────────────────────────────────────────────────────────────
# set_voxel_slice：体素模型切片
# ─────────────────────────────────────────────────────────────
class SetVoxelSliceInput(BaseModel):
    entity_id: int = Field(description="体素模型实体 ID")
    enabled: bool = Field(description="True=启用切片，False=关闭切片恢复完整显示")
    axis: str = Field(
        default="Z",
        description="切片轴：'X'（纵断面）| 'Y'（横断面）| 'Z'（水平面/平切）",
    )
    position: float = Field(
        default=0.0,
        description="切片位置，工程坐标系下的坐标值（米）",
    )


@tool(args_schema=SetVoxelSliceInput)
def set_voxel_slice(
    entity_id: int,
    enabled: bool,
    axis: str = "Z",
    position: float = 0.0
) -> dict[str, Any]:
    """
    为体素模型设置切片面，在三维面板中查看内部地质结构。
    enabled=False 可恢复完整体素模型显示。
    """
    logger.info(
        "set_voxel_slice | entity_id=%s, enabled=%s, axis=%r, position=%s",
        entity_id, enabled, axis, position,
    )
    valid_axes = ("X", "Y", "Z")
    if axis.upper() not in valid_axes:
        return ToolOutput(
            success=False,
            message=f"不支持的切片轴: {axis!r}，可选: {valid_axes}",
        ).model_dump()
    try:
        import DTPyRuntime as dtpr
        dtpr.set_voxel_slice(entity_id, enabled, axis.upper(), position)
        state = f"已在 {axis.upper()} 轴 {position} 处启用切片" if enabled else "切片已关闭"
        logger.info("set_voxel_slice 完成 | entity_id=%s, %s", entity_id, state)
        return ToolOutput(
            success=True,
            data={"entity_id": entity_id, "enabled": enabled, "axis": axis.upper(), "position": position},
            message=f"实体 {entity_id} {state}",
        ).model_dump()
    except Exception as e:
        logger.error("set_voxel_slice 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"体素切片设置失败: {e}").model_dump()
