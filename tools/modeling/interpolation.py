"""工具: 空间插值"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


class SpatialInterpolateInput(BaseModel):
    control_points_id: int = Field(
        description="控制点数据实体ID（含三维坐标 + 属性值，如钻孔数据）"
    )
    target_grid_id: int = Field(
        description="目标体素网格实体ID（定义插值范围和分辨率）"
    )
    attribute: str = Field(description="需要插值的属性名（如 'lithology_code'、'depth'）")
    method: str = Field(
        default="kriging",
        description="插值方法: IDW（反距离加权）|kriging（克里金）|RBF（径向基函数）"
    )
    method_params: dict = Field(
        default={},
        description="方法参数，如 kriging 的 {'variogram_model': 'spherical', 'nlags': 6}"
    )


@tool(args_schema=SpatialInterpolateInput)
def interpolate_spatial(
    control_points_id: int,
    target_grid_id: int,
    attribute: str,
    method: str = "kriging",
    method_params: dict = {},
) -> dict[str, Any]:
    """
    基于稀疏控制点（钻孔数据、地表采样点）在三维体素网格中进行空间插值，
    生成连续的属性场（如岩性概率、地层深度、物性参数）。

    方法选择建议：
    - IDW：局部各向同性数据，计算快
    - Kriging：有空间自相关性的地质属性（推荐），提供不确定性估计
    - RBF：规则曲面拟合，适合地层界面
    """
    logger.info(
        "interpolate_spatial 调用 | control_points_id=%s, target_grid_id=%s, attribute=%s, method=%s",
        control_points_id, target_grid_id, attribute, method
    )

    try:
        import DTPyRuntime as dtpr

        output_entity_id = dtpr.interpolate_spatial(
            control_points_id=control_points_id,
            target_grid_id=target_grid_id,
            attribute=attribute,
            method=method,
            method_params=method_params
        )

        logger.info("空间插值完成 | 输出实体 ID=%s", output_entity_id)

        return ToolOutput(
            success=True,
            data={"entity_id": output_entity_id},
            message=f"空间插值成功，输出实体 ID {output_entity_id}",
            metadata={
                "control_points_id": control_points_id,
                "target_grid_id": target_grid_id,
                "attribute": attribute,
                "method": method,
            },
        ).model_dump()

    except NotImplementedError as e:
        logger.warning("interpolate_spatial 暂未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("空间插值失败 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"空间插值失败: {e}").model_dump()
