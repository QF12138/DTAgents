"""Pydantic 数据模型 - 与数据库表结构对应（Schema v3）"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ──────────────────────────────────────────────
# 1. 工程项目
# ──────────────────────────────────────────────
class Project(BaseModel):
    project_id: str = Field(default_factory=_new_uuid)
    name: str
    type: Optional[str] = None                      # highway|railway|metro|municipal|waterway
    description: Optional[str] = None
    default_crs: str = "EPSG:4547"
    created_at: Optional[datetime] = None


# ──────────────────────────────────────────────
# 2. 工点（直属工程，合并了原设计段落的关键字段）
#
#    centerline_id / profile_id 逻辑上指向 datasets.id，
#    但数据库层不设 FK（避免与 datasets.site_id → work_sites
#    形成循环引用），由应用层负责校验其有效性。
# ──────────────────────────────────────────────
class WorkSite(BaseModel):
    site_id: str = Field(default_factory=_new_uuid)
    project_id: str
    name: str
    type: Optional[str] = None                       # tunnel|bridge|open_cut|station|culvert
    mileage_prefix: Optional[str] = None             # 里程冠号，如 X1DK、ZDK、YDK
    centerline_id: Optional[str] = None              # 关联中线数据集 (datasets.id)
    profile_id: Optional[str] = None                 # 关联设计断面轮廓数据集 (datasets.id)
    construction_direction: Optional[str] = None     # forward（大里程）| backward（小里程）
    start_mileage: Optional[float] = None            # 工点起始里程（m）
    end_mileage: Optional[float] = None              # 工点终止里程（m）
    description: Optional[str] = None
    created_at: Optional[datetime] = None


# ──────────────────────────────────────────────
# 3. 数据集基础（不含定位字段）
# ──────────────────────────────────────────────
class Dataset(BaseModel):
    id: str = Field(default_factory=_new_uuid)
    project_id: Optional[str] = None
    site_id: Optional[str] = None                   # 可为 None（跨工点数据）
    name: str
    data_type: str
    # 地表/区域类：DEM DOM DRL EGM BIM
    # 洞内/里程类：TSP TEM GPR AHD DBH TFR TBM RDR IST EMS
    positioning_type: str                            # spatial | mileage | both
    file_path: str
    file_format: Optional[str] = None
    file_size_mb: Optional[float] = None
    checksum: Optional[str] = None                  # MD5
    survey_date_start: Optional[str] = None         # ISO8601
    survey_date_end: Optional[str] = None
    status: str = "raw"                              # raw|validated|processed|archived
    quality_flag: int = 0                            # 0:未验证 1:通过 2:警告 3:失败
    tags: Optional[list[str]] = None
    description: Optional[str] = None
    extra_meta: Optional[dict[str, Any]] = None     # 类型特定属性
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ──────────────────────────────────────────────
# 4. 地理空间范围（与 Dataset 1:1）
# ──────────────────────────────────────────────
class SpatialExtent(BaseModel):
    dataset_id: str
    crs: str                                        # 如 'EPSG:4547'
    bbox_minx: Optional[float] = None
    bbox_miny: Optional[float] = None
    bbox_maxx: Optional[float] = None
    bbox_maxy: Optional[float] = None
    bbox_minz: Optional[float] = None               # 最小高程（m），二维数据为 None
    bbox_maxz: Optional[float] = None
    resolution_m: Optional[float] = None            # 空间分辨率（m），栅格数据填写
    map_scale: Optional[str] = None                 # 比例尺，如 '1:2000'


# ──────────────────────────────────────────────
# 5. 里程范围（与 Dataset 1:1）
#
#    中线通过 datasets.site_id → work_sites.centerline_id 间接获取，
#    不在本表冗余存储。
# ──────────────────────────────────────────────
class MileageExtent(BaseModel):
    dataset_id: str
    start_mileage: float                            # 起始里程（m）
    end_mileage: Optional[float] = None             # 终止里程（m），None 表示点状数据
    offset_lateral: float = 0.0                     # 横向偏移（m，右正左负）
    offset_vertical: float = 0.0                    # 竖向偏移（m，上正下负）
    measurement_dir: Optional[str] = None           # forward | backward（相对中线推进方向）


# ──────────────────────────────────────────────
# 6. 处理历史记录
# ──────────────────────────────────────────────
class ProcessingHistory(BaseModel):
    id: Optional[int] = None
    project_id: Optional[str] = None
    site_id: Optional[str] = None
    agent_name: str
    tool_name: str
    input_datasets: Optional[list[str]] = None     # dataset_id 列表
    output_datasets: Optional[list[str]] = None
    parameters: Optional[dict[str, Any]] = None
    status: str = "pending"                         # pending|running|success|failed
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: Optional[datetime] = None


# ──────────────────────────────────────────────
# 7. 地质模型注册（支持双坐标体系）
#
#    centerline_id → datasets.id（中线数据集）
# ──────────────────────────────────────────────
class ModelRegistry(BaseModel):
    id: str = Field(default_factory=_new_uuid)
    project_id: Optional[str] = None
    site_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    positioning_type: str = "spatial"               # spatial | mileage

    # 体素网格参数
    voxel_resolution: Optional[float] = None        # 网格分辨率（m）
    grid_nx: Optional[int] = None
    grid_ny: Optional[int] = None
    grid_nz: Optional[int] = None

    # 地理坐标范围（positioning_type = 'spatial' 时填写）
    crs_epsg: Optional[int] = None
    bbox_minx: Optional[float] = None
    bbox_miny: Optional[float] = None
    bbox_minz: Optional[float] = None
    bbox_maxx: Optional[float] = None
    bbox_maxy: Optional[float] = None
    bbox_maxz: Optional[float] = None

    # 里程范围（positioning_type = 'mileage' 时填写）
    centerline_id: Optional[str] = None             # 关联中线数据集 (datasets.id)
    start_mileage: Optional[float] = None           # 模型起始里程（m）
    end_mileage: Optional[float] = None             # 模型终止里程（m）
    model_radius: Optional[float] = None            # 建模半径（m，以中线为轴）

    # 文件存储（元数据引用）
    file_path: Optional[str] = None
    file_format: Optional[str] = None
    file_size_mb: Optional[float] = None

    # 来源追踪
    attributes: Optional[list[str]] = None
    input_dataset_ids: Optional[list[str]] = None
    processing_ids: Optional[list[int]] = None

    created_at: Optional[datetime] = None
    version: int = 1
