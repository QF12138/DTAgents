"""工具: 属性计算"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)


# 内置公式定义：从semantic_config.cpp中的basicFormula函数提取
# ConfigBasicEnum定义
FORMULA_DEFINITIONS = {
    # formulaId: 1 - 泊松比 (PrFromVpVs)
    # 公式: (V_p^2 - 2*V_s^2) / (2*(V_p^2 - V_s^2))
    # 变量: V_p(纵波速度), V_s(横波速度)
    1: {
        "name": "PrFromVpVs",
        "description": "根据纵波速度(V_p)和横波速度(V_s)计算泊松比",
        "formula": "(V_p^2 - 2*V_s^2) / (2*(V_p^2 - V_s^2))",
        "variables": ["V_p", "V_s"],
        "constants": {},
        "output_type": "PoissonsRatio",
    },
    # formulaId: 2 - 岩石密度 (RdFromVpVs)
    # 公式: 700.0 * (V_p * V_s)^0.08
    # 变量: V_p, V_s
    2: {
        "name": "RdFromVpVs",
        "description": "根据纵波速度(V_p)和横波速度(V_s)计算岩石密度",
        "formula": "700.0 * (V_p * V_s)^0.08",
        "variables": ["V_p", "V_s"],
        "constants": {},
        "output_type": "RockDensity",
    },
    # formulaId: 3 - 杨氏模量 (YmFromVpVsRd)
    # 公式: R_d * V_s^2 * ((3*V_p^2 - 4*V_s^2) / (V_p^2 - V_s^2)) * 10^-9
    # 变量: R_d(密度), V_p, V_s
    3: {
        "name": "YmFromVpVsRd",
        "description": "根据密度(R_d)、纵波速度(V_p)和横波速度(V_s)计算杨氏模量",
        "formula": "R_d * V_s^2 * ((3*V_p^2 - 4*V_s^2) / (V_p^2 - V_s^2)) * 10^-9",
        "variables": ["R_d", "V_p", "V_s"],
        "constants": {},
        "output_type": "YoungsModulus",
    },
    # formulaId: 4 - 体积模量 (BmFromVpVsRd)
    # 公式: R_d * (V_p^2 - 4*V_s^2/3) * 10^-9
    # 变量: R_d, V_p, V_s
    4: {
        "name": "BmFromVpVsRd",
        "description": "根据密度(R_d)、纵波速度(V_p)和横波速度(V_s)计算体积模量",
        "formula": "R_d * (V_p^2 - 4*V_s^2/3) * 10^-9",
        "variables": ["R_d", "V_p", "V_s"],
        "constants": {},
        "output_type": "BulkModulus",
    },
    # formulaId: 5 - 剪切模量 (SmFromVsRd)
    # 公式: (R_d * V_s^2) * 10^-9
    # 变量: R_d, V_s
    5: {
        "name": "SmFromVsRd",
        "description": "根据密度(R_d)和横波速度(V_s)计算剪切模量",
        "formula": "(R_d * V_s^2) * 10^-9",
        "variables": ["R_d", "V_s"],
        "constants": {},
        "output_type": "ShearModulus",
    },
    # formulaId: 6 - 单轴抗压强度 (UCSFromYm)
    # 公式: k * E_d^m，常数 k=7.1718, m=0.6062
    # 变量: E_d(杨氏模量)
    6: {
        "name": "UCSFromYm",
        "description": "根据杨氏模量(E_d)计算单轴抗压强度，包含常数 k=7.1718, m=0.6062",
        "formula": "k * E_d^m",
        "variables": ["E_d"],
        "constants": {"k": 7.1718, "m": 0.6062},
        "output_type": "UniCprsvStre",
    },
    # formulaId: 7 - 岩石孔隙度 (RpFromYm)
    # 公式: (log(E_r/E_d)) / k，常数 E_r=60, k=1.5
    # 变量: E_d(杨氏模量)
    7: {
        "name": "RpFromYm",
        "description": "根据杨氏模量(E_d)计算岩石孔隙度，包含常数 E_r=60, k=1.5",
        "formula": "(log(E_r/E_d)) / k",
        "variables": ["E_d"],
        "constants": {"E_r": 60.0, "k": 1.5},
        "output_type": "RockPorosity",
    },
    # formulaId: 8 - 完整度 (KvFromVp)
    # 公式: (V_p/V_r)^2，常数 V_r=5500
    # 变量: V_p
    8: {
        "name": "KvFromVp",
        "description": "根据纵波速度(V_p)计算完整度，包含常数 V_r=5500",
        "formula": "(V_p/V_r)^2",
        "variables": ["V_p"],
        "constants": {"V_r": 5500.0},
        "output_type": "CompletenessKv",
    },
    # formulaId: 9 - 地应力场评估基准 (IsFromUcsDpRd)
    # 公式: R_c * 10^3 / (R_d * D_p)
    # 变量: R_c(单轴抗压强度), R_d(密度), D_p(埋深)
    9: {
        "name": "IsFromUcsDpRd",
        "description": "根据单轴抗压强度(R_c)、密度(R_d)和埋深(D_p)计算地应力场评估基准",
        "formula": "R_c * 10^3 / (R_d * D_p)",
        "variables": ["R_c", "R_d", "D_p"],
        "constants": {},
        "output_type": "IGStressFieldEvalBase",
    },
    # formulaId: 10 - 水饱和度 (SwFromRwRtRp)
    # 公式: ((a*b*(0.55965+(165963.07/(w^0.995)))/(t+21.5))/(R*P^m))^n
    # 变量: P(孔隙度), R(电阻率)
    10: {
        "name": "SwFromRwRtRp",
        "description": "根据孔隙度(P)和电阻率(R)计算水饱和度，包含常数 a=0.005, b=1, m=1.5, n=0.5, w=1000, t=25",
        "formula": "((a*b*(0.55965+(165963.07/(w^0.995)))/(t+21.5))/(R*P^m))^n",
        "variables": ["P", "R"],
        "constants": {"a": 0.005, "b": 1.0, "m": 1.5, "n": 0.5, "w": 1000.0, "t": 25},
        "output_type": "SaturationOfWater",
    },
    # formulaId: 11 - 含水量 (WrFromSwRp)
    # 公式: S_w * R_p
    # 变量: S_w(饱和度), R_p(孔隙度)
    11: {
        "name": "WrFromSwRp",
        "description": "根据水饱和度(S_w)和孔隙度(R_p)计算含水量",
        "formula": "S_w * R_p",
        "variables": ["S_w", "R_p"],
        "constants": {},
        "output_type": "WaterRation",
    },
}


class CalculatePropertyInput(BaseModel):
    """基于公式ID的属性计算"""
    formulaId: int = Field(
        description=f"""内置公式ID，用于匹配计算公式。可选值及说明：
        1: PrFromVpVs - 泊松比 (需要: V_p纵波速度, V_s横波速度)
        2: RdFromVpVs - 岩石密度 (需要: V_p纵波速度, V_s横波速度)
        3: YmFromVpVsRd - 杨氏模量 (需要: R_d密度, V_p纵波速度, V_s横波速度)
        4: BmFromVpVsRd - 体积模量 (需要: R_d密度, V_p纵波速度, V_s横波速度)
        5: SmFromVsRd - 剪切模量 (需要: R_d密度, V_s横波速度)
        6: UCSFromYm - 单轴抗压强度 (需要: E_d杨氏模量)
        7: RpFromYm - 岩石孔隙度 (需要: E_d杨氏模量)
        8: KvFromVp - 完整度 (需要: V_p纵波速度)
        9: IsFromUcsDpRd - 地应力场评估基准 (需要: R_c单轴抗压强度, R_d密度, D_p埋深)
        10: SwFromRwRtRp - 水饱和度 (需要: P孔隙度, R电阻率)
        11: WrFromSwRp - 含水量 (需要: S_w水饱和度, R_p孔隙度)"""
    )
    entity_ids: list[int] = Field(
        description="输入实体ID列表，提供公式中需要的变量值"
    )
    regionId: Optional[int] = Field(
        default=None,
        description="计算区域ID，用于限定计算范围，可选"
    )
    params: Optional[dict[str, Any]] = Field(
        default=None,
        description="""公式参数字典，用于提供公式中变量的值。
        根据formulaId指定的公式，传入对应的变量名和值。
        例如: {"V_p": 5000, "V_s": 3000} 或 {"R_d": 2.5, "V_p": 5000, "V_s": 3000}"""
    )


@tool(args_schema=CalculatePropertyInput)
def calculate_property(
    formulaId: int,
    entity_ids: list[int],
    regionId: Optional[int] = None,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    基于公式ID进行属性计算，通过formulaId匹配内置公式，从entity_ids中提取变量值进行计算。
    支持的计算区域限定(regionId)和自定义参数(params)。
    """
    # 验证公式ID
    if formulaId not in FORMULA_DEFINITIONS:
        available_ids = list(FORMULA_DEFINITIONS.keys())
        return ToolOutput(
            success=False,
            message=f"无效的公式ID: {formulaId}。可用公式ID: {available_ids}"
        ).model_dump()

    formula_info = FORMULA_DEFINITIONS[formulaId]

    logger.info(
        "calculate_property 调用 | formulaId=%d(%s), entities=%s, regionId=%s, params=%s",
        formulaId, formula_info["name"], entity_ids, regionId, params
    )

    try:
        import DTPyRuntime as dtpr

        # 使用formulaId匹配公式
        output_entity_id = dtpr.calculate_property_by_entity(
            formulaId=formulaId,
            entity_ids=entity_ids,
            regionId=regionId,
            params=params
        )

        logger.info("属性计算完成 | 输出实体 ID=%s", output_entity_id)

        return ToolOutput(
            success=True,
            data={
                "entity_id": output_entity_id,
                "formula_name": formula_info["name"],
                "output_type": formula_info["output_type"],
            },
            message=f"属性计算成功，使用公式 {formula_info['name']} 计算 {formula_info['output_type']}，输出实体 ID {output_entity_id}",
            metadata={
                "formulaId": formulaId,
                "formula_name": formula_info["name"],
                "formula_text": formula_info["formula"],
                "output_type": formula_info["output_type"],
                "regionId": regionId,
                "params": params,
                "input_entity_count": len(entity_ids),
            },
        ).model_dump()

    except NotImplementedError as e:
        logger.warning("calculate_property_by_entity 暂未实现 | %s", e)
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        logger.error("属性计算失败 | %s", e, exc_info=True)
        return ToolOutput(success=False, message=f"属性计算失败: {e}").model_dump()
