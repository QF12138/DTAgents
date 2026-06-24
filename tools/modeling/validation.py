"""工具: 模型验证"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


class ValidateModelInput(BaseModel):
    model_id: int = Field(description="待验证的地质模型实体ID")
    drillhole_id: Optional[int] = Field(
        default=None,
        description="钻孔实测数据实体ID，用于与模型预测值交叉验证"
    )
    constraints: dict = Field(
        default={},
        description="地质约束条件，如 {'no_floating_bodies': True, 'layer_continuity': True}"
    )


@tool(args_schema=ValidateModelInput)
def validate_model(
    model_id: int,
    drillhole_id: Optional[int] = None,
    constraints: dict = {},
) -> dict[str, Any]:
    """
    对生成的地质模型进行一致性验证：
    1) 钻孔对比验证（模型预测值 vs 钻孔实测岩性，计算准确率/RMSE）
    2) 地质规律性检查（地层连续性、无悬空体素、无负厚度地层）
    3) 与输入约束数据的符合性评估
    返回验证报告，包含误差统计和不合理区域标记（位置 + 类型）。
    建议在属性融合后、导出模型前执行。
    """
    logger.info(
        "validate_model 调用 | model_id=%s, drillhole_id=%s",
        model_id, drillhole_id
    )

    try:
        import DTPyRuntime as dtpr

        result = dtpr.validate_model(
            model_id=model_id,
            drillhole_id=drillhole_id,
            constraints=constraints
        )

        logger.info("模型验证完成 | 通过=%s", result.get("passed"))

        return ToolOutput(
            success=True,
            data=result,
            message="模型验证完成",
            metadata={
                "model_id": model_id,
                "drillhole_id": drillhole_id,
            },
        ).model_dump()

    except NotImplementedError as e:
        logger.warning("validate_model 暂未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("模型验证失败 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"模型验证失败: {e}").model_dump()
