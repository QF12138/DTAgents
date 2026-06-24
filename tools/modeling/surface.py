"""工具: Delaunay 三角网 & 等值面提取"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Delaunay 三角网
# ─────────────────────────────────────────────────────────────
class DelaunayInput(BaseModel):
    raster_id: int = Field(description="栅格数据实体ID")
    precision: Optional[float] = Field(description="三角网建模精度，可不填")
    constraints_id: Optional[int] = Field(description="边界约束实体ID，可不填")
    with_uvcoords: Optional[bool] = Field(default=True, description="是否生成纹理坐标，可不填")


@tool(args_schema=DelaunayInput)
def delaunay_triangulation(
    raster_id: int,
    precision: Optional[float] = None,
    constraints_id: Optional[int] = None,
    with_uvcoords: Optional[bool] = True
) -> dict[str, Any]:
    """
    输入DEM栅格数据构造三角网，可选项：设置重采样精度，以及添加边界约束，
    不设置精度和边界约束则默认使用栅格边界及精度，默认生成纹理坐标。
    """

    logger.info(
        "delaunay_triangulation 调用 | raster_id=%s, precision=%s, constraints_id=%s, with_uvcoords=%s",
        raster_id, precision, constraints_id, with_uvcoords
    )

    try:
        import DTPyRuntime as dtpr

        output_entity_id = dtpr.surface_25d(
            raster_id, precision, constraints_id, with_uvcoords
        )

        logger.info("三角网构建完成 | 输出实体 ID=%s", output_entity_id)

        return ToolOutput(
            success=True,
            data={"entity_id": output_entity_id},
            message=f"三角网构建成功，输出实体 ID {output_entity_id}",
            metadata={
                "raster_id": raster_id,
                "constraints_id": constraints_id,
            },
        ).model_dump()

    except NotImplementedError as e:
        logger.warning("delaunay_triangulation 暂未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("三角网构建失败 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"三角网构建失败: {e}").model_dump()


# ─────────────────────────────────────────────────────────────
# 等值面提取
# ─────────────────────────────────────────────────────────────
class ExtractIsosurfaceInput(BaseModel):
    voxel_grid_id: int = Field(description="三维体素属性场实体ID")
    attribute: str = Field(description="提取等值面的属性名")
    isovalue: float = Field(description="等值面对应的属性值")


@tool(args_schema=ExtractIsosurfaceInput)
def extract_isosurface(
    voxel_grid_id: int,
    attribute: str,
    isovalue: float,
) -> dict[str, Any]:
    """
    从三维体素属性场中提取指定属性值的等值面（隐式曲面重建）。
    """
    logger.info(
        "extract_isosurface 调用 | voxel_grid_id=%s, attribute=%s, isovalue=%s",
        voxel_grid_id, attribute, isovalue
    )

    try:
        import DTPyRuntime as dtpr

        output_entity_id = dtpr.extract_isosurface(
            voxel_grid_id=voxel_grid_id,
            attribute=attribute,
            isovalue=isovalue
        )

        logger.info("等值面提取完成 | 输出实体 ID=%s", output_entity_id)

        return ToolOutput(
            success=True,
            data={"entity_id": output_entity_id},
            message=f"等值面提取成功，输出实体 ID {output_entity_id}",
            metadata={
                "voxel_grid_id": voxel_grid_id,
                "attribute": attribute,
                "isovalue": isovalue,
            },
        ).model_dump()

    except NotImplementedError as e:
        logger.warning("extract_isosurface 暂未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("等值面提取失败 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"等值面提取失败: {e}").model_dump()
