"""工具: 空间投影转换（里程↔三维空间 / EPSG CRS 互转）"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field, model_validator

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# project_transform：空间投影转换
# ─────────────────────────────────────────────────────────────
class ProjectTransformInput(BaseModel):
    dataset_id: int = Field(
        description="输入数据的运行时实体ID（由初始化阶段 import_dataset 返回）"
    )
    transform_type: str = Field(
        description=(
            "转换类型: "
            "mileage_to_spatial（里程坐标转三维空间坐标，需同时提供 centerline_id 和 profile_id）"
            " | "
            "crs_transform（坐标系转换，需提供 target_crs，可选 source_crs）"
        )
    )
    centerline_id: Optional[int] = Field(
        default=None,
        description="工程中线实体ID。transform_type=mileage_to_spatial 时必填",
    )
    profile_id: Optional[int] = Field(
        default=None,
        description="工程纵断面实体ID。transform_type=mileage_to_spatial 时必填",
    )
    source_crs: Optional[str] = Field(
        default=None,
        description="源坐标系 EPSG 代码（如 'EPSG:4326'）。transform_type=crs_transform 时可选，None 则自动识别",
    )
    target_crs: Optional[str] = Field(
        default=None,
        description="目标坐标系 EPSG 代码（如 'EPSG:4547'）。transform_type=crs_transform 时必填",
    )

    @model_validator(mode="after")
    def check_conditional_fields(self) -> "ProjectTransformInput":
        if self.transform_type == "mileage_to_spatial":
            if self.centerline_id is None or self.profile_id is None:
                raise ValueError(
                    "transform_type='mileage_to_spatial' 时，centerline_id 和 profile_id 均为必填项"
                )
        elif self.transform_type == "crs_transform":
            if self.target_crs is None:
                raise ValueError(
                    "transform_type='crs_transform' 时，target_crs 为必填项"
                )
        return self


@tool(args_schema=ProjectTransformInput)
def project_transform(
    dataset_id: int,
    transform_type: str,
    centerline_id: Optional[int] = None,
    profile_id: Optional[int] = None,
    source_crs: Optional[str] = None,
    target_crs: Optional[str] = None,
) -> dict[str, Any]:
    """
    将输入数据实体进行空间投影转换，返回转换后的新实体ID（存于 data 字段）。

    支持两种转换模式：
    - mileage_to_spatial：将里程坐标系数据（如 AHD、DBH、TEM 等隧道洞内数据）转换为
      三维空间坐标，需要中线实体（centerline_id）和纵断面实体（profile_id）定义三维参考系。
    - crs_transform：将数据从当前坐标系重投影到目标 EPSG 坐标系（如工程坐标系 EPSG:4547），
      需提供 target_crs，source_crs 可选（None 则自动识别）。
    """
    logger.info(
        "project_transform 调用 | dataset_id=%r, transform_type=%r, "
        "centerline_id=%r, profile_id=%r, source_crs=%r, target_crs=%r",
        dataset_id, transform_type, centerline_id, profile_id, source_crs, target_crs,
    )
    try:
        import DTPyRuntime as dtpr

        if transform_type == "mileage_to_spatial":
            result_id = dtpr.transform_mileage_to_spatial(dataset_id, centerline_id, profile_id)
        elif transform_type == "crs_transform":
            raise NotImplementedError("crs_transform 暂未在 DTGeoStudio 中实现")
        else:
            raise ValueError(f"不支持的 transform_type: {transform_type!r}")

        if result_id is None or result_id == 0xFFFFFFFF:
            return ToolOutput(success=False, message="坐标转换失败: 运行时返回无效实体ID").model_dump()
        return ToolOutput(success=True, data=result_id).model_dump()

    except NotImplementedError as e:
        logger.warning("project_transform 未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("project_transform 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"坐标转换失败: {e}").model_dump()
