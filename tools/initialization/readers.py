"""工具: 数据读取（统一入口，内部按类型分发）"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from database import db
from tools.common import ToolOutput

logger = logging.getLogger(__name__)


class ReadDataInput(BaseModel):
    dataset_path: str = Field(description="文件路径")
    dataset_type: str = Field(description="数据类型")
    options: bool = Field(
        default=False, description="是否将读取的数据合并为组"
    )


@tool(args_schema=ReadDataInput)
def import_dataset(dataset_path: str, 
              dataset_type: str,
              options: dict = {}
              ) -> dict[str, Any]:
    """
    根据数据的文件路径读取。
    """
    logger.info("import_dataset 调用 | dataset_path=%r, dataset_type=%r", dataset_path, dataset_type)
    try:
        # TODO: 接入 DTGeoStudio 实现数据读取
        import DTPyRuntime as dtpr
        entity_id = dtpr.read_data(dataset_path, dataset_type)

        logger.info("import_dataset 完成 | DTGeoStudio服务平台 entity_id=%s", entity_id)
        return ToolOutput(
            success=True,
            data={"entity_id", entity_id},
            message=f"数据实体ID {entity_id} ({dataset_type}) 已成功读取"
        ).model_dump()

    except Exception as e:
        logger.error("import_dataset 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"数据读取失败: {e}").model_dump()
