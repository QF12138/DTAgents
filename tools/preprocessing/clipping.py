"""工具: 区域裁剪（按里程区间或空间包围盒）"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# clip_to_boundary：区域裁剪
# ─────────────────────────────────────────────────────────────
class ClipBoundaryInput(BaseModel):
    dataset_id: int = Field(
        description="输入数据的运行时实体ID（由初始化阶段 import_dataset 返回）"
    )
    centerline_id: int = Field(
        description="工程中线实体ID，两种裁剪模式均以中线为基准生成缓冲区"
    )
    coverage_range: float = Field(
        description=(
            "缓冲区范围，单位：米。"
            "clip_mode=regional 时沿中线创建二维缓冲区（平面范围）；"
            "clip_mode=tunnel 时沿中线创建三维缓冲区（隧道空间范围）"
        )
    )
    clip_mode: str = Field(
        description=(
            "裁剪模式: "
            "tunnel（洞内尺度，沿中线创建三维缓冲区，适用于里程定位数据）"
            " | "
            "regional（工程尺度，沿中线创建二维缓冲区，适用于大范围地表数据）"
        )
    )
    mileage_range: Optional[list[float]] = Field(
        default=None,
        description="里程区间 [start_mileage, end_mileage]，如 [5268.0, 6100.0]；不传则覆盖中线全段",
    )


@tool(args_schema=ClipBoundaryInput)
def clip_to_boundary(
    dataset_id: int,
    centerline_id: int,
    coverage_range: float,
    clip_mode: str,
    mileage_range: Optional[list[float]] = None,
) -> dict[str, Any]:
    """
    沿工程中线创建缓冲区并裁剪数据实体，返回边界实体ID（存于 data 字段）。

    两种裁剪模式均以中线为基准：
    - tunnel：创建三维缓冲区，适用于洞内里程定位数据（如 AHD、TEM 等）；
    - regional：创建二维缓冲区，适用于工程尺度大范围地表数据（如 DEM、DOM 等）。

    可通过 mileage_range 指定里程区间以限定裁剪范围；不传则覆盖中线全段。
    裁剪结果（边界实体ID）可传给 spatial_sample 的 boundary_entity_id 参数。

    注意：若用户未明确指出覆盖范围，请直接跳过本工具，不要执行裁剪操作。
    """
    logger.info(
        "clip_to_boundary 调用 | dataset_id=%r, centerline_id=%r, "
        "clip_mode=%r, coverage_range=%r, mileage_range=%r",
        dataset_id, centerline_id, clip_mode, coverage_range, mileage_range,
    )
    try:
        import DTPyRuntime as dtpr

        boundary_entity_id = dtpr.clip_to_boundary(
            dataset_id, centerline_id, coverage_range, clip_mode, mileage_range
        )

        if boundary_entity_id is None or boundary_entity_id == 0xFFFFFFFF:
            return ToolOutput(success=False, message="区域裁剪失败: 运行时返回无效实体ID").model_dump()
        return ToolOutput(success=True, data=boundary_entity_id).model_dump()

    except NotImplementedError as e:
        logger.warning("clip_to_boundary 未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("clip_to_boundary 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"区域裁剪失败: {e}").model_dump()
