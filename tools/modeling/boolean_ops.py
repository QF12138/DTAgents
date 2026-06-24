"""工具: 布尔运算"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


class BooleanOpInput(BaseModel):
    mesh_a_id: int = Field(description="第一个三角网曲面实体ID（被操作对象）")
    mesh_b_id: int = Field(description="第二个三角网曲面实体ID（操作工具）")
    operation: str = Field(
        description="布尔运算类型: union（合并）|intersection（交集）|difference（差集，A-B）|split（A 被 B 切割）"
    )


@tool(args_schema=BooleanOpInput)
def boolean_operation(
    mesh_a_id: int,
    mesh_b_id: int,
    operation: str,
) -> dict[str, Any]:
    """
    对两个三角网曲面执行布尔运算，用于实现地质体的切割、合并、差集操作。
    """
    logger.info(
        "boolean_operation 调用 | mesh_a_id=%s, mesh_b_id=%s, operation=%s",
        mesh_a_id, mesh_b_id, operation
    )

    try:
        import DTPyRuntime as dtpr

        output_entity_id = dtpr.boolean_operation(
            mesh_a_id=mesh_a_id,
            mesh_b_id=mesh_b_id,
            operation=operation
        )

        logger.info("布尔运算完成 | 输出实体 ID=%s", output_entity_id)

        return ToolOutput(
            success=True,
            data={"entity_id": output_entity_id},
            message=f"布尔运算成功，输出实体 ID {output_entity_id}",
            metadata={
                "mesh_a_id": mesh_a_id,
                "mesh_b_id": mesh_b_id,
                "operation": operation,
            },
        ).model_dump()

    except NotImplementedError as e:
        logger.warning("boolean_operation 暂未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("布尔运算失败 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"布尔运算失败: {e}").model_dump()
