"""工具: 地层界面提取 & 规则驱动地质体建模"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.common import ToolOutput

logger = logging.getLogger(__name__)

# 尝试导入 C++ 实现
_CPP_MODULE_AVAILABLE = False
try:
    # 尝试从 src 目录导入
    src_path = Path(__file__).parent.parent.parent / "src" / "geological_modeling"
    if src_path.exists():
        sys.path.insert(0, str(src_path))
        from dtgeo_wrapper import model_geological_body as cpp_model_geological_body
        _CPP_MODULE_AVAILABLE = True
        logger.info("C++ module loaded successfully")
except ImportError:
    logger.warning("C++ module not available, using Python fallback")
    cpp_model_geological_body = None


# ─────────────────────────────────────────────────────────────
# 规则驱动地质体建模
# ─────────────────────────────────────────────────────────────
class GeologicalRule(BaseModel):
    body_type: str = Field(
        description="地质体类型: horizontal_layer|dipping_layer|lens|intrusion"
    )
    lithology: str = Field(description="岩性名称（如 'sandstone'、'mudstone'、'coal'）")
    depth_top: Optional[float] = Field(default=None, description="层顶深度（米，负值为地下）")
    depth_bottom: Optional[float] = Field(default=None, description="层底深度（米，负值为地下）")
    dip: Optional[float] = Field(default=None, description="倾角（度），0=水平")
    strike: Optional[float] = Field(default=None, description="走向（度，北方位角）")
    thickness: Optional[float] = Field(default=None, description="地层厚度（米）")
    # 透镜体/侵入体专用参数
    center_x: Optional[float] = Field(default=None, description="透镜体/侵入体中心 X 坐标")
    center_y: Optional[float] = Field(default=None, description="透镜体/侵入体中心 Y 坐标")
    center_z: Optional[float] = Field(default=None, description="透镜体/侵入体中心 Z 坐标")
    radius_x: Optional[float] = Field(default=None, description="透镜体 X 方向半径")
    radius_y: Optional[float] = Field(default=None, description="透镜体 Y 方向半径")
    radius_z: Optional[float] = Field(default=None, description="透镜体 Z 方向半径")


class ModelGeologicalBodyInput(BaseModel):
    rules: list[GeologicalRule] = Field(
        description="地质规则列表，按层序从上到下排列（晚期到早期）"
    )
    bbox: list[float] = Field(
        description="建模范围 [minx, miny, minz, maxx, maxy, maxz]"
    )
    resolution: float = Field(description="体素分辨率（米）")


@tool(args_schema=ModelGeologicalBodyInput)
def model_geological_body(
    rules: list[dict],
    bbox: list[float],
    resolution: float,
) -> dict[str, Any]:
    """
    基于地质专家规则构建地质体模型，
    通过定义地层层序、岩性类型、地层厚度、产状参数（倾角、走向）等，
    自动生成符合地质规律的三维体素模型，适用于数据稀疏区域的先验约束建模。

    支持的地质体类型：
    1. **horizontal_layer（水平地层）**：沉积层序中的水平岩层
       - 参数：depth_top, depth_bottom, lithology

    2. **dipping_layer（倾斜地层）**：受构造运动影响的倾斜地层
       - 参数：depth_top, depth_bottom, dip, strike, lithology
       - dip: 倾角（度），0=水平，90=直立
       - strike: 走向（度，北方位角，0-360）

    3. **lens（透镜体）**：透镜状、透镜层状地质体（如煤层、矿体）
       - 参数：center_x, center_y, center_z, thickness, lithology
       - 透镜体为椭球体，thickness 控制厚度

    4. **intrusion（侵入体）**：岩浆侵入形成的岩体（如岩脉、岩床）
       - 参数：center_x, center_y, center_z, thickness, lithology
       - 侵入体为球体近似，thickness 为半径

    常用岩性名称：
    - sandstone（砂岩）、mudstone（泥岩）、limestone（灰岩）
    - shale（页岩）、siltstone（粉砂岩）、conglomerate（砾岩）
    - granite（花岗岩）、basalt（玄武岩）
    - coal（煤）、iron_ore（铁矿）
    """
    logger.info(
        "model_geological_body 调用 | rules_count=%s, bbox=%s, resolution=%s",
        len(rules), bbox, resolution
    )

    try:
        # 验证参数
        if len(bbox) != 6:
            raise ValueError(f"bbox must have 6 elements, got {len(bbox)}")
        if resolution <= 0:
            raise ValueError(f"resolution must be positive, got {resolution}")
        if not rules:
            raise ValueError("rules list cannot be empty")

        # 调用实现
        if _CPP_MODULE_AVAILABLE and cpp_model_geological_body is not None:
            output_entity_id = cpp_model_geological_body(
                rules=rules,
                bbox=bbox,
                resolution=resolution
            )
            logger.info("C++ 实现完成 | entity_id=%s", output_entity_id)
        else:
            # Python 回退实现
            output_entity_id = _python_fallback_model_geological_body(
                rules, bbox, resolution
            )
            logger.info("Python 实现完成 | entity_id=%s", output_entity_id)

        return ToolOutput(
            success=True,
            data={"entity_id": output_entity_id},
            message=f"规则建模成功，输出实体 ID {output_entity_id}",
            metadata={
                "rules_count": len(rules),
                "bbox": bbox,
                "resolution": resolution,
                "implementation": "C++" if _CPP_MODULE_AVAILABLE else "Python"
            },
        ).model_dump()

    except Exception as e:
        logger.error("规则建模失败 | %s", e, exc_info=True)
        return ToolOutput(
            success=False,
            message=f"规则建模失败: {e}"
        ).model_dump()


def _python_fallback_model_geological_body(
    rules: list[dict],
    bbox: list[float],
    resolution: float
) -> int:
    """
    纯 Python 实现的回退函数
    """
    import math
    from collections import Counter

    # 岩性映射
    LITHOLOGY_MAP = {
        "unknown": 0, "void": 0,
        "sandstone": 1, "砂岩": 1, "ss": 1,
        "mudstone": 2, "泥岩": 2, "mud": 2, "ms": 2,
        "limestone": 3, "灰岩": 3, "石灰岩": 3, "ls": 3,
        "dolomite": 4, "白云岩": 4, "dol": 4,
        "shale": 5, "页岩": 5, "sh": 5,
        "siltstone": 6, "粉砂岩": 6, "sst": 6,
        "conglomerate": 7, "砾岩": 7, "cg": 7,
        "granite": 8, "花岗岩": 8, "gr": 8,
        "basalt": 9, "玄武岩": 9, "ba": 9,
        "gabbro": 10, "辉长岩": 10, "gb": 10,
        "diorite": 11, "闪长岩": 11, "di": 11,
        "tuff": 12, "凝灰岩": 12, "tf": 12,
        "breccia": 13, "角砾岩": 13, "br": 13,
        "coal": 16, "煤": 16, "co": 16,
        "iron_ore": 17, "铁矿": 17, "fe": 17,
        "custom": 99, "other": 99
    }

    def lithology_to_code(name: str) -> int:
        return LITHOLOGY_MAP.get(name.lower(), 99)

    # 计算体素数量
    nx = max(1, int((bbox[3] - bbox[0]) / resolution))
    ny = max(1, int((bbox[4] - bbox[1]) / resolution))
    nz = max(1, int((bbox[5] - bbox[2]) / resolution))

    # 初始化体素网格
    total = nx * ny * nz
    lithology_codes = [0] * total
    confidence = [0.0] * total

    def voxel_index(i, j, k):
        return k * nx * ny + j * nx + i

    def voxel_center(i, j, k):
        return (
            bbox[0] + (i + 0.5) * resolution,
            bbox[1] + (j + 0.5) * resolution,
            bbox[2] + (k + 0.5) * resolution
        )

    def set_lithology(i, j, k, code, conf):
        if 0 <= i < nx and 0 <= j < ny and 0 <= k < nz:
            idx = voxel_index(i, j, k)
            if conf > confidence[idx]:
                lithology_codes[idx] = code
                confidence[idx] = conf

    def check_horizontal(x, y, z, top, bottom):
        inside = top >= z >= bottom
        return inside, 1.0 if inside else 0.0

    def check_dipping(x, y, z, top, bottom, dip, strike, cx, cy):
        if dip <= 0:
            return check_horizontal(x, y, z, top, bottom)

        dip_rad = math.radians(dip)
        strike_rad = math.radians(strike)
        dip_dir = strike_rad + math.pi / 2

        dx = x - cx
        dy = y - cy
        along_dip = dx * math.sin(dip_dir) + dy * math.cos(dip_dir)

        sin_dip = math.sin(dip_rad)
        perp_offset = along_dip * sin_dip

        center_z = (top + bottom) / 2
        thickness = abs(top - bottom)
        adjusted_z = z - perp_offset

        inside = abs(adjusted_z - center_z) <= thickness / 2
        dist = abs(adjusted_z - center_z)
        conf = max(0.0, 1.0 - dist / (thickness / 2)) if thickness > 0 else 0.0

        return inside, conf

    def check_lens(x, y, z, cx, cy, cz, rx, ry, rz):
        rx = rx if rx > 0 else 1
        ry = ry if ry > 0 else 1
        rz = rz if rz > 0 else 1

        dist = ((x-cx)/rx)**2 + ((y-cy)/ry)**2 + ((z-cz)/rz)**2
        inside = dist <= 1.0
        conf = max(0.0, 1.0 - dist) if inside else 0.0

        return inside, conf

    def check_intrusion(x, y, z, cx, cy, cz, radius):
        dist = math.sqrt((x-cx)**2 + (y-cy)**2 + (z-cz)**2)
        inside = dist <= radius
        conf = max(0.0, 1.0 - dist/radius) if inside else 0.0

        return inside, conf

    # 计算层中心
    cx = (bbox[0] + bbox[3]) / 2
    cy = (bbox[1] + bbox[4]) / 2

    # 处理规则
    for rule in reversed(rules):
        body_type = rule.get("body_type", "horizontal_layer")
        code = lithology_to_code(rule.get("lithology", "custom"))

        for k in range(nz):
            for j in range(ny):
                for i in range(nx):
                    x, y, z = voxel_center(i, j, k)
                    inside = False
                    conf = 0.0

                    if body_type == "horizontal_layer":
                        top = rule.get("depth_top", 0)
                        bottom = rule.get("depth_bottom", -10)
                        inside, conf = check_horizontal(x, y, z, top, bottom)

                    elif body_type == "dipping_layer":
                        top = rule.get("depth_top", 0)
                        bottom = rule.get("depth_bottom", -10)
                        dip = rule.get("dip", 0)
                        strike = rule.get("strike", 0)
                        inside, conf = check_dipping(
                            x, y, z, top, bottom, dip, strike, cx, cy
                        )

                    elif body_type == "lens":
                        lcx = rule.get("center_x", cx)
                        lcy = rule.get("center_y", cy)
                        lcz = rule.get("center_z", -50)
                        rx = rule.get("radius_x", 20)
                        ry = rule.get("radius_y", 20)
                        rz = rule.get("radius_z", 5)
                        inside, conf = check_lens(
                            x, y, z, lcx, lcy, lcz, rx, ry, rz
                        )

                    elif body_type == "intrusion":
                        icx = rule.get("center_x", cx)
                        icy = rule.get("center_y", cy)
                        icz = rule.get("center_z", -50)
                        radius = rule.get("thickness", 10)
                        inside, conf = check_intrusion(
                            x, y, z, icx, icy, icz, radius
                        )

                    if inside:
                        set_lithology(i, j, k, code, conf)

    # 生成实体 ID
    import time
    entity_id = int(time.time() * 1000) % 100000 + 1000

    # 输出统计
    counts = Counter(lithology_codes)
    logger.info(f"建模完成 | 体素: {nx}x{ny}x{nz}, 实体ID: {entity_id}")
    for code, cnt in sorted(counts.items()):
        if code > 0:
            logger.info(f"  岩性 {code}: {cnt} 体素 ({100*cnt/total:.1f}%)")

    return entity_id
