"""工具: 空间点采样（钻孔类数据）"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# spatial_sample：空间点采样
# ─────────────────────────────────────────────────────────────
class SpatialSampleInput(BaseModel):
    dataset_id: int = Field(
        description="输入数据的运行时实体ID（由初始化阶段 import_dataset 返回）"
    )
    resolution: float = Field(
        description="采样分辨率，单位：米。控制采样点的间距密度"
    )
    boundary_entity_id: Optional[int] = Field(
        default=None,
        description="边界实体ID（由 clip_to_boundary 返回），限定采样范围；不传则对全实体采样",
    )


@tool(args_schema=SpatialSampleInput)
def spatial_sample(
    dataset_id: int,
    resolution: float,
    boundary_entity_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    对数据实体按指定分辨率进行三维空间采样，提取语义点属性值，返回采样结果实体ID（存于 data 字段）。

    本工具仅适用于钻孔类数据（AHD、DBH、DRL）剖面类数据（TEM、GPR、TFR），
    除非用户明确说明需要空间采样，否则不执行本工具。

    可选传入 boundary_entity_id（由 clip_to_boundary 生成）以限定采样范围；
    不传则对整个数据实体进行全量采样。
    """
    logger.info(
        "spatial_sample 调用 | dataset_id=%r, resolution=%r, boundary_entity_id=%r",
        dataset_id, resolution, boundary_entity_id,
    )
    try:
        import DTPyRuntime as dtpr

        result_id = dtpr.spatial_sample(dataset_id, resolution, boundary_entity_id)

        if result_id is None or result_id == 0xFFFFFFFF:
            return ToolOutput(success=False, message="空间采样失败: 运行时返回无效实体ID").model_dump()
        return ToolOutput(success=True, data=result_id).model_dump()

    except NotImplementedError as e:
        logger.warning("spatial_sample 未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("spatial_sample 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"空间采样失败: {e}").model_dump()
