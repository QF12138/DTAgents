"""工具: 元数据查询"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import QUERY_RESULT_CONFIRM_THRESHOLD, MILEAGE_DATA_TYPES
from database import db
from tools.common import ToolOutput
from utils.mileage import parse_mileage_str

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# query_metadata：数据集查询
# ─────────────────────────────────────────────────────────────
class QueryMetadataInput(BaseModel):
    project_id: Optional[str] = Field(
        default=None, description="按工程 ID 过滤，先调用 query_hierarchy(level = project) 获取工程ID"
    )
    site_ids: Optional[list[str]] = Field(
        default=None, description="按工点 ID 列表过滤，调用 query_hierarchy(level = site) 获取对应工点列表"
    )
    data_type: Optional[str] = Field(
        default=None, description="数据类型过滤：DEM|DOM|DRL|EGM|BIM|TSP|TEM|GPR|AHD|DBH|TFR|TBM|RDR|IST|EMS"
    )
    time_range: Optional[list[str]] = Field(
        default=None, description="采集时间范围过滤，格式 [start_iso, end_iso]，如 ['2024-01-01', '2024-12-31']"
    )
    mileage_range: Optional[list[float]] = Field(
        default=None, description="里程范围过滤 [start_m, end_m]，如 [1251, 1355]"
    )


@tool(args_schema=QueryMetadataInput)
def query_metadata(
    project_id: Optional[str] = None,
    site_ids: Optional[list[str]] = None,
    data_type: Optional[str] = None,
    time_range: Optional[list[str]] = None,
    mileage_range: Optional[list[float]] = None,
) -> dict[str, Any]:
    """
    查询元数据索引库，支持按工程/工点/数据类型/里程范围/时间范围筛选。
    返回数据集列表，当结果条数超过确认阈值时，仅返回按类型汇总的统计摘要，请用户确认。
    """
    logger.info(
        "query_metadata 调用 | project_id=%r, site_ids=%r, data_type=%r, "
        "mileage_range=%s, time_range=%s",
        project_id, site_ids, data_type, mileage_range, time_range,
    )
    try:
        results = db.query_datasets(
            project_id=project_id,
            site_ids=site_ids,
            data_type=data_type,
            mileage_range=mileage_range,
            time_range=time_range,
        )

        count = len(results)

        # 结果超阈值：返回摘要，要求用户确认或缩小范围
        if count > QUERY_RESULT_CONFIRM_THRESHOLD:
            by_type: dict[str, int] = {}
            for r in results:
                t = r.get("data_type", "unknown")
                by_type[t] = by_type.get(t, 0) + 1
            type_summary = "、".join(f"{t}×{n}" for t, n in sorted(by_type.items()))
            logger.info("query_metadata 完成 | 查询到 %d 个数据集，超过确认阈值", count)
            return ToolOutput(
                success=True,
                data=[],
                message=(
                    f"查询到 {count} 个数据集，超过确认阈值（{QUERY_RESULT_CONFIRM_THRESHOLD} 条）。\n"
                    f"按类型分布：{type_summary}。\n"
                    "请向用户确认是否继续加载全部数据，或通过 data_type / mileage_range / time_range 缩小范围后重新查询。"
                ),
                metadata={
                    "count": count,
                    "needs_confirmation": True,
                    "by_type": by_type,
                },
            ).model_dump()

        # 判断是否存在里程定位类型数据，若有则自动补充中线/纵断面辅助数据
        auxiliary_data: dict[str, list[dict]] = {}
        mileage_types = {r["data_type"] for r in results if r.get("data_type") in MILEAGE_DATA_TYPES}
        if mileage_types:
            raw_site_ids = list({r["site_id"] for r in results if r.get("site_id")})
            if raw_site_ids:
                site_rows = db.get_work_sites_by_ids(raw_site_ids)

                centerline_ids = {s["centerline_id"] for s in site_rows if s.get("centerline_id")}
                profile_ids    = {s["profile_id"]    for s in site_rows if s.get("profile_id")}

                aux_keep = {"name", "data_type", "file_path", "description"}
                centerlines = [
                    {k: v for k, v in (db.get_dataset(cid) or {}).items() if k in aux_keep}
                    for cid in centerline_ids
                ]
                profiles = [
                    {k: v for k, v in (db.get_dataset(pid) or {}).items() if k in aux_keep}
                    for pid in profile_ids
                ]
                auxiliary_data = {
                    "centerlines": [c for c in centerlines if c],
                    "profiles":    [p for p in profiles    if p],
                }

        keep_keys = {"name", "data_type", "description", "file_path"}
        trimmed = [{k: v for k, v in r.items() if k in keep_keys} for r in results]

        meta: dict = {"raw_data_count": count}
        if auxiliary_data:
            meta["auxiliary_data"] = auxiliary_data

        logger.info(
            "query_metadata 完成 | 查询到 %d 个数据集，centerlines=%d, profiles=%d",
            count,
            len(auxiliary_data.get("centerlines", [])),
            len(auxiliary_data.get("profiles", [])),
        )
        return ToolOutput(
            success=True,
            data=trimmed,
            message=f"查询到 {count} 个数据集" + ("，附加中线/纵断面辅助数据" if auxiliary_data else ""),
            metadata=meta,
        ).model_dump()

    except Exception as e:
        logger.error("query_metadata 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"元数据查询失败: {e}").model_dump()


# ─────────────────────────────────────────────────────────────
# query_hierarchy：工程层级查询
# ─────────────────────────────────────────────────────────────
class QueryHierarchyInput(BaseModel):
    level: str = Field(
        description="查询层级：'project'（所有工程）| 'work_site'（工点列表）"
    )
    project_id: Optional[str] = Field(
        default=None, description="工程 ID，查询 work_site 时按工程过滤"
    )
    mileage_infos: Optional[list[str]] = Field(
        default=None, description="通常为 冠号+里程值 形式（如 X1DK2+539）"
    )


@tool(args_schema=QueryHierarchyInput)
def query_hierarchy(
    level: str,
    project_id: Optional[str] = None,
    mileage_infos: Optional[list[str]] = None
) -> dict[str, Any]:
    """
    查询工程层级信息。

    使用场景：
    - 查询所有工程：level='project'
    - 查询工点列表：level='work_site'，可按 project_id / mileage_prefix 过滤
    - 里程信息筛选：level='work_site' + mileage_infos=[...]，返回该里程冠号下所有工点
    """
    logger.info(
        "query_hierarchy 调用 | level=%r, project_id=%r, mileage_infos=%r",
        level, project_id, mileage_infos
    )
    try:
        valid_levels = ("project", "work_site")
        if level not in valid_levels:
            logger.warning("query_hierarchy 失败 | 不支持的查询层级: %s", level)
            return ToolOutput(
                success=False,
                message=f"不支持的查询层级: {level}，可选: {valid_levels}",
            ).model_dump()
        
        start_prefix: Optional[str] = None
        start_mile: Optional[float] = None
        end_mile: Optional[float] = None

        if mileage_infos:
            start_prefix, start_mile = parse_mileage_str(mileage_infos[0])
            end_prefix, end_mile = parse_mileage_str(mileage_infos[-1])

        if level == "project":
            rows = db.list_projects()
            results = [
                {"project_id": r["project_id"], "name": r.get("name", ""), "description": r.get("description", "")}
                for r in rows
            ]
        else:  # work_site
            rows = db.list_work_sites(
                project_id=project_id,
                mileage_prefix=start_prefix,
            )
            results = [
                {"site_id": r["site_id"], "name": r.get("name", ""), "description": r.get("description", "")}
                for r in rows
            ]

        logger.info("query_hierarchy 完成 | level=%s, 查询到 %d 条记录，mileage_range=[%s, %s]", level, len(results), start_mile, end_mile)

        meta: dict = {"level": level, "count": len(results)}
        if start_mile is not None or end_mile is not None:
            meta["mileage_range"] = [start_mile, end_mile]

        return ToolOutput(
            success=True,
            data=results,
            message=f"查询到 {len(results)} 条 {level} 记录" + (
                f"，里程区间 [{start_mile}, {end_mile}]" if start_mile is not None else ""
            ),
            metadata=meta,
        ).model_dump()

    except Exception as e:
        logger.error("query_hierarchy 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"层级查询失败: {e}").model_dump()
