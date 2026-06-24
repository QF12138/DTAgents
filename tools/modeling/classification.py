"""工具: 指标分级"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


class ClassifyIndicatorInput(BaseModel):
    voxel_grid_id: int = Field(
        description="三维体素属性场实体ID（如电阻率、波速、密度等）"
    )
    indicator_name: str = Field(
        description="指标名称，如 RSR（岩石应力比）、RQD（岩石质量指标）等"
    )
    grade_scheme: str = Field(
        description="分级方案: RSR|RMR|Q|GSI|RBI 等预定义方案，或自定义 JSON"
    )
    attribute: str = Field(
        description="进行分级的属性名，如 resistivity, velocity, density"
    )


@tool(args_schema=ClassifyIndicatorInput)
def classify_indicator(
    voxel_grid_id: int,
    indicator_name: str,
    grade_scheme: str,
    attribute: str,
) -> dict[str, Any]:
    """
    对三维体素属性场按指定分级方案进行指标分级。

    支持的分级方案：
    - RSR (Rock Structure Rating): 1-100
    - RMR (Rock Mass Rating): 0-100
    - Q (NGI Quality Index): 0.001-1000
    - GSI (Geological Strength Index): 0-100
    - RBI (Rock Mass Basic Index): 0-100

    输出体素网格包含分级类别和对应的工程分级值。
    """
    logger.info(
        "classify_indicator 调用 | voxel_grid_id=%s, indicator=%s, scheme=%s, attribute=%s",
        voxel_grid_id, indicator_name, grade_scheme, attribute
    )

    try:
        import DTPyRuntime as dtpr

        output_entity_id = dtpr.classify_indicator(
            voxel_grid_id=voxel_grid_id,
            indicator_name=indicator_name,
            grade_scheme=grade_scheme,
            attribute=attribute
        )

        logger.info("指标分级完成 | 输出实体 ID=%s", output_entity_id)

        return ToolOutput(
            success=True,
            data={"entity_id": output_entity_id},
            message=f"指标分级成功，{indicator_name} 分级完成，输出实体 ID {output_entity_id}",
            metadata={
                "voxel_grid_id": voxel_grid_id,
                "indicator_name": indicator_name,
                "grade_scheme": grade_scheme,
                "attribute": attribute,
            },
        ).model_dump()

    except NotImplementedError as e:
        logger.warning("classify_indicator 暂未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("指标分级失败 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"指标分级失败: {e}").model_dump()
