"""工具: 数据验证"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from database import db
from tools.common import ToolOutput

logger = logging.getLogger(__name__)


class ValidateDataInput(BaseModel):
    dataset_id: str = Field(description="需要验证的数据集 ID")
    check_coverage: bool = Field(
        default=True,
        description=(
            "覆盖范围检查：spatial 类型检查是否覆盖工程区域；"
            "mileage 类型检查里程是否在所属工点范围内"
        )
    )
    check_value_range: bool = Field(
        default=True, description="检查数值属性是否存在异常值（超出地质合理范围）"
    )
    check_field_completeness: bool = Field(
        default=True, description="检查必需字段完整性（坐标、高程、岩性编码等）"
    )


@tool(args_schema=ValidateDataInput)
def validate_data(
    dataset_id: str,
    check_coverage: bool = True,
    check_value_range: bool = True,
    check_field_completeness: bool = True,
) -> dict[str, Any]:
    """
    对数据集进行质量验证，验证结果更新元数据库中的 quality_flag。
    quality_flag: 0=未验证, 1=通过, 2=警告（有问题但可用）, 3=失败（不可用）
    """
    logger.info(
        "validate_data 调用 | dataset_id=%r, check_coverage=%s, "
        "check_value_range=%s, check_field_completeness=%s",
        dataset_id, check_coverage, check_value_range, check_field_completeness,
    )
    try:
        ds = db.get_dataset_full(dataset_id)
        if ds is None:
            logger.warning("validate_data 失败 | 数据集不存在: %s", dataset_id)
            return ToolOutput(
                success=False,
                message=f"数据集不存在: {dataset_id}",
            ).model_dump()

        # 基础检查：文件是否存在
        file_path = ds["file_path"]
        if not Path(file_path).exists():
            logger.warning("validate_data 失败 | 文件不存在: %s", file_path)
            db.update_dataset_status(dataset_id, "validated", quality_flag=3)
            return ToolOutput(
                success=False,
                message=f"文件不存在: {file_path}",
                metadata={"quality_flag": 3, "reason": "file_missing"},
            ).model_dump()

        positioning_type = ds.get("positioning_type", "spatial")
        issues: list[str] = []
        warnings: list[str] = []

        # 里程定位数据的元数据完整性检查
        if positioning_type in ("mileage", "both") and check_field_completeness:
            if not ds.get("mileage_centerline_id"):
                issues.append("里程定位数据缺少 centerline_id")
            if ds.get("start_mileage") is None:
                issues.append("里程定位数据缺少 start_mileage")
            else:
                # 检查里程是否在中线范围内
                cl = db.get_centerline(ds["mileage_centerline_id"]) if ds.get("mileage_centerline_id") else None
                if cl and cl.get("mileage_start") is not None:
                    if ds["start_mileage"] < cl["mileage_start"] or (
                        cl.get("mileage_end") is not None
                        and ds["start_mileage"] > cl["mileage_end"]
                    ):
                        warnings.append(
                            f"start_mileage={ds['start_mileage']} 超出中线里程范围 "
                            f"[{cl['mileage_start']}, {cl['mileage_end']}]"
                        )

        # 地理空间数据的元数据完整性检查
        if positioning_type in ("spatial", "both") and check_field_completeness:
            if not ds.get("crs"):
                warnings.append("空间定位数据未指定坐标系（crs）")

        # 确定 quality_flag
        if issues:
            quality_flag = 3  # 失败
        elif warnings:
            quality_flag = 2  # 警告
        else:
            quality_flag = 1  # 通过（文件存在 + 元数据完整）

        db.update_dataset_status(dataset_id, "validated", quality_flag=quality_flag)

        # TODO: 接入 DTGeoStudio 实现深度验证
        # from ecs_bridge import validate_dataset
        # report = validate_dataset(
        #     file_path, ds["data_type"], ds["positioning_type"],
        #     check_coverage=check_coverage,
        #     check_value_range=check_value_range,
        # )
        # quality_flag = 1 if report["passed"] else (2 if report["warnings"] else 3)
        # db.update_dataset_status(dataset_id, "validated", quality_flag=quality_flag)

        flag_desc = {1: "通过", 2: "警告", 3: "失败"}
        msg = (
            f"验证完成: quality_flag={quality_flag}（{flag_desc[quality_flag]}）"
            + (f"，问题: {'; '.join(issues)}" if issues else "")
            + (f"，警告: {'; '.join(warnings)}" if warnings else "")
        )
        log_fn = logger.warning if quality_flag == 3 else (
            logger.warning if quality_flag == 2 else logger.info
        )
        log_fn("validate_data 完成 | dataset_id=%s, %s", dataset_id, msg)
        return ToolOutput(
            success=quality_flag != 3,
            message=msg,
            metadata={
                "dataset_id": dataset_id,
                "quality_flag": quality_flag,
                "issues": issues,
                "warnings": warnings,
                "positioning_type": positioning_type,
            },
        ).model_dump()

    except Exception as e:
        logger.error("validate_data 异常 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"数据验证失败: {e}").model_dump()
