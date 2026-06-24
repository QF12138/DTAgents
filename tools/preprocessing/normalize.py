"""工具: 属性标准化 & 异常值过滤"""
from __future__ import annotations

from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput


# ─────────────────────────────────────────────────────────────
# 属性标准化
# ─────────────────────────────────────────────────────────────
class NormalizeInput(BaseModel):
    file_path: str = Field(description="输入数据文件路径")
    attributes: list[str] = Field(description="需要标准化的属性名列表")
    method: str = Field(
        default="minmax",
        description="标准化方法: minmax（[0,1]缩放）|zscore（均值0方差1）|log（对数变换）"
    )
    output_path: Optional[str] = Field(default=None, description="输出文件路径")


@tool(args_schema=NormalizeInput)
def normalize_attributes(
    file_path: str,
    attributes: list[str],
    method: str = "minmax",
    output_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    对多源数据的属性值进行标准化处理，消除量纲差异。
    是多源属性融合（如将地球物理参数与钻孔岩性特征联合用于 ML 分类）的前提。
    minmax：适合已知值域的属性（如深度、电阻率）；
    zscore：适合正态分布属性；
    log：适合正偏态分布（如电阻率、渗透率）。
    """
    try:
        # TODO: 接入自有库实现
        # from your_lib.preprocessing import normalize
        # result_path = normalize(file_path, attributes, method, output_path)

        raise NotImplementedError("请接入自有库实现: your_lib.preprocessing.normalize")

    except NotImplementedError as e:
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        return ToolOutput(success=False, message=f"属性标准化失败: {e}").model_dump()


# ─────────────────────────────────────────────────────────────
# 异常值过滤
# ─────────────────────────────────────────────────────────────
class FilterOutliersInput(BaseModel):
    file_path: str = Field(description="输入数据文件路径")
    method: str = Field(
        default="statistical",
        description="过滤方法: statistical（均值±N倍标准差）|radius（半径邻域密度）|iqr（四分位距）"
    )
    params: dict = Field(
        default={},
        description="方法参数，如 {'std_multiplier': 3}（statistical）或 {'k': 6}（radius）"
    )
    output_path: Optional[str] = Field(default=None, description="输出文件路径")


@tool(args_schema=FilterOutliersInput)
def filter_outliers(
    file_path: str,
    method: str = "statistical",
    params: dict = {},
    output_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    对数据进行去噪处理，移除统计异常值或孤立点。
    适用于存在测量误差的钻孔数据、地球物理数据。
    statistical：适合属性值异常检测；radius：适合点云稀疏点去除；
    iqr：对非正态分布数据更鲁棒。
    """
    try:
        # TODO: 接入自有库实现
        # from your_lib.preprocessing import filter_noise
        # result_path = filter_noise(file_path, method, params, output_path)

        raise NotImplementedError("请接入自有库实现: your_lib.preprocessing.filter_noise")

    except NotImplementedError as e:
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        return ToolOutput(success=False, message=f"异常值过滤失败: {e}").model_dump()
