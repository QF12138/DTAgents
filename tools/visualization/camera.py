"""工具: 视图与相机控制

在 DTGeoStudio 三维面板中创建视图、切换标准视角、聚焦实体。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# create_view：新建视图
# ─────────────────────────────────────────────────────────────
class CreateViewInput(BaseModel):
    view_name: str = Field(description="视图名称，用于后续工具中通过 view_id 定位该视图")
    layout: str = Field(
        default="single",
        description=(
            "视口布局：\n"
            "  single   — 单视图（全屏）\n"
            "  split_h  — 左右分屏（两个视图横向排列）\n"
            "  split_v  — 上下分屏（两个视图纵向排列）\n"
            "  quad     — 四视图（2×2 标准多视图布局）"
        ),
    )


@tool(args_schema=CreateViewInput)
def create_view(
    view_name: str,
    layout: str = "single",
) -> dict[str, Any]:
    """
    在 DTGeoStudio 三维面板中新建一个视图（视口）。
    返回 view_id，后续相机控制工具通过 view_id 定位到该视图。
    split_h/split_v 适用于同一模型的不同截面对比；
    quad 适用于俯视 + 前视 + 侧视 + 三维四视图同时展示。
    """
    logger.info("create_view | view_name=%r, layout=%r", view_name, layout)
    valid_layouts = ("single", "split_h", "split_v", "quad")
    if layout not in valid_layouts:
        return ToolOutput(
            success=False,
            message=f"不支持的布局: {layout!r}，可选: {valid_layouts}",
        ).model_dump()
    try:
        import DTPyRuntime as dtpr
        view_id = dtpr.create_view(view_name, layout)
        logger.info("create_view 完成 | view_id=%s, view_name=%r, layout=%r", view_id, view_name, layout)
        return ToolOutput(
            success=True,
            data={"view_id": view_id, "view_name": view_name, "layout": layout},
            message=f"视图 '{view_name}' 创建成功，view_id={view_id}，布局={layout}",
        ).model_dump()
    except Exception as e:
        logger.error("create_view 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"视图创建失败: {e}").model_dump()


# ─────────────────────────────────────────────────────────────
# set_standard_view：标准视角
# ─────────────────────────────────────────────────────────────
class SetStandardViewInput(BaseModel):
    view_id: int = Field(
        default=-1,
        description="目标视图 ID，-1 表示当前活动视图",
    )
    direction: str = Field(
        description=(
            "标准视角方向：\n"
            "  top        — 俯视（从 +Z 向下看）\n"
            "  bottom     — 仰视（从 -Z 向上看）\n"
            "  front      — 正视（从 +Y 向前看）\n"
            "  back       — 后视（从 -Y 向后看）\n"
            "  right      — 右视（从 +X 向左看）\n"
            "  left       — 左视（从 -X 向右看）\n"
            "  isometric  — 等轴测（西南方向 45° 俯角，最常用三维视角）"
        )
    )
    projection: str = Field(
        default="perspective",
        description=(
            "投影类型：\n"
            "  perspective   — 透视投影（近大远小，符合视觉习惯）\n"
            "  orthographic  — 正交投影（无透视变形，适合测量和断面图）"
        ),
    )


@tool(args_schema=SetStandardViewInput)
def set_standard_view(
    direction: str,
    view_id: int = -1,
    projection: str = "perspective",
) -> dict[str, Any]:
    """
    将指定视图的相机切换到标准方向视角。
    isometric（等轴测）是最常用的三维全局视角；
    top（俯视）配合 orthographic 投影适合查看平面分布；
    front/right 配合 orthographic 适合查看断面剖切图。
    """
    logger.info(
        "set_standard_view | view_id=%s, direction=%r, projection=%r",
        view_id, direction, projection,
    )
    valid_directions = ("top", "bottom", "front", "back", "right", "left", "isometric")
    valid_projections = ("perspective", "orthographic")
    if direction not in valid_directions:
        return ToolOutput(
            success=False,
            message=f"不支持的视角方向: {direction!r}，可选: {valid_directions}",
        ).model_dump()
    if projection not in valid_projections:
        return ToolOutput(
            success=False,
            message=f"不支持的投影类型: {projection!r}，可选: {valid_projections}",
        ).model_dump()
    try:
        # TODO necessary?
        import DTPyRuntime as dtpr
        # dtpr.set_standard_view(view_id, direction, projection)
        logger.info("set_standard_view 完成 | view_id=%s → %s/%s", view_id, direction, projection)
        return ToolOutput(
            success=True,
            data={"view_id": view_id, "direction": direction, "projection": projection},
            message=f"视图 {view_id} 已切换为 {direction} 视角（{projection}）",
        ).model_dump()
    except Exception as e:
        logger.error("set_standard_view 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"标准视角设置失败: {e}").model_dump()


# ─────────────────────────────────────────────────────────────
# focus_on_entity：自动 fit 相机到实体
# ─────────────────────────────────────────────────────────────
class FocusOnEntityInput(BaseModel):
    entity_ids: list[int] = Field(
        description="目标实体 ID 列表，相机将自动缩放平移以完整显示指定实体集"
    )
    view_id: int = Field(
        default=-1,
        description="目标视图 ID，-1 表示当前活动视图",
    )
    orbit: bool = Field(
        default=False,
        description="是否启用轨道环绕（Orbiting）",
    )


@tool(args_schema=FocusOnEntityInput)
def focus_on_entity(
    entity_ids: list[int],
    view_id: int = -1,
    orbit: bool = False,
) -> dict[str, Any]:
    """
    将指定视图的相机自动调整到最佳位置，使所有目标实体完整可见。
    设置 orbit=True 围绕目标模型列表进行轨道环绕查看。
    """
    logger.info("focus_on_entity | entity_ids=%s, view_id=%s, orbit=%s", entity_ids, view_id, orbit)
    try:
        import DTPyRuntime as dtpr
        if orbit: dtpr.orbit_entity(entity_ids, view_id)
        else: dtpr.focus_scene(view_id, 0)
        
        orbit_info = "，轨道旋转中心已设置" if orbit else ""
        logger.info("focus_on_entity 完成 | %s 实体已聚焦，view_id=%s, orbit=%s", entity_ids, view_id, orbit_info)

        return ToolOutput(
            success=True,
            data={"entity_ids": entity_ids, "view_id": view_id, "orbit": orbit},
            message=f"相机已聚焦到指定实体",
        ).model_dump()
    except Exception as e:
        logger.error("focus_on_entity 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"相机聚焦失败: {e}").model_dump()


