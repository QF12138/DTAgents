"""工具: 纹理贴图
- apply_texture  : 将影像贴到三维模型
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# apply_texture：DOM 正射影像 → 地表三角网纹理
# ─────────────────────────────────────────────────────────────
class ApplyTextureInput(BaseModel):
    surface_entity_id: int = Field(
        description="三角网实体 ID（通常由 delaunay_triangulation 输出）"
    )
    dom_dataset_id: int = Field(
        description="DOM 数据集 ID（数据类型须为 DOM），作为纹理图像来源"
    )


@tool(args_schema=ApplyTextureInput)
def apply_texture(
    surface_entity_id: int,
    dom_dataset_id: int,
) -> dict[str, Any]:
    """
    将 DOM 正射影像作为纹理贴图到地形三角网模型上，生成带真彩色纹理的地表模型。
    """
    logger.info(
        "apply_texture 调用 | surface_entity_id=%s, dom_dataset_id=%s",
        surface_entity_id, dom_dataset_id
    )

    try:
        import DTPyRuntime as dtpr
        result_entity_id = dtpr.bind_texture(
            surface_entity_id,
            dom_dataset_id
        )

        logger.info("apply_texture 完成 | 输出实体 entity_id=%s", result_entity_id)
        
        return ToolOutput(
            success=True,
            data={"entity_id": result_entity_id},
            message=f"纹理贴图成功，输出实体 ID {result_entity_id}",
            metadata={
                "surface_entity_id": surface_entity_id,
                "dom_dataset_id": dom_dataset_id,
            },
        ).model_dump()

    except NotImplementedError as e:
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("apply_texture 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"DOM 纹理贴图失败: {e}").model_dump()
